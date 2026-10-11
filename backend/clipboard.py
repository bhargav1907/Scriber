"""
Scriber — Clipboard & Paste
Copies text to the macOS clipboard and simulates Cmd+V to paste into the active app.
"""

import subprocess
import time
import pyperclip


def paste_text(text: str) -> bool:
    """
    Copy text to clipboard, then simulate Cmd+V in the frontmost application.
    Returns True on success.
    """
    try:
        pyperclip.copy(text)
        time.sleep(0.05)  # Let the clipboard settle

        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to keystroke "v" using command down',
            ],
            capture_output=True,
            timeout=5,
        )
        return True

    except Exception as e:
        print(f"[Scriber] Paste failed: {e}")
        return False
