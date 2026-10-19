# Real-Time Streaming Dictation & Live Typing Implementation Plan

> **For Agent:** Use `~/.gemini/config/skills/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Eliminate post-recording release delay by transcribing audio chunks concurrently while speaking, with configurable delivery via instant buffered paste or direct real-time typing into the focused window, complete with Whisper vs LLM latency benchmarks.

**Architecture:**
A concurrent audio streaming processor slices incoming 16kHz PCM audio into ~1-second VAD speech chunks. A background worker transcribes completed chunks via Apple Silicon Metal GPU Whisper while the hotkey is held, maintaining a rolling context prefix. Text is routed either to live Quartz keystroke injection (`live_typing`) or staged for instantaneous `<0.5ms` paste upon release (`paste_on_finish`), reporting sub-second Whisper and LLM latency metrics to the HUD and dashboard.

**Tech Stack:**
- Python 3.14 + FastAPI + WebSockets + MLX Whisper (Metal GPU)
- AppKit + Quartz `CGEventPost` (`CGEventKeyboardSetUnicodeString`) for live keystroke typing
- Electron (Node.js) + HTML5/CSS3 glassmorphic HUD & Dashboard

---

### Task 1: Quartz Native Unicode Typing Engine (`backend/clipboard.py`)

**Files:**
- Modify: `backend/clipboard.py`
- Test: `tests/test_typing.py`

**Step 1: Write the failing test**
Create `tests/test_typing.py` verifying that `type_text(text: str)` handles ASCII and Unicode characters (e.g. quotes, emojis, code punctuation) and respects focus safety.

**Step 2: Run test to observe failure**
```bash
backend/venv/bin/python3 -m unittest tests/test_typing.py
```

**Step 3: Implement `type_text` in `backend/clipboard.py`**
Implement:
```python
def type_text(text: str) -> None:
    """
    Directly type Unicode characters into the frontmost focused application
    using macOS Quartz CGEventKeyboardSetUnicodeString without touching system clipboard.
    """
    if not text:
        return
    for char in text:
        event_down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
        event_up = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
        utf16_units = char.encode('utf-16-le')
        length = len(utf16_units) // 2
        Quartz.CGEventKeyboardSetUnicodeString(event_down, length, utf16_units)
        Quartz.CGEventKeyboardSetUnicodeString(event_up, length, utf16_units)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event_down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event_up)
```

**Step 4: Verify test passes**
```bash
backend/venv/bin/python3 -m unittest tests/test_typing.py
```

**Step 5: Git commit**
```bash
git add backend/clipboard.py tests/test_typing.py
git commit -m "feat: add Quartz unicode direct typing engine in clipboard.py"
```

---

### Task 2: Streaming Audio Segmenter & VAD Chunking (`backend/audio_recorder.py`)

**Files:**
- Modify: `backend/audio_recorder.py`
- Test: `tests/test_streaming_recorder.py`

**Step 1: Write test for streaming chunk emission**
Verify that `AudioRecorder` can accept an async chunk callback:
```python
def on_speech_chunk(audio_chunk: np.ndarray, is_final: bool)
```
and emit speech segments when ~1 second of acoustic energy is detected.

**Step 2: Run test to observe failure**
```bash
backend/venv/bin/python3 -m unittest tests/test_streaming_recorder.py
```

**Step 3: Implement streaming chunk accumulation and emission in `AudioRecorder`**
- In `_process_audio`, maintain a rolling ring buffer of PCM samples.
- Every 16,000 samples (~1.0s) with active voice RMS (`rms >= 0.003`), queue the chunk for transcription.
- On `stop()`, emit the trailing chunk with `is_final=True`.

**Step 4: Verify tests pass**
```bash
backend/venv/bin/python3 -m unittest tests/test_streaming_recorder.py
```

**Step 5: Git commit**
```bash
git add backend/audio_recorder.py tests/test_streaming_recorder.py
git commit -m "feat: implement streaming audio chunking and VAD emission in AudioRecorder"
```

---

### Task 3: Streaming Transcription Manager & Pipeline Integration (`backend/streaming_transcriber.py` & `backend/main.py`)

**Files:**
- Create: `backend/streaming_transcriber.py`
- Modify: `backend/main.py`
- Test: `tests/test_streaming_pipeline.py`

**Step 1: Write test for streaming transcriber**
Verify that incoming audio chunks are transcribed in worker threads, text diffs are calculated, and delivery router directs to `type_text` or accumulates for `paste_text`.

**Step 2: Implement `StreamingTranscriber` in `backend/streaming_transcriber.py`**
- Manages real-time transcription queue.
- Computes new words emitted per chunk.
- Tracks exact execution times (`t_whisper_ms`, `t_llm_ms`, `t_total_ms`).
- In `live_typing` mode: immediately invokes `type_text(new_text)`.
- In `paste_on_finish` mode: buffers text, and upon `finish()` runs optional LLM polish if enabled, then calls `paste_text(cleaned_text)`.

**Step 3: Wire into `backend/main.py`**
- Connect `StreamingTranscriber` to `state.recorder.chunk_callback`.
- Broadcast WebSocket latency updates:
  ```json
  {
    "type": "state",
    "state": "done",
    "text": "...",
    "metrics": {
      "whisper_ms": 115,
      "llm_ms": 135,
      "total_ms": 250,
      "mode": "paste_on_finish"
    }
  }
  ```

**Step 4: Test end-to-end with mock and live audio**
```bash
backend/venv/bin/python3 -m unittest tests/test_streaming_pipeline.py
```

**Step 5: Git commit**
```bash
git add backend/streaming_transcriber.py backend/main.py tests/test_streaming_pipeline.py
git commit -m "feat: integrate concurrent streaming pipeline with real-time text delivery"
```

---

### Task 4: Configuration Persistence & Settings Schema (`backend/config.py`)

**Files:**
- Modify: `backend/config.py`
- Test: `tests/test_config.py`

**Step 1: Add config fields and defaults**
In `DEFAULT_CONFIG`:
```python
"delivery_mode": "paste_on_finish",  # "paste_on_finish" | "live_typing"
```
Ensure `load_config()` preserves and merges `delivery_mode`.

**Step 2: Verify config loading**
```bash
backend/venv/bin/python3 -c "from backend.config import load_config; assert 'delivery_mode' in load_config()"
```

**Step 3: Git commit**
```bash
git add backend/config.py
git commit -m "feat: add delivery_mode to config schema and persistence"
```

---

### Task 5: Floating HUD Live Latency Pill (`src/widget.html`, `src/widget.css`, `src/widget.js`)

**Files:**
- Modify: `src/widget.html`
- Modify: `src/widget.css`
- Modify: `src/widget.js`

**Step 1: Add latency metrics container to `src/widget.html`**
```html
<div class="hud-metrics" id="hudMetrics" style="display: none;">
  <span class="hud-latency-pill" id="hudLatencyPill">⚡ 250ms</span>
  <span class="hud-latency-breakdown" id="hudLatencyBreakdown">(W: 115ms · L: 135ms)</span>
</div>
```

**Step 2: Style HUD pill in `src/widget.css`**
Add glassmorphic styling, micro-badge styling, and smooth fade transitions.

**Step 3: Update `src/widget.js` to render live metrics**
Handle `metrics` object in WebSocket `done` state and display the breakdown for 1.8 seconds before returning to idle.

**Step 4: Git commit**
```bash
git add src/widget.html src/widget.css src/widget.js
git commit -m "feat: render live latency breakdown in floating HUD widget"
```

---

### Task 6: Dashboard Settings UI & History Latency Cards (`src/index.html`, `src/renderer.js`)

**Files:**
- Modify: `src/index.html`
- Modify: `src/renderer.js`

**Step 1: Add Delivery Mode segmented control in `src/index.html`**
```html
<div class="setting-row">
  <div class="setting-label">
    <span>Delivery Mode</span>
    <span class="setting-desc">Choose between zero-delay instant paste or real-time typing</span>
  </div>
  <div class="segmented-control">
    <button class="seg-btn active" data-delivery="paste_on_finish">📋 Paste on Finish</button>
    <button class="seg-btn" data-delivery="live_typing">⌨️ Live Typing</button>
  </div>
</div>
```

**Step 2: Wire events and config sync in `src/renderer.js`**
Handle `delivery_mode` updates, save via IPC `update-config`, and display latency tags on history cards.

**Step 3: Git commit**
```bash
git add src/index.html src/renderer.js
git commit -m "feat: add delivery mode segmented control and history latency badges"
```

---

### Task 7: Full Verification, Documentation & GitHub Sync

**Files:**
- Modify: `README.md`
- Update: `REPO_MAP.md` (`npm run map`)

**Step 1: Run complete test suite**
```bash
backend/venv/bin/python3 -m unittest discover tests/
npm run map
```

**Step 2: Update `README.md` with streaming architecture and latency metrics**

**Step 3: Atomic commit and push to GitHub**
```bash
git add README.md REPO_MAP.md
git commit -m "docs: document streaming dictation pipeline and latency benchmarks"
git push origin main
```
