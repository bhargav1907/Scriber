"""
Scriber — FastAPI Backend Server
Orchestrates recording → transcription → LLM cleanup → paste pipeline.
Communicates with the Electron frontend via WebSocket.
"""

import asyncio
import json
import time
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config import load_config, save_config
from database import init_db, save_transcription, get_history, delete_transcription, clear_history
from audio_recorder import AudioRecorder
from transcriber import Transcriber
from llm_cleaner import LLMCleaner
from clipboard import paste_text
from fn_listener import FnKeyListener


# ---------------------------------------------------------------------------
# Application State
# ---------------------------------------------------------------------------

class AppState:
    def __init__(self):
        self.config = load_config()
        self.recorder = AudioRecorder()
        self.transcriber = Transcriber(self.config.get("whisper_model", "base"))
        self.cleaner = LLMCleaner(
            model=self.config.get("llm_model", "llama3.2:3b"),
            host=self.config.get("ollama_host", "http://localhost:11434"),
        )
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
    state.is_recording = True
    last_level_ts = [0.0]

    def level_cb(level: float):
        now = time.time()
        if now - last_level_ts[0] > 0.066:  # ~15 FPS throttle
            last_level_ts[0] = now
            broadcast_from_thread({"type": "audio_level", "level": round(level, 3)})

    state.recorder.level_callback = level_cb
    state.recorder.start()
    await broadcast({"type": "state", "state": "listening"})
    print("[Scriber] 🎤 Recording started")


async def stop_recording():
    """Stop listening and kick off transcription + cleanup pipeline."""
    if state.is_processing or not state.is_recording:
        return
    state.is_recording = False
    state.is_processing = True
    await broadcast({"type": "state", "state": "processing"})
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

        # 1. Transcribe
        raw_text = state.transcriber.transcribe(audio_path)
        if not raw_text or not raw_text.strip():
            broadcast_from_thread({"type": "state", "state": "error", "message": "No speech detected"})
            time.sleep(2.0)
            broadcast_from_thread({"type": "state", "state": "idle"})
            return

        # 2. LLM cleanup (optional)
        cleaned_text = raw_text
        if state.config.get("llm_cleanup_enabled", True):
            try:
                loop = asyncio.new_event_loop()
                cleaned_text = loop.run_until_complete(state.cleaner.cleanup(raw_text))
                loop.close()
            except Exception as e:
                print(f"[Scriber] LLM cleanup error (using raw text): {e}")

        # 3. Paste into the active app
        if state.config.get("auto_paste", True):
            time.sleep(0.1)  # Brief pause so the OS can settle
            paste_text(cleaned_text)

        # 4. Save to history
        save_transcription(raw_text, cleaned_text, duration, state.config.get("whisper_model", "base"))

        # 5. Broadcast success
        broadcast_from_thread({
            "type": "state",
            "state": "done",
            "raw_text": raw_text,
            "cleaned_text": cleaned_text,
            "duration": round(duration, 1),
        })
        print(f"[Scriber] ✅ Done ({round(duration, 1)}s) → {cleaned_text[:80]}")

        time.sleep(2.0)
        broadcast_from_thread({"type": "state", "state": "idle"})

    except Exception as e:
        print(f"[Scriber] ❌ Pipeline error: {e}")
        broadcast_from_thread({"type": "state", "state": "error", "message": str(e)})
        time.sleep(3.0)
        broadcast_from_thread({"type": "state", "state": "idle"})
    finally:
        state.is_processing = False


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
        def on_fn_action(action: str):
            loop = state.main_loop
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(handle_fn_action(action), loop)

        fn_listener = FnKeyListener(on_fn_action)
        fn_listener.start()
    except Exception as e:
        print(f"[Scriber] Could not start Fn key listener: {e}")

    print("[Scriber] Backend server starting on http://127.0.0.1:58932")
    yield
    # ── Shutdown ───────────────────────────────────────────────────────
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
    await websocket.send_json({
        "type": "init",
        "state": "recording" if state.is_recording else ("processing" if state.is_processing else "idle"),
        "config": state.config,
        "whisper_ready": state.transcriber.is_ready,
    })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "toggle_recording":
                await handle_toggle()

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
    }


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

    await broadcast({"type": "config", "config": state.config})
    return state.config


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=58932, log_level="warning")
