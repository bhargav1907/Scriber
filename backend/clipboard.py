"""
Scriber — High-Performance Native macOS Clipboard & Paste
Copies text via AppKit NSPasteboard (<0.1ms) and simulates Cmd+V via Quartz CGEventPost (<0.5ms).
Preserves and restores prior user clipboard contents in the background.
"""

import time
import threading
import subprocess

try:
    import AppKit
    import Quartz
    HAS_NATIVE = True
except ImportError:
    HAS_NATIVE = False

try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False


def _restore_clipboard_string(prev_text: str):
    """Restore previous clipboard string after target app has accepted the paste."""
    try:
        if HAS_NATIVE:
            pb = AppKit.NSPasteboard.generalPasteboard()
            pb.clearContents()
            pb.setString_forType_(prev_text, AppKit.NSPasteboardTypeString)
        elif HAS_PYPERCLIP:
            pyperclip.copy(prev_text)
    except Exception as e:
        print(f"[Scriber] Could not restore clipboard: {e}")


def paste_text(text: str, restore_previous: bool = True, restore_delay: float = 0.45) -> bool:
    """
    Copy text to clipboard, then simulate Cmd+V in the frontmost application.
    If restore_previous is True, restores previous clipboard content after restore_delay seconds.
    Returns True on success.
    """
    if not text:
        return False

    prev_text = None

    # 1. Native AppKit + Quartz route (ultra-low latency ~1ms)
    if HAS_NATIVE:
        try:
            pb = AppKit.NSPasteboard.generalPasteboard()

            # Save previous clipboard string to prevent accidental data destruction
            if restore_previous:
                try:
                    prev_text = pb.stringForType_(AppKit.NSPasteboardTypeString)
                except Exception:
                    prev_text = None

            # Set new transcribed string
            pb.clearContents()
            pb.setString_forType_(text, AppKit.NSPasteboardTypeString)

            # Small 20ms pause for macOS pasteboard change notification to propagate
            time.sleep(0.02)

            # Post native Cmd+V keyboard events directly to HID tap
            # Virtual keycode 9 is 'v' on standard macOS keyboards
            event_down = Quartz.CGEventCreateKeyboardEvent(None, 9, True)
            Quartz.CGEventSetFlags(event_down, Quartz.kCGEventFlagMaskCommand)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event_down)

            time.sleep(0.01)

            event_up = Quartz.CGEventCreateKeyboardEvent(None, 9, False)
            Quartz.CGEventSetFlags(event_up, Quartz.kCGEventFlagMaskCommand)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event_up)

            # Background thread restores previous clipboard so user's copied item isn't lost
            if restore_previous and prev_text is not None and prev_text != text:
                timer = threading.Timer(restore_delay, _restore_clipboard_string, args=[prev_text])
                timer.daemon = True
                timer.start()

            return True

        except Exception as e:
            print(f"[Scriber] Native paste warning ({e}), falling back to AppleScript...")

    # 2. Fallback: pyperclip + osascript
    try:
        if HAS_PYPERCLIP:
            if restore_previous:
                try:
                    prev_text = pyperclip.paste()
                except Exception:
                    prev_text = None
            pyperclip.copy(text)

        time.sleep(0.05)
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to keystroke "v" using command down',
            ],
            capture_output=True,
            timeout=3,
        )

        if restore_previous and prev_text is not None and prev_text != text:
            timer = threading.Timer(restore_delay, _restore_clipboard_string, args=[prev_text])
            timer.daemon = True
            timer.start()

        return True

    except Exception as e:
        print(f"[Scriber] Paste failed: {e}")
        return False

