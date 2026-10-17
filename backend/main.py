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

from config import load_config, save_config
from database import init_db, save_transcription, get_history, delete_transcription, clear_history, get_stats
from audio_recorder import AudioRecorder
from transcriber import Transcriber
from llm_cleaner import LLMCleaner
from clipboard import paste_text
from fn_listener import FnKeyListener
from context_detector import get_frontmost_app
from audio_ducker import AudioDucker


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

    await broadcast({
        "type": "state",
        "state": "listening",
        "active_app": state.current_app,
        "mode": state.current_mode,
    })
    print(f"[Scriber] 🎤 Recording started (App: {state.current_app['name']}, Mode: {state.current_mode})")


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

    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _process_pipeline)


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


def _process_pipeline():
    """Runs in a background thread: transcribe → cleanup → paste → save."""
    try:
        audio_path, duration = state.recorder.stop()

        if not audio_path:
            broadcast_from_thread({"type": "state", "state": "error", "message": "No audio captured"})
            time.sleep(2.0)
            broadcast_from_thread({"type": "state", "state": "idle"})
            return

        t_pipeline_start = time.time()

        # 1. Transcribe audio acoustically (without prompt injection to prevent hallucination loops)
        t_w0 = time.time()
        custom_vocab = state.config.get("custom_vocabulary", [])
        raw_text = state.transcriber.transcribe(audio_path)
        t_whisper = time.time() - t_w0

        # Anti-hallucination guard 1: If raw text is just an echoing of the custom vocabulary list, discard it
        if raw_text and custom_vocab:
            words = [w.strip().lower() for w in re.split(r'[,.\s]+', raw_text) if w.strip()]
            vocab_set = {w.strip().lower() for v in custom_vocab for w in v.split()}
            if words and all(w in vocab_set for w in words) and len(set(words)) >= len(vocab_set) * 0.7:
                print(f"[Scriber] ⚠️ Discarded prompt hallucination: '{raw_text[:60]}'")
                raw_text = ""

        # Anti-hallucination guard 2: Whisper silence phantom outputs ("Thank you.", "Thanks for watching!", etc.)
        if raw_text and raw_text.strip().lower() in {
            "thank you.", "thank you", "thanks for watching.", "thanks for watching!",
            "thank you very much.", "thank you very much", "thanks.", "thanks",
            "you", "bye.", "bye", "goodbye.", "goodbye",
            "please subscribe.", "subscribe", "[music]", "[applause]", "[silence]",
            "(music)", "(applause)", "(silence)", "[blank_audio]", "thank you for watching.",
            "thank you for watching", "so, thank you.", "so, thank you", "thank you so much.",
            "thank you so much", "thanks for listening.", "thanks for listening!",
        }:
            print(f"[Scriber] ⚠️ Discarded silence hallucination: '{raw_text}'")
            raw_text = ""

        if not raw_text or not raw_text.strip():
            broadcast_from_thread({"type": "state", "state": "error", "message": "No speech detected"})
            time.sleep(2.0)
            broadcast_from_thread({"type": "state", "state": "idle"})
            return

        # 2. LLM cleanup with app mode context & word replacements
        cleaned_text = raw_text
        t_llm = 0.0
        word_reps = state.config.get("word_replacements", {})
        if state.config.get("llm_cleanup_enabled", True) and state.current_mode != "raw":
            t_l0 = time.time()
            try:
                loop = asyncio.new_event_loop()
                cleaned_text = loop.run_until_complete(
                    state.cleaner.cleanup(
                        raw_text,
                        mode=state.current_mode,
                        custom_vocabulary=custom_vocab,
                        word_replacements=word_reps,
                    )
                )
                loop.close()
            except Exception as e:
                print(f"[Scriber] LLM cleanup error (using raw text): {e}")
                cleaned_text = state.cleaner._apply_replacements(raw_text, word_reps)
            t_llm = time.time() - t_l0
        else:
            cleaned_text = state.cleaner._apply_replacements(raw_text, word_reps)

        # 3. Paste into the active app
        if state.config.get("auto_paste", True):
            time.sleep(0.05)  # Brief pause so the OS can settle
            paste_text(cleaned_text)

        # 4. Save to history
        save_transcription(raw_text, cleaned_text, duration, state.config.get("whisper_model", "base"))

        t_total = time.time() - t_pipeline_start
        word_count = len(cleaned_text.split())

        # 5. Broadcast success
        broadcast_from_thread({
            "type": "state",
            "state": "done",
            "raw_text": raw_text,
            "cleaned_text": cleaned_text,
            "duration": round(duration, 1),
            "pipeline_time": round(t_total, 2),
            "word_count": word_count,
            "active_app": state.current_app,
            "mode": state.current_mode,
        })
        print(f"[Scriber] ⚡ Processed in {t_total:.2f}s (STT: {t_whisper:.2f}s, LLM: {t_llm:.2f}s) → \"{cleaned_text[:60]}\"")

        time.sleep(2.0)
        broadcast_from_thread({"type": "state", "state": "idle"})

    except Exception as e:
        print(f"[Scriber] ❌ Pipeline error: {e}")
        broadcast_from_thread({"type": "state", "state": "error", "message": str(e)})
        time.sleep(3.0)
        broadcast_from_thread({"type": "state", "state": "idle"})
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
    print("[Scriber] Backend server shutting down")


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    return get_history(limit, offset)


@app.delete("/api/history/{row_id}")
async def api_delete(row_id: int):
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
    state.config.update(body)
    save_config(state.config)

    # Hot-reload affected components
    if "whisper_model" in body:
        threading.Thread(
            target=state.transcriber.load_model,
            args=(body["whisper_model"],),
            daemon=True,
        ).start()
    if "llm_model" in body:
        state.cleaner.model = body["llm_model"]
    if "ollama_host" in body:
        state.cleaner.host = body["ollama_host"]
    if "input_device" in body:
        state.recorder.set_device(body["input_device"])

    await broadcast({"type": "config", "config": state.config})
    return state.config


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=58932, log_level="warning")
