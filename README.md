# 🎤 Scriber

**Local voice-to-text for macOS** — like Kivi & Wispr Flow, but fully private.

Everything runs on your Mac. No cloud, no subscription, no data leaves your machine.

## Quick Start

```bash
# 1. Setup (one-time)
./scripts/setup.sh

# 2. Launch
./scripts/start.sh
# or: npm start
```

## How It Works

1. **Press `F5`** → Scriber starts listening (floating widget appears with 🔴 pulsing dot)
2. **Speak naturally** as long as you want
3. **Press `F5` again** → Scriber transcribes + cleans up your speech
4. **Polished text** is pasted into whatever app is focused (~1 second)

## Features

- 🎙️ **High-quality transcription** via Whisper (runs locally on Apple Silicon)
- 🧠 **AI text cleanup** via Ollama — removes fillers, fixes punctuation
- 📋 **Auto-paste** into any app
- 💊 **Floating indicator widget** — always know what Scriber is doing
- 📜 **Transcription history** — browse, copy, or delete past entries
- ⚙️ **Configurable** — change model size, toggle cleanup, customize behavior
- 🌙 **Beautiful dark UI** — glassmorphism, animations, premium design
- 🔒 **100% local & private** — zero internet required

## Tech Stack

| Component | Technology |
|---|---|
| Speech-to-Text | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2) |
| Text Cleanup | [Ollama](https://ollama.com) + Llama 3.2 (3B) |
| Backend | Python FastAPI + WebSocket |
| Frontend | Electron |
| Audio | sounddevice (PortAudio) |

## Requirements

- macOS with Apple Silicon (M1/M2/M3/M4)
- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com/download)
- 16 GB RAM recommended

## macOS Permissions

- **Microphone**: macOS will prompt for microphone access on first recording. Click "Allow".
- **Accessibility (Auto-Paste)**: To allow Scriber to automatically paste text (`Cmd+V`) into active apps, grant Accessibility permissions:
  - System Settings → Privacy & Security → Accessibility → Enable your terminal or Electron/Scriber.
  - *Even without Accessibility permission, your cleaned text is always copied to your clipboard immediately.*

## Settings

Open the main window (click tray icon) → click ⚙️:

- **Whisper Model**: tiny / base / small / medium / large-v3-turbo / large-v3
- **AI Cleanup**: toggle on/off
- **Auto Paste**: toggle on/off
- **LLM Model**: change the Ollama model
- **Ollama Host**: custom Ollama endpoint

## License

MIT
