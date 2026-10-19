# 🎤 Scriber

**Next-generation local voice-to-text for macOS** — engineered for Apple Silicon with sub-second Metal GPU transcription, smart context awareness, native macOS Human Interface Guidelines (HIG) design, and zero telemetry.

Everything runs **100% locally on your Mac**. No cloud APIs, no subscriptions, and no audio or text ever leaves your machine.

---

## ⚡ Highlights

- **⚡ Apple Silicon Metal GPU (~0.6s)**: Uses Apple MLX Metal GPU unified memory (`whisper-large-v3-turbo`) with zero-disk in-memory audio buffers for instant transcription.
- **✨ In-Process App Context Detection (<1ms)**: Leverages `NSWorkspace` and reverse-DNS bundle IDs (`com.microsoft.VSCode`, `com.google.antigravity-ide`, `com.brave.Browser`, `com.apple.mail`) to automatically tailor formatting, code styling, and tone for the active app.
- **📋 Sub-Millisecond Native Paste & Clipboard Preservation**: Injects text in <0.5ms via native AppKit `NSPasteboard` and Quartz `CGEventPost` (`Cmd+V`), while automatically saving and restoring your prior copied clipboard content in the background.
- **⌨️ Physical `Fn` Key Integration**: Intercepts the hardware `Fn` key via a low-level Quartz `kCGHIDEventTap` (keycode 63) while suppressing the macOS emoji picker, featuring automatic recovery when waking your Mac from sleep.
- **🔒 Apple-Grade Security & Privacy**: Strict localhost CORS isolation, atomic file persistence, Content Security Policy (CSP), and user-only POSIX permissions (`0700`/`0600`) ensure your speech history is completely protected.
- **🎯 Custom Vocabulary & Phonetic Normalization**: Dual-stage acoustic decoder priming (`initial_prompt`) and context-aware phonetic homophone repair eliminate speech recognition mishearings for proper nouns, developer tools, and AI models (Claude, ChatGPT, Ollama, PyTorch, etc.).
- **⏩ Shorthand Replacements**: Instant expansion of triggers (e.g., `btw` → `by the way`, `lgtm` → `Looks good to me!`).
- **🎧 Dynamic CoreAudio Mic Switching**: Automatically shifts input whenever your Bluetooth headphones (AirPods, Bose, etc.) connect or disconnect.
- **🔇 Audio Ducking**: Optionally lowers system music and video volume while speaking to eliminate speaker bleed.
- **💊 Floating Waveform HUD**: Fluid glassmorphic Dynamic Island pill with live app context badge, 7-bar audio reactive visualizer, and sub-second execution metrics.
- **📊 Native macOS Dashboard**: Designed following Apple HIG with segmented controls, live stats ribbon, instant keyword search, and 1-click clipboard copy.

---

## 🏗️ Architecture & Data Flow

```
[ Microphone Audio ] 
        │
        ▼ (sounddevice 16kHz PCM stream)
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

---

## ⌨️ Shortcuts & Controls

| Shortcut | Scope | Action |
|---|---|---|
| <kbd>Fn</kbd> *(Tap)* | Global (Any App) | Start recording → Tap again to polish & paste |
| <kbd>⌥</kbd> <kbd>Space</kbd> | Global (Any App) | Secondary global dictation toggle hotkey |
| <kbd>⌘</kbd> <kbd>1</kbd> | Dashboard | Switch to **History** view |
| <kbd>⌘</kbd> <kbd>,</kbd> or <kbd>⌘</kbd> <kbd>2</kbd> | Dashboard | Open **Preferences** |
| <kbd>⌘</kbd> <kbd>R</kbd> | Dashboard | Refresh transcription history & stats |
| <kbd>Esc</kbd> | Dashboard | Clear search filter or exit preferences back to history |

---

## 🎯 Context-Aware Dictation Modes

Scriber dynamically identifies the frontmost application using in-process `NSWorkspace` bundle identifiers:

| Mode | Target Applications | Formatting Behavior |
|---|---|---|
| **Auto** | Any | Automatically selects the optimal mode based on the active window |
| **Code** | VS Code, Cursor, Xcode, Terminal, Warp, Ghostty, Antigravity | Formats variable names into camelCase/snake_case/backticks; generates concise commit messages |
| **Email** | Mail, Outlook, Superhuman, Spark | Polished business paragraphs, clean salutations and sign-offs |
| **Notes** | Notion, Obsidian, Bear, Apple Notes, Pages | Structured bullet points and clean markdown outlines |
| **Chat** | Slack, Discord, Messages, WhatsApp, Teams | Punchy, casual conversational style |
| **Browser** | Safari, Chrome, Brave, Arc, Firefox, Edge | Direct search queries, natural form inputs, and preserved URLs |
| **Raw** | Any | Pure Whisper acoustic decoding, bypassing LLM cleanup |

---

## 🚀 Quick Start

### Prerequisites
- macOS 13+ on Apple Silicon (M1/M2/M3/M4)
- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com/download) running `llama3.2:3b` (`ollama run llama3.2:3b`)

### 1. Installation
```bash
# Clone the repository
git clone https://github.com/bhargav1907/Scriber.git
cd Scriber

# One-time automated setup (creates virtualenv, installs MLX Metal Whisper & dependencies)
./scripts/setup.sh
```

### 2. Launching Scriber
```bash
./scripts/start.sh
# or: npm start
```

---

## 🛡️ Security & Privacy Architecture

- **100% On-Device Processing**: Transcription runs on the Metal GPU in unified memory. Text cleanup runs via a local Ollama instance on `127.0.0.1:11434`. No external API requests are ever made.
- **Localhost Network Isolation**: FastAPI backend CORS is restricted strictly to local origins (`127.0.0.1`, `localhost`, and Electron renderers). Remote browser pages cannot access your dictation history.
- **POSIX Permission Hardening**: User data (`~/.scriber/`) is restricted to mode `0700` and database/config files to `0600`.
- **SQLite Write-Ahead Logging (WAL)**: Database operations use WAL mode with resilient busy timeouts, ensuring concurrent non-blocking access with zero risk of database locks.
- **Single-Instance Protection**: Electron enforces a single-instance lock to prevent port collisions and duplicate hardware event listeners.

---

## ⚙️ macOS Permissions Setup

On first launch, macOS requires two permissions for Scriber to operate globally:
1. **Microphone**: Allow access when prompted to enable audio capture.
2. **Accessibility & Input Monitoring**: Required to swallow the physical `Fn` key and simulate paste into your active cursor:
   - Open **System Settings** → **Privacy & Security** → **Accessibility** → Enable **Terminal** (or **Scriber**).
   - Open **System Settings** → **Privacy & Security** → **Input Monitoring** → Enable **Terminal** (or **Scriber**).

---

## 📄 License

MIT © Bhargav Singuluri
