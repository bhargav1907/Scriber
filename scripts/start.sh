#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
# Scriber — Launch Script
# Starts Ollama (if needed), then launches the Electron app
# (which in turn spawns the Python backend).
# ──────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🎤 Starting Scriber…"

# Start Ollama if not running
if ! pgrep -x "ollama" > /dev/null 2>&1; then
  echo "  ▸ Starting Ollama service…"
  ollama serve &> /dev/null &
  sleep 2
  echo "  ✓ Ollama started"
fi

# Launch Electron app (it spawns the Python backend automatically)
cd "$PROJECT_DIR"
npx electron .
