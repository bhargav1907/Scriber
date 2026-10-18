# 🤖 AI Agent Guidelines for Scriber (`AGENTS.md`)

This repository is optimized for autonomous AI coding agents (Claude Code, Cursor, Windsurf, ChatGPT, Hermes, Antigravity, Aider, etc.). 
Follow these guidelines to minimize token usage and maximize navigation speed and accuracy.

---

## 🗺️ 1. Macro Navigation: Use `REPO_MAP.md` First

**Do NOT blindly crawl or grep the codebase.**
- An auto-generated, token-compact architectural map of all classes, methods, signatures, IPC bridges, and WebSocket endpoints is maintained in [`REPO_MAP.md`](file:///Users/bhargavsinguluri/Documents/Scriber/REPO_MAP.md).
- **First Step**: Always inspect `REPO_MAP.md` to identify exact file locations, function names, and structural relationships in **~1,600 tokens** instead of ingesting full source files.
- **Maintenance**: Whenever you add, rename, or delete functions, routes, or IPC events, run:
  ```bash
  npm run map
  ```
  *(or `python3 scripts/generate_repo_map.py`)* to keep the architectural map synchronized.

---

## 🔬 2. Micro Navigation: Use LSP Over Text Search

If the environment has an active Language Server Protocol (LSP) tool or MCP server (`code-lsp` / `agent-lsp`):
- Use `go_to_definition` and `find_references` for precise symbol resolution instead of loose grep matches.
- Use `inspect_symbol` for type signatures and docstrings.
- Use compiler diagnostics to catch type or syntax errors in memory before finalizing edits.

---

## 🏗️ 3. Architecture & Data Flow

```
[ Microphone Audio ] 
        │
        ▼ (sounddevice PCM stream)
[ AudioRecorder (backend/audio_recorder.py) ]
        │
        ▼ (in-memory float32 numpy array — zero disk round-trip)
[ Transcriber (backend/transcriber.py) ] ──▶ Apple Silicon Metal GPU (mlx-whisper large-v3-turbo, ~0.6s)
        │
        ▼ (raw acoustic transcript)
[ LLMCleaner (backend/llm_cleaner.py) ] ──▶ Ollama /api/chat (persistent keep-alive connection reuse)
        │
        ▼ (polished text)
[ Clipboard (backend/clipboard.py) ] ────▶ Native AppKit & Quartz CGEventPost Cmd+V (<0.5ms) + restore
        │
        ▼ (WebSocket status & level events)
[ Electron Main (main.js) ] ──────────────▶ IPC bridge (preload.js) ──▶ Renderers (src/widget.js & src/renderer.js)
```

### Key Technical Invariants
1. **Physical `Fn` Key Swallowing & Auto-Recovery**:
   - Managed in [`backend/fn_listener.py`](file:///Users/bhargavsinguluri/Documents/Scriber/backend/fn_listener.py) using a Quartz `kCGHIDEventTap` intercepting keycode 63.
   - Must swallow the event (`return None`) to prevent the macOS emoji picker popup.
   - Automatically recovers on sleep/wake timeouts via `kCGEventTapDisabledByTimeout` re-enabling.
2. **Context-Aware App Detection**:
   - Managed in [`backend/context_detector.py`](file:///Users/bhargavsinguluri/Documents/Scriber/backend/context_detector.py) using in-process `NSWorkspace` (<1ms) and reverse-DNS **Bundle Identifiers** (`com.brave.Browser`, `com.google.antigravity-ide`, `com.microsoft.VSCode`, etc.).
   - Distinguishes Scriber's own Electron process from external Electron apps (like Antigravity IDE or VS Code).
3. **Silence Hallucination Guards**:
   - Managed in [`backend/transcriber.py`](file:///Users/bhargavsinguluri/Documents/Scriber/backend/transcriber.py) with RMS acoustic energy gate (`rms < 0.003`) and silence phrase filter (`"Thank you."`, `"[Music]"`).
4. **Dynamic Audio Device Monitoring**:
   - Background watcher in [`backend/main.py`](file:///Users/bhargavsinguluri/Documents/Scriber/backend/main.py) polls CoreAudio every 5 seconds to switch default input on AirPods / Bluetooth connection.

---

## 🚀 4. Useful Commands

```bash
# Start Scriber (spawns Python FastAPI backend on :58932 + Electron HUD)
npm start

# Regenerate the architectural repo map (<50ms)
npm run map

# Test Python backend health
curl -s http://127.0.0.1:58932/api/health

# Run test or check venv packages
backend/venv/bin/python3 -c "import mlx_whisper; print('MLX ready')"
```

---

## 📝 5. Development Conventions
- **No telemetry, 100% local**: No cloud APIs, no analytics, no external tracking.
- **Git commits**: Always commit clean, descriptive atomic changes with conventional commit prefixes (`feat:`, `fix:`, `refactor:`, `docs:`).
- **Keep `README.md` Synchronized**: Whenever a significant feature, optimization, architecture upgrade, or security change is introduced, inspect [`README.md`](./README.md) and update it to clearly showcase the new capability, metrics, shortcuts, and architecture.

