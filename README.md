# 🎤 Scriber

**Next-generation local voice-to-text for macOS** — engineered for Apple Silicon with sub-second Metal GPU transcription, smart context awareness, and zero telemetry.

Everything runs 100% locally on your Mac. No cloud, no subscriptions, no audio or text ever leaves your machine.

---

## ⚡ Highlights

- **⚡ Apple Silicon Metal GPU (~0.6s)**: Uses Apple MLX Metal GPU unified memory (`whisper-large-v3-turbo`) for instant transcription.
- **✨ Smart Context Detection**: Auto-detects whether you're typing in **VS Code**, **Terminal**, **Slack**, **Mail**, or **Notion**, and tailors tone, code formatting, and structure accordingly.
- **🎯 Custom Vocabulary**: Define personal names, company brands, and technical terms to bias Whisper's acoustic decoding and LLM capitalization.
- **⏩ Shorthand Replacements**: Instant expansion of triggers (e.g., `btw` → `by the way`, `lgtm` → `Looks good to me!`).
- **🎧 Dynamic Mic Switching**: Automatically shifts input whenever your Bluetooth headphones (AirPods, Bose, etc.) connect or disconnect.
- **🔇 Audio Ducking**: Optionally lowers system music/video volume while recording to eliminate speaker bleed.
- **⌨️ Hardware `Fn` Key Integration**: Intercepts the physical `Fn` key via Quartz HID tap while suppressing the macOS emoji picker popup.
- **💊 Floating Waveform Widget**: Draggable, glassmorphic HUD with active app badge, 7-bar audio reactor, and speed metrics.
- **📊 Live Dashboard**: Real-time stats ribbon (Dictations, Words, Time Saved), instant search filter, and 1-click clipboard copy.

---

## Quick Start

```bash
# 1. Setup (one-time)
./scripts/setup.sh

# 2. Launch
./scripts/start.sh
# or: npm start
```

---

## How It Works

1. **Press `Fn`** (or `Option + Space`) → Scriber detects the active app and begins listening with a reactive audio HUD.
2. **Speak naturally** — dictate code, emails, messages, or stream-of-consciousness thoughts.
3. **Press `Fn` again** → Scriber transcribes on Metal GPU, cleans up speech stumbles with local LLM, and auto-pastes into your cursor in ~1 second.

---

## Tech Stack

| Component | Technology | Performance |
|---|---|---|
| Speech-to-Text | [MLX Whisper](https://github.com/ml-explore/mlx-examples) (`whisper-large-v3-turbo`) | ~0.6s on Metal GPU |
| STT Fallback | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2) | CPU optimized int8 |
| Context Cleanup | [Ollama](https://ollama.com) (`llama3.2:3b`) | ~0.35s local prompt formatting |
| macOS Integration | PyObjC / AppKit NSWorkspace & Quartz HID | Hardware Fn key & active window detection |
| Backend | Python 3.10+ FastAPI + WebSockets | Sub-millisecond IPC |
| Frontend | Electron + Vanilla JS & CSS | Frameless glassmorphic HUD |

---

## Dictation Modes

| Mode | Target Apps | Formatting Behavior |
|---|---|---|
| **Auto** | Any | Automatically selects mode based on the active window |
| **Code** | VS Code, Cursor, Xcode, Terminal, Warp, Ghostty | camelCase, snake_case, backticks, concise commit messages |
| **Email** | Mail, Outlook, Superhuman, Spark | Polished business paragraphs, clean salutations and sign-offs |
| **Notes** | Notion, Obsidian, Bear, Notes | Structured bullet points, clean markdown outlines |
| **Chat** | Slack, Discord, Messages, WhatsApp | Punchy, casual conversational style |
| **Raw** | Any | Pure Whisper output directly, bypassing LLM cleanup |

---

## Requirements

- macOS 13+ on Apple Silicon (M1/M2/M3/M4)
- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com/download) with `llama3.2:3b` (`ollama run llama3.2:3b`)

---

## macOS Permissions

- **Microphone**: Allow access when prompted on first launch.
- **Accessibility & Input Monitoring**: To allow hardware `Fn` key capture and auto-pasting (`Cmd+V`):
  - **System Settings** → **Privacy & Security** → **Accessibility** → Enable **Terminal** (or **Scriber**).
  - **System Settings** → **Privacy & Security** → **Input Monitoring** → Enable **Terminal** (or **Scriber**).

---

## License

MIT
