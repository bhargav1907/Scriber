"""
Scriber — Configuration Management
Stores user preferences in ~/.scriber/config.json
"""

import os
import json
from pathlib import Path

APP_DIR = Path.home() / ".scriber"
CONFIG_FILE = APP_DIR / "config.json"
DB_FILE = APP_DIR / "scriber.db"

DEFAULT_CONFIG = {
    "whisper_model": "large-v3-turbo",
    "llm_cleanup_enabled": True,
    "llm_model": "llama3.2:3b",
    "ollama_host": "http://localhost:11434",
    "auto_paste": True,
    "sound_effects": True,
    "input_device": None,
    "dictation_mode": "auto",  # auto, browser, general, email, code, notes, chat, raw
    "custom_vocabulary": [
        "Scriber", "Bhargav", "Kivi", "Claude", "Anthropic",
        "ChatGPT", "Ollama", "Whisper", "Apple Silicon", "MLX", "GitHub"
    ],
    "word_replacements": {"btw": "by the way", "lgtm": "Looks good to me!"},
    "audio_ducking": False,
    "delivery_mode": "paste_on_finish",  # paste_on_finish, live_typing
}


def load_config() -> dict:
    """Load config from disk, merging with defaults for any missing keys."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(APP_DIR, 0o700)
    except Exception:
        pass

    if CONFIG_FILE.exists():
        try:
            os.chmod(CONFIG_FILE, 0o600)
        except Exception:
            pass
        try:
            with open(CONFIG_FILE) as f:
                config = json.load(f)
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
            # Ensure essential default vocabulary terms exist in custom_vocabulary
            if isinstance(config.get("custom_vocabulary"), list):
                existing_lower = {v.lower().strip() for v in config["custom_vocabulary"] if isinstance(v, str)}
                for term in DEFAULT_CONFIG["custom_vocabulary"]:
                    if term.lower().strip() not in existing_lower:
                        config["custom_vocabulary"].append(term)
            return config
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """Persist config atomically to disk with strict user-only privacy permissions."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    tmp_file = APP_DIR / "config.json.tmp"
    with open(tmp_file, "w") as f:
        json.dump(config, f, indent=2)
    os.replace(tmp_file, CONFIG_FILE)
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except Exception:
        pass

