# Comprehensive Codebase Refactoring & Full-Feature Validation Plan

> **For Claude:** Use `/Users/bhargavsinguluri/.gemini/config/skills/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Refactor the Scriber codebase to eliminate architectural redundancies and fragile import coupling, implement defense-in-depth validation across all layers, and provide a 100% comprehensive automated test suite verifying every backend component, API endpoint, and UI integration.

**Architecture:** 
1. Apply **Simplification Cascades** to unify imports, remove dead chunk-streaming stubs, and streamline the dictation orchestration pipeline.
2. Apply **Defense-in-Depth** to harden entry points, database access, config boundaries, and WebSocket state machines against invalid data and unhandled exceptions.
3. Build a comprehensive unit and integration test suite covering audio processing, context detection, database queries, phonetic normalization, pipeline latency profiling, and FastAPI endpoints.

**Tech Stack:** Python 3.11, FastAPI, Uvicorn, MLX Whisper, Ollama, SoundDevice, Quartz / AppKit (PyObjC), SQLite3 (WAL), Electron, Vanilla JS (HIG).

---

### Task 1: Package Import & Module Resolution Hardening (Defense-in-Depth)

**Files:**
- Modify: `backend/database.py:1-25`
- Modify: `backend/main.py:1-40`
- Test: `tests/test_package_imports.py`

**Step 1: Write the failing test**
Create `tests/test_package_imports.py` verifying that all backend modules can be imported directly and as packages (`backend.*`) without `ModuleNotFoundError: No module named 'config'`.

```python
import unittest

class TestPackageImports(unittest.TestCase):
    def test_database_import(self):
        from backend.database import init_db, get_stats, save_transcription
        self.assertTrue(callable(init_db))

    def test_main_import(self):
        from backend.main import app, AppState
        self.assertIsNotNone(app)
        self.assertIsNotNone(AppState)
```

**Step 2: Run test to verify it fails**
Run: `PYTHONPATH=. backend/venv/bin/python3 -m unittest tests/test_package_imports.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'config'`

**Step 3: Implement minimal fix in `backend/database.py` and `backend/main.py`**
Wrap all local module imports with try-except fallback (`from backend.X import ...` / `from X import ...`).

**Step 4: Run test to verify it passes**
Run: `PYTHONPATH=. backend/venv/bin/python3 -m unittest tests/test_package_imports.py`
Expected: PASS

**Step 5: Commit**
```bash
git add backend/database.py backend/main.py tests/test_package_imports.py
git commit -m "refactor: harden package imports across database and main modules"
```

---

### Task 2: Streamline Dictation Pipeline & Remove Dead Chunk Stubs (Simplification Cascades)

**Files:**
- Modify: `backend/streaming_transcriber.py:1-140`
- Modify: `backend/main.py:200-280`
- Test: `tests/test_streaming_pipeline.py`

**Step 1: Write test verifying pipeline orchestration and latency output**
Verify `finalize` runs full-waveform transcription, runs anti-hallucination checks, and outputs exact `whisper_ms`, `llm_ms`, `total_ms` without dead callback hooks.

**Step 2: Clean up dead methods in `backend/streaming_transcriber.py` and duplicate anti-hallucination checks in `backend/main.py`**
Remove no-op stubs (`on_chunk`, `get_accumulated_text`, `_calculate_delta`) and simplify `StreamingTranscriber` (or alias as `DictationPipeline`) to cleanly handle end-to-end processing.

**Step 3: Run tests to verify they pass**
Run: `PYTHONPATH=. backend/venv/bin/python3 -m unittest tests/test_streaming_pipeline.py`
Expected: PASS

**Step 4: Commit**
```bash
git add backend/streaming_transcriber.py backend/main.py tests/test_streaming_pipeline.py
git commit -m "refactor: simplify dictation pipeline and eliminate duplicate guard checks"
```

---

### Task 3: Comprehensive Database & Aggregation Testing

**Files:**
- Modify: `backend/database.py` (if any edge cases discovered)
- Test: `tests/test_database.py`

**Step 1: Write tests for all database operations**
- Database initialization and table creation with WAL mode
- Saving transcriptions and verifying returned row IDs
- History retrieval with limit and pagination offset
- SQL aggregation in `get_stats()` (verifying word counts, total duration, time saved math)
- Row deletion by ID
- Clearing history

**Step 2: Run test suite**
Run: `PYTHONPATH=. backend/venv/bin/python3 -m unittest tests/test_database.py`
Expected: PASS

**Step 3: Commit**
```bash
git add tests/test_database.py
git commit -m "test: add comprehensive test suite for database and SQL statistics"
```

---

### Task 4: Comprehensive Phonetic Homophone & Context Cleaning Testing

**Files:**
- Modify: `backend/llm_cleaner.py` (if regex holes discovered)
- Test: `tests/test_llm_cleaner.py`

**Step 1: Write tests for all phonetic and text cleaning rules**
- "Cloud" -> "Claude" when followed by "desktop", "code", "ai", "model", etc.
- App-context specific conversion ("cloud" -> "Claude" when `app_name="Claude"`)
- Tech homophone fixes: "get hub" -> "GitHub", "mac os" -> "macOS", "v s code" -> "VS Code", "anti gravity" -> "Antigravity"
- Custom vocabulary exact casing preservation
- Shorthand word replacements (`btw` -> `by the way`, `lgtm` -> `Looks good to me!`)
- Sanitization filters: instruction lists, prompt guard words, and conversational preambles

**Step 2: Run test suite**
Run: `PYTHONPATH=. backend/venv/bin/python3 -m unittest tests/test_llm_cleaner.py`
Expected: PASS

**Step 3: Commit**
```bash
git add tests/test_llm_cleaner.py
git commit -m "test: add comprehensive tests for phonetic repair and text sanitization"
```

---

### Task 5: FastAPI REST Endpoints & WebSocket API Verification

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_api_endpoints.py`

**Step 1: Write tests using FastAPI TestClient**
- `GET /api/health` returns status, whisper_ready, ollama_connected, audio_devices, stats
- `GET /api/stats` returns accurate stats payload
- `GET /api/history` returns history list with pagination
- `DELETE /api/history/{id}` deletes specific row
- `DELETE /api/history` clears history
- `GET /api/config` returns full configuration
- `POST /api/config` updates configuration and persists to disk
- `GET /api/devices` returns device list and default device

**Step 2: Run test suite**
Run: `PYTHONPATH=. backend/venv/bin/python3 -m unittest tests/test_api_endpoints.py`
Expected: PASS

**Step 3: Commit**
```bash
git add tests/test_api_endpoints.py
git commit -m "test: add full API endpoint test suite using FastAPI TestClient"
```

---

### Task 6: Context Detector & Audio Recorder Unit Testing

**Files:**
- Modify: `backend/context_detector.py`
- Test: `tests/test_context_detector.py`
- Modify: `tests/test_streaming_recorder.py` -> rename/expand to `tests/test_audio_recorder.py`

**Step 1: Write tests for bundle ID resolution and audio buffer resampling**
- Reverse-DNS bundle ID mapping (`com.microsoft.VSCode` -> Code mode, `com.brave.Browser` -> Browser mode, etc.)
- Audio buffer linear interpolation resampling (e.g. 48kHz / 44.1kHz -> 16kHz)
- RMS level calculation and silence thresholding

**Step 2: Run test suite**
Run: `PYTHONPATH=. backend/venv/bin/python3 -m unittest tests/test_context_detector.py tests/test_audio_recorder.py`
Expected: PASS

**Step 3: Commit**
```bash
git add tests/test_context_detector.py tests/test_audio_recorder.py
git commit -m "test: add context detector and audio recorder unit tests"
```

---

### Task 7: UI Copy & Setting Descriptions Synchronization

**Files:**
- Modify: `src/renderer.js`
- Modify: `src/index.html` (if any stale text)
- Test: Verification via visual inspection & code review

**Step 1: Update delivery mode description in `src/renderer.js`**
Update descriptions from legacy "streaming background transcription (<150ms delay)" to "Full-attention Metal GPU transcription with instant paste (<0.5ms)" and "Direct Quartz Unicode keystrokes into focused window".

**Step 2: Commit**
```bash
git add src/renderer.js
git commit -m "ui: update settings descriptions to reflect full-waveform Whisper and Quartz typing"
```

---

### Task 8: Whole-Project Verification & REPO_MAP.md Synchronization

**Files:**
- Update: `REPO_MAP.md` via `npm run map`
- Run: `PYTHONPATH=. backend/venv/bin/python3 -m unittest discover tests/`
- Test live backend health endpoint via `curl`

**Step 1: Run complete test suite**
Run: `PYTHONPATH=. backend/venv/bin/python3 -m unittest discover tests/`
Expected: ALL TESTS PASS with 0 failures

**Step 2: Regenerate architecture map**
Run: `npm run map`

**Step 3: Commit and Push**
```bash
git add .
git commit -m "chore: complete whole-codebase refactoring, verification, and map synchronization"
git push origin main
```
