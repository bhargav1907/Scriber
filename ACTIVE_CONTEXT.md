# 🧠 Active Working Context & Memory Ledger (`ACTIVE_CONTEXT.md`)

> **Agent Directive**: This document is the single source of truth for the active task state, recent decisions, and technical invariants. 
> To minimize input context bloat, read this file (~400 tokens) instead of re-reading or crawling extensive past conversation transcripts.

---

## 📌 Current Focus & Active Task
- **Goal**: Implement and test the bounded active memory ledger pattern to eliminate conversation context bloat.
- **Current Status**: Active memory ledger initialized and wired into `AGENTS.md` and `GEMINI.md`.
- **Next Step**: Validate agent adherence across turns and measure prompt token savings.

---

## 🛠️ Architecture Decisions & Recent Invariants (Hardened)
1. **Clipboard & Native Paste ([`backend/clipboard.py`](file:///Users/bhargavsinguluri/Documents/Scriber/backend/clipboard.py))**:
   - **Single Event Tap**: Posts `Cmd+V` strictly to `kCGAnnotatedSessionEventTap`. Never multicast to `kCGHIDEventTap` (multicasting causes double-paste).
   - **Event Timing**: 50ms pasteboard sync delay, 40ms key-down hold time to guarantee Electron/Chromium event loops register the keypress.
   - **Clipboard Fallback**: `restore_previous` defaults to `False`. Transcriptions stay in `NSPasteboard` so users can manually `Cmd+V` if a target app drops focus.
   - **Whitespace Guard**: `paste_text` strips whitespace and immediately rejects empty/blank strings without touching pasteboard.
2. **Focus Management ([`main.js`](file:///Users/bhargavsinguluri/Documents/Scriber/main.js))**:
   - Removed `widgetWindow.moveTop()` from widget state updates to prevent WindowServer from blurring active target windows during paste.
3. **Alternative Speech Engine Option ([`backend/transcriber.py`](file:///Users/bhargavsinguluri/Documents/Scriber/backend/transcriber.py))**:
   - Integrated Cactus Whistle (`whistle.cact`, 16.9 MB) as an selectable lightweight CPU engine profile alongside default Apple Silicon MLX Large-v3-Turbo.
4. **Automated Testing Suite ([`tests/test_clipboard.py`](file:///Users/bhargavsinguluri/Documents/Scriber/tests/test_clipboard.py))**:
   - Tests real macOS `NSPasteboard` read/write directly via AppKit.
   - Spies on `CGEventPost` to assert exactly 2 calls (1 down, 1 up) targeted exclusively at `kCGAnnotatedSessionEventTap`. Total test suite: 35 passing tests.

---

## 📋 Task Checklist
- [x] Eliminate clipboard restore race conditions & double-paste bug.
- [x] Add automated unit tests for `backend/clipboard.py`.
- [x] Design industry-standard bounded memory pattern (`ACTIVE_CONTEXT.md`).
- [ ] Wire `ACTIVE_CONTEXT.md` into `AGENTS.md` and `GEMINI.md`.
- [ ] Validate prompt context reduction in subsequent user turns.
