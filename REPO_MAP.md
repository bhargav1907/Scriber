# 🗺️ Scriber Codebase Architecture Map
> Auto-generated AST & structural symbol map for token-efficient agent navigation.
> Keep this map updated to provide instant whole-repo awareness in ~1,000 tokens.

## 🐍 Python Backend (`backend/`)

### `backend/audio_ducker.py`
  > Scriber — Audio Ducking Manager
  - **class `AudioDucker`**
    - `def __init__(self)`
    - `def duck(self, target_volume)`
    - `def unduck(self)`

### `backend/audio_recorder.py`
  > Scriber — Microphone Audio Recorder
  - **class `AudioRecorder`**
    - `def __init__(self, sample_rate, channels, device)`
    - `def set_device(self, device)`
    - `def refresh_devices(cls)`
    - `def get_input_devices(cls, force_refresh)`
    - `def check_for_device_changes(cls)`
    - `def start(self)`
    - `def stop(self)`
    - `def get_duration(self)`
    - `def _audio_callback(self, indata, frames, time_info, status)`
    - `def _process_audio(self)`

### `backend/clipboard.py`
  > Scriber — High-Performance Native macOS Clipboard & Paste
  - `def _restore_clipboard_string(prev_text)`
  - `def paste_text(text, restore_previous, restore_delay)`

### `backend/config.py`
  > Scriber — Configuration Management
  - `def load_config()`
  - `def save_config(config)`

### `backend/context_detector.py`
  > Scriber — Active Application Context Detector
  - `def get_frontmost_app()`

### `backend/database.py`
  > Scriber — High-Performance SQLite Database for Transcription History
  - `def _connect()`
  - `def init_db()`
  - `def save_transcription(raw_text, cleaned_text, duration, model)`
  - `def get_history(limit, offset)`
  - `def delete_transcription(row_id)`
  - `def clear_history()`
  - `def get_stats()`

### `backend/fn_listener.py`
  > Scriber — macOS Fn / Globe Key Global Listener
  - **class `FnKeyListener`**
    - `def __init__(self, toggle_callback)`
    - `def start(self)`
    - `def _run(self)`
    - `def stop(self)`

### `backend/llm_cleaner.py`
  > Scriber — LLM Text Cleanup via Ollama
  - **class `LLMCleaner`**
    - `def __init__(self, model, host)`
    - `def _get_client(self)`
    - `async def aclose(self)`
    - `async def cleanup(self, raw_text, mode, custom_vocabulary, word_replacements)`
    - `def _sanitize_llm_output(self, cleaned, raw_text)`
    - `def _apply_replacements(self, text, replacements)`
    - `async def check_connection(self)`

### `backend/main.py`
  > Scriber — FastAPI Backend Server
  - **class `AppState`**
    - `def __init__(self)`
  - `async def broadcast(message)`
  - `def broadcast_from_thread(message)`
  - `async def start_recording()`
  - `async def stop_recording()`
  - `async def handle_toggle()`
  - `async def handle_fn_action(action)`
  - `async def _process_pipeline()`
  - `async def lifespan(app)`
  - `async def ws_endpoint(websocket)` [@app.websocket]
  - `async def health()` [@app.get]
  - `async def api_stats()` [@app.get]
  - `async def api_audio_devices()` [@app.get]
  - `async def api_history(limit, offset)` [@app.get]
  - `async def api_delete(row_id)` [@app.delete]
  - `async def api_clear()` [@app.delete]
  - `async def api_get_config()` [@app.get]
  - `async def api_update_config(body)` [@app.post]

### `backend/transcriber.py`
  > Scriber — Whisper Transcription Engine
  - **class `Transcriber`**
    - `def __init__(self, model_size)`
    - `def is_ready(self)`
    - `def load_model(self, model_size)`
    - `def transcribe(self, audio_source)`

## ⚡ Electron & Frontend (`main.js`, `preload.js`, `src/`)

### `main.js`
  > Scriber — Electron Main Process
  - *IPC Receive:* `ipcMain.on('clear-history')`
  - *IPC Receive:* `ipcMain.on('delete-entry')`
  - *IPC Receive:* `ipcMain.on('fetch-audio-devices')`
  - *IPC Receive:* `ipcMain.on('fetch-history')`
  - *IPC Receive:* `ipcMain.on('fetch-stats')`
  - *IPC Receive:* `ipcMain.on('request-duration')`
  - *IPC Receive:* `ipcMain.on('request-health')`
  - *IPC Receive:* `ipcMain.on('show-main-window')`
  - *IPC Receive:* `ipcMain.on('toggle-recording')`
  - *IPC Receive:* `ipcMain.on('update-config')`
  - `function createPNGBuffer(width, height, drawFn)`
  - `function chunk(type, data)`
  - `function crc32(buf)`
  - `function setPixel(buf, w, x, y, r, g, b, a = 255)`
  - `function makeTrayIcon(state)`
  - `function updateTrayIcon(state)`
  - `function secureWebContents(win)`
  - `function createWidgetWindow()`
  - `function showWidget()`
  - `function hideWidget()`
  - `function createMainWindow()`
  - `function createTray()`
  - `function spawnPythonBackend()`
  - `function connectWebSocket()`
  - `function scheduleReconnect()`
  - `function sendWS(data)`
  - `function sendToggle()`
  - `function handleBackendMessage(msg)`
  - `function sendToAllRenderers(channel, data)`
  - `function setupIPC()`
  - `function stopBackendProcess()`

### `preload.js`
  > Scriber — Electron Preload Script
  - *Bridge:* `scriber.clearHistory()` ↔ `clear-history`
  - *Bridge:* `scriber.deleteEntry()` ↔ `delete-entry`
  - *Bridge:* `scriber.fetchAudioDevices()` ↔ `fetch-audio-devices`
  - *Bridge:* `scriber.fetchHistory()` ↔ `fetch-history`
  - *Bridge:* `scriber.fetchStats()` ↔ `fetch-stats`
  - *Bridge:* `scriber.onAudioDevicesUpdate()` ↔ `audio-devices-update`
  - *Bridge:* `scriber.onAudioLevel()` ↔ `audio-level`
  - *Bridge:* `scriber.onConfigChange()` ↔ `config-change`
  - *Bridge:* `scriber.onDuration()` ↔ `duration`
  - *Bridge:* `scriber.onHealthUpdate()` ↔ `health-update`
  - *Bridge:* `scriber.onHistoryUpdate()` ↔ `history-update`
  - *Bridge:* `scriber.onStateChange()` ↔ `state-change`
  - *Bridge:* `scriber.onStatsUpdate()` ↔ `stats-update`
  - *Bridge:* `scriber.requestDuration()` ↔ `request-duration`
  - *Bridge:* `scriber.requestHealth()` ↔ `request-health`
  - *Bridge:* `scriber.showMainWindow()` ↔ `show-main-window`
  - *Bridge:* `scriber.toggleRecording()` ↔ `toggle-recording`
  - *Bridge:* `scriber.updateConfig()` ↔ `update-config`

### `src/renderer.js`
  > Scriber — Main Dashboard Renderer
  - `function switchView(viewName)`
  - `function updateStats(stats)`
  - `function renderFilteredHistory()`
  - `function updateStatusBadge(state, extra = {})`
  - `function renderHistory(items)`
  - `function getDateLabel(date)`
  - `function formatTime(date)`
  - `function escapeHtml(str)`
  - `function showToast(message)`
  - `function renderVocabularyTags(vocabList)`
  - `function addVocabularyTerm()`
  - `function removeVocabularyTerm(index)`
  - `function renderReplacements(replacements)`
  - `function addReplacement()`
  - `function renderAudioDevices(data, selectedId = null)`
  - `function applyConfig(config)`
  - `function sendConfigUpdate(key, value)`

### `src/widget.js`
  > Scriber — Floating Widget Renderer
  - `function getAudioContext()`
  - `function playTone(freq, duration = 0.12, vol = 0.05)`
  - `function playStartSound()`
  - `function playDoneSound()`
  - `function playErrorSound()`
  - `function startTimer()`
  - `function stopTimer()`
  - `function updateAppBadge(appInfo, mode)`
  - `function setState(state, extra = {})`
  - `function updateAudioBars(level)`