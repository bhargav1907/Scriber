"""
Scriber — Configuration Management
Stores user preferences in ~/.scriber/config.json
"""

import json
from pathlib import Path

APP_DIR = Path.home() / ".scriber"
CONFIG_FILE = APP_DIR / "config.json"
DB_FILE = APP_DIR / "scriber.db"

DEFAULT_CONFIG = {
    "whisper_model": "base",
    "llm_cleanup_enabled": True,
    "llm_model": "llama3.2:3b",
    "ollama_host": "http://localhost:11434",
    "auto_paste": True,
    "sound_effects": True,
    "input_device": None,
}


def load_config() -> dict:
    """Load config from disk, merging with defaults for any missing keys."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                config = json.load(f)
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
            return config
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """Persist config to disk."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
