#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
# Scriber — One-Click Setup
# Installs all dependencies for both the Python backend and Electron frontend.
# ──────────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/backend"

echo ""
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║          🎤 Scriber — Setup               ║"
echo "  ║    Local Voice-to-Text for macOS           ║"
echo "  ╚═══════════════════════════════════════════╝"
echo ""

# ── 1. Check prerequisites ────────────────────────────────────────────

echo "▸ Checking prerequisites…"

if ! command -v python3 &> /dev/null; then
  echo "  ✗ Python 3 not found. Install via: brew install python3"
  exit 1
fi
echo "  ✓ Python: $(python3 --version)"

if ! command -v node &> /dev/null; then
  echo "  ✗ Node.js not found. Install via: brew install node"
  exit 1
fi
echo "  ✓ Node.js: $(node --version)"

if ! command -v ollama &> /dev/null; then
  echo "  ✗ Ollama not found."
  echo "    Install from: https://ollama.com/download"
  echo "    Or: brew install ollama"
  exit 1
fi
echo "  ✓ Ollama: found"
echo ""

# ── 2. Python virtual environment ─────────────────────────────────────

echo "▸ Setting up Python virtual environment…"
if [ ! -d "$BACKEND_DIR/venv" ]; then
  python3 -m venv "$BACKEND_DIR/venv"
  echo "  ✓ Created venv at backend/venv/"
else
  echo "  ✓ Venv already exists"
fi

# Activate and install deps
source "$BACKEND_DIR/venv/bin/activate"
echo "  ▸ Installing Python dependencies…"
pip install --upgrade pip -q
pip install -r "$BACKEND_DIR/requirements.txt" -q
echo "  ✓ Python dependencies installed"
echo ""

# ── 3. Node.js dependencies ──────────────────────────────────────────

echo "▸ Installing Node.js dependencies…"
cd "$PROJECT_DIR"
npm install --no-fund --no-audit 2>&1 | tail -1
echo "  ✓ Node dependencies installed"
echo ""

# ── 4. Ollama model ──────────────────────────────────────────────────

echo "▸ Setting up Ollama LLM model…"

# Start Ollama if not running
if ! pgrep -x "ollama" > /dev/null 2>&1; then
  echo "  ▸ Starting Ollama service…"
  ollama serve &> /dev/null &
  sleep 3
fi

# Pull the cleanup model
echo "  ▸ Pulling llama3.2:3b (this may take a few minutes on first run)…"
ollama pull llama3.2:3b 2>&1 | tail -3
echo "  ✓ Ollama model ready"
echo ""

# ── 5. Pre-download Whisper model ────────────────────────────────────

echo "▸ Pre-downloading Whisper model (base)…"
"$BACKEND_DIR/venv/bin/python3" -c "
from faster_whisper import WhisperModel
print('  ▸ Downloading Whisper base model…')
model = WhisperModel('base', device='auto', compute_type='auto')
print('  ✓ Whisper model ready')
" 2>&1 | grep -E "✓|▸|Downloading"
echo ""

# ── 6. Done ──────────────────────────────────────────────────────────

echo "  ╔═══════════════════════════════════════════╗"
echo "  ║          ✅ Setup Complete!                ║"
echo "  ║                                           ║"
echo "  ║  Run Scriber:                             ║"
echo "  ║    ./scripts/start.sh                     ║"
echo "  ║                                           ║"
echo "  ║  Or:                                      ║"
echo "  ║    npm start                              ║"
echo "  ║                                           ║"
echo "  ║  Hotkey: Fn or Option + Space             ║"
echo "  ╚═══════════════════════════════════════════╝"
echo ""
