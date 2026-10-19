"""
Scriber — FastAPI Backend Server
Orchestrates recording → transcription → LLM cleanup → paste pipeline.
Communicates with the Electron frontend via WebSocket.
"""

import asyncio
import json
import re
import time
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

try:
    from backend.config import load_config, save_config
    from backend.database import init_db, save_transcription, get_history, delete_transcription, clear_history, get_stats
    from backend.audio_recorder import AudioRecorder
    from backend.transcriber import Transcriber
    from backend.llm_cleaner import LLMCleaner
    from backend.clipboard import paste_text
    from backend.fn_listener import FnKeyListener
    from backend.context_detector import get_frontmost_app
    from backend.audio_ducker import AudioDucker
    from backend.streaming_transcriber import StreamingTranscriber
except ImportError:
    from config import load_config, save_config
    from database import init_db, save_transcription, get_history, delete_transcription, clear_history, get_stats
    from audio_recorder import AudioRecorder
    from transcriber import Transcriber
    from llm_cleaner import LLMCleaner
    from clipboard import paste_text
    from fn_listener import FnKeyListener
    from context_detector import get_frontmost_app
    from audio_ducker import AudioDucker
    from streaming_transcriber import StreamingTranscriber


# ---------------------------------------------------------------------------
# Application State
# ---------------------------------------------------------------------------

class AppState:
    def __init__(self):
        self.config = load_config()
        self.recorder = AudioRecorder(device=self.config.get("input_device"))
        self.transcriber = Transcriber(self.config.get("whisper_model", "base"))
        self.cleaner = LLMCleaner(
            model=self.config.get("llm_model", "llama3.2:3b"),
            host=self.config.get("ollama_host", "http://localhost:11434"),
        )
        self.audio_ducker = AudioDucker()
        self.streaming_transcriber: StreamingTranscriber | None = None
        self.current_app = {"name": "General", "category": "general", "icon": "✨"}
        self.current_mode = "general"
        self.is_recording = False
        self.is_processing = False
        self.websocket_clients: set[WebSocket] = set()
        self.main_loop: asyncio.AbstractEventLoop | None = None


state = AppState()


# ---------------------------------------------------------------------------
# WebSocket Broadcasting
# ---------------------------------------------------------------------------

async def broadcast(message: dict):
    """Send a JSON message to every connected WebSocket client."""
    dead = set()
    for ws in state.websocket_clients.copy():
        try:
            await ws.send_json(message)
        except Exception:
            dead.add(ws)
    state.websocket_clients -= dead


def broadcast_from_thread(message: dict):
    """Thread-safe wrapper — schedule broadcast on the main event loop."""
    loop = state.main_loop
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(broadcast(message), loop)


# ---------------------------------------------------------------------------
# Recording Toggle & Processing Pipeline
# ---------------------------------------------------------------------------

async def start_recording():
    """Start listening and recording audio from the microphone."""
    if state.is_processing or state.is_recording:
        return

    # Detect frontmost active application context
    app_info = get_frontmost_app()
    config_mode = state.config.get("dictation_mode", "auto")
    effective_mode = app_info.get("category", "general") if config_mode == "auto" else config_mode

    state.current_app = app_info
    state.current_mode = effective_mode
    state.is_recording = True
    last_level_ts = [0.0]

    # Audio ducking (temporarily quiet background audio / music)
    if state.config.get("audio_ducking", False):
        try:
            state.audio_ducker.duck()
        except Exception:
            pass

    def level_cb(level: float):
        now = time.time()
        if now - last_level_ts[0] > 0.066:  # ~15 FPS throttle
            last_level_ts[0] = now
            broadcast_from_thread({"type": "audio_level", "level": round(level, 3)})

    state.recorder.level_callback = level_cb
    try:
        ok = state.recorder.start()
        if not ok:
            state.is_recording = False
            if state.config.get("audio_ducking", False):
                state.audio_ducker.unduck()
            await broadcast({"type": "state", "state": "error", "message": "Mic stream failed"})
            await asyncio.sleep(2.0)
            await broadcast({"type": "state", "state": "idle"})
            return
    except Exception as e:
        state.is_recording = False
        if state.config.get("audio_ducking", False):
            state.audio_ducker.unduck()
        print(f"[Scriber] ❌ Failed to start recording: {e}")
        await broadcast({"type": "state", "state": "error", "message": str(e)})
        await asyncio.sleep(2.0)
        await broadcast({"type": "state", "state": "idle"})
        return

    # Initialize and start concurrent streaming transcriber
    delivery_mode = state.config.get("delivery_mode", "paste_on_finish")
    llm_enabled = state.config.get("llm_cleanup_enabled", True)
    custom_vocab = state.config.get("custom_vocabulary", [])
    word_reps = state.config.get("word_replacements", {})
    app_name = state.current_app.get("name") if state.current_app else None

    state.streaming_transcriber = StreamingTranscriber(
        transcriber=state.transcriber,
        cleaner=state.cleaner,
        delivery_mode=delivery_mode,
        custom_vocabulary=custom_vocab,
        word_replacements=word_reps,
        app_name=app_name,
        mode=state.current_mode,
        llm_enabled=llm_enabled,
    )

    await broadcast({
        "type": "state",
        "state": "listening",
        "active_app": state.current_app,
        "mode": state.current_mode,
    })
    print(f"[Scriber] 🎤 Recording started (App: {state.current_app['name']}, Mode: {state.current_mode}, Delivery: {delivery_mode})")


async def stop_recording():
    """Stop listening and kick off transcription + cleanup pipeline."""
    if state.is_processing or not state.is_recording:
        return
    state.is_recording = False
    state.is_processing = True

    # Restore system volume immediately upon stopping recording
    if state.config.get("audio_ducking", False):
        try:
            state.audio_ducker.unduck()
        except Exception:
            pass

    await broadcast({
        "type": "state",
        "state": "processing",
        "active_app": state.current_app,
        "mode": state.current_mode,
    })
    print("[Scriber] ⏳ Processing …")

    asyncio.create_task(_process_pipeline())


async def handle_toggle():
    """Toggle recording on/off."""
    if state.is_recording:
        await stop_recording()
    else:
        await start_recording()


async def handle_fn_action(action: str):
    """Handle Fn key events from listener (start, stop, or toggle)."""
    if action == "start":
        await start_recording()
    elif action == "stop":
        await stop_recording()
    else:
        await handle_toggle()


async def _process_pipeline():
    """Asynchronous pipeline: finalize concurrent streaming transcription → LLM cleanup → native paste → save."""
    try:
        # 1. Stop recorder and get in-memory float32 audio
        audio_np, duration, audio_path = state.recorder.stop()

        if audio_np is None or audio_np.size == 0:
            await broadcast({"type": "state", "state": "error", "message": "No audio captured"})
            await asyncio.sleep(2.0)
            await broadcast({"type": "state", "state": "idle"})
            return

        t_pipeline_start = time.time()

        # 2. Transcribe and deliver through pipeline orchestrator
        if state.streaming_transcriber:
            result = await state.streaming_transcriber.finalize(
                full_audio_np=audio_np,
                auto_paste=state.config.get("auto_paste", True),
            )
            raw_text = result["raw_text"]
            cleaned_text = result["cleaned_text"]
            whisper_ms = result["whisper_ms"]
            llm_ms = result["llm_ms"]
            total_ms = result["total_ms"]
        else:
            raw_text, cleaned_text = "", ""
            whisper_ms, llm_ms, total_ms = 0, 0, 0

        if not raw_text or not raw_text.strip():
            await broadcast({"type": "state", "state": "error", "message": "No speech detected"})
            await asyncio.sleep(2.0)
            await broadcast({"type": "state", "state": "idle"})
            return

        # 3. Save to history
        save_transcription(raw_text, cleaned_text, duration, state.config.get("whisper_model", "large-v3-turbo"))

        word_count = len(cleaned_text.split())

        # 4. Broadcast success with metrics breakdown
        await broadcast({
            "type": "state",
            "state": "done",
            "raw_text": raw_text,
            "cleaned_text": cleaned_text,
            "text": cleaned_text,
            "duration": round(duration, 1),
            "pipeline_time": round(total_ms / 1000.0, 2),
            "word_count": word_count,
            "active_app": state.current_app,
            "mode": state.current_mode,
            "metrics": {
                "whisper_ms": whisper_ms,
                "llm_ms": llm_ms,
                "total_ms": total_ms,
                "delivery_mode": state.config.get("delivery_mode", "paste_on_finish"),
                "llm_enabled": state.config.get("llm_cleanup_enabled", True),
            },
        })
        print(f"[Scriber] ⚡ Completed in {total_ms}ms (Whisper: {whisper_ms}ms · LLM: {llm_ms}ms) → \"{cleaned_text[:60]}\"")

        await asyncio.sleep(2.0)
        await broadcast({"type": "state", "state": "idle"})

    except Exception as e:
        print(f"[Scriber] ❌ Pipeline error: {e}")
        await broadcast({"type": "state", "state": "error", "message": str(e)})
        await asyncio.sleep(3.0)
        await broadcast({"type": "state", "state": "idle"})
    finally:
        state.is_processing = False
        if state.config.get("audio_ducking", False):
            try:
                state.audio_ducker.unduck()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# FastAPI App & Lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────────────
    state.main_loop = asyncio.get_running_loop()
    init_db()

    # Pre-load Whisper model in a background thread
    threading.Thread(target=state.transcriber.load_model, daemon=True).start()

    # Start hardware Fn key listener
    fn_listener = None
    try:
        def on_fn_toggle():
            loop = state.main_loop
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(handle_toggle(), loop)

        fn_listener = FnKeyListener(on_fn_toggle)
        fn_listener.start()
    except Exception as e:
        print(f"[Scriber] Could not start Fn key listener: {e}")

    # Background task: Monitor audio hardware changes (e.g. Bluetooth headphones connected/disconnected)
    async def device_watcher():
        while True:
            await asyncio.sleep(5.0)
            try:
                if not state.is_recording and not state.is_processing:
                    has_changed, devices_data = AudioRecorder.check_for_device_changes()
                    if has_changed:
                        print(f"[Scriber] 🎧 Audio device configuration changed: Default is now '{devices_data.get('default_name')}'")
                        await broadcast({
                            "type": "audio_devices_update",
                            "audio_devices": devices_data,
                        })
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    watcher_task = asyncio.create_task(device_watcher())

    print("[Scriber] Backend server starting on http://127.0.0.1:58932")
    yield
    # ── Shutdown ───────────────────────────────────────────────────────
    watcher_task.cancel()
    if fn_listener:
        fn_listener.stop()
    await state.cleaner.aclose()
    print("[Scriber] Backend server shutting down")


app = FastAPI(lifespan=lifespan)

# ---------------------------------------------------------------------------
# Security & Config Validation
# ---------------------------------------------------------------------------

ALLOWED_ORIGINS = [
    "http://127.0.0.1",
    "http://localhost",
    "http://127.0.0.1:58932",
    "http://localhost:58932",
    "null",  # Electron file:// protocol renderer
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

ALLOWED_CONFIG_TYPES = {
    "whisper_model": (str,),
    "llm_model": (str,),
    "ollama_host": (str,),
    "dictation_mode": (str,),
    "input_device": (str, int, type(None)),
    "audio_ducking": (bool,),
    "llm_cleanup_enabled": (bool,),
    "auto_paste": (bool,),
    "custom_vocabulary": (list,),
    "word_replacements": (dict,),
    "delivery_mode": (str,),
    "sound_effects": (bool,),
}


# ---------------------------------------------------------------------------
# WebSocket Endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    state.websocket_clients.add(websocket)

    # Send the current state + config on connect
    app_info = get_frontmost_app()
    state.current_app = app_info
    await websocket.send_json({
        "type": "init",
        "state": "recording" if state.is_recording else ("processing" if state.is_processing else "idle"),
        "config": state.config,
        "whisper_ready": state.transcriber.is_ready,
        "active_app": app_info,
        "mode": state.current_mode,
        "audio_devices": AudioRecorder.get_input_devices(force_refresh=True),
        "stats": get_stats(),
    })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "toggle_recording":
                await handle_toggle()

            elif msg_type == "refresh_devices":
                devices = AudioRecorder.get_input_devices(force_refresh=True)
                await websocket.send_json({
                    "type": "audio_devices_update",
                    "audio_devices": devices,
                })

            elif msg_type == "get_duration":
                await websocket.send_json({
                    "type": "duration",
                    "duration": round(state.recorder.get_duration(), 1),
                })

    except WebSocketDisconnect:
        state.websocket_clients.discard(websocket)
    except Exception:
        state.websocket_clients.discard(websocket)


# ---------------------------------------------------------------------------
# REST Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    ollama_ok = await state.cleaner.check_connection()
    return {
        "status": "ok",
        "whisper_model": state.config.get("whisper_model"),
        "whisper_ready": state.transcriber.is_ready,
        "ollama_connected": ollama_ok,
        "is_recording": state.is_recording,
        "is_processing": state.is_processing,
        "audio_devices": AudioRecorder.get_input_devices(),
        "stats": get_stats(),
    }


@app.get("/api/stats")
async def api_stats():
    return get_stats()


@app.get("/api/audio-devices")
async def api_audio_devices():
    return AudioRecorder.get_input_devices()


@app.get("/api/history")
async def api_history(limit: int = 100, offset: int = 0):
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)
    return get_history(safe_limit, safe_offset)


@app.delete("/api/history/{row_id}")
async def api_delete(row_id: int):
    if row_id > 0:
        delete_transcription(row_id)
    return {"status": "deleted"}


@app.delete("/api/history")
async def api_clear():
    clear_history()
    return {"status": "cleared"}


@app.get("/api/config")
async def api_get_config():
    return state.config


@app.post("/api/config")
async def api_update_config(body: dict):
    # Sanitize and validate inputs against strict whitelist
    sanitized = {}
    for key, val in body.items():
        if key in ALLOWED_CONFIG_TYPES:
            expected_types = ALLOWED_CONFIG_TYPES[key]
            if isinstance(val, expected_types):
                sanitized[key] = val

    state.config.update(sanitized)
    save_config(state.config)

    # Hot-reload affected components
    if "whisper_model" in sanitized:
        threading.Thread(
            target=state.transcriber.load_model,
            args=(sanitized["whisper_model"],),
            daemon=True,
        ).start()
    if "llm_model" in sanitized:
        state.cleaner.model = sanitized["llm_model"]
    if "ollama_host" in sanitized:
        state.cleaner.host = sanitized["ollama_host"]
    if "input_device" in sanitized:
        state.recorder.set_device(sanitized["input_device"])

    await broadcast({"type": "config", "config": state.config})
    return state.config


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=58932, log_level="warning")
