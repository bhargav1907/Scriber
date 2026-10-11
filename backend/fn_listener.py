"""
Scriber — macOS Fn / Globe Key Global Listener
Supports both Push-to-Talk (hold Fn like Kivi) and Tap-to-Toggle.
Uses Quartz CGEventTap with active filter to swallow the Fn key event.
"""

import time
import threading
from Quartz import (
    CGEventTapCreate,
    kCGSessionEventTap,
    kCGHeadInsertEventTap,
    kCGEventTapOptionDefault,
    CGEventMaskBit,
    kCGEventFlagsChanged,
    kCGKeyboardEventKeycode,
    CGEventGetIntegerValueField,
    CGEventGetFlags,
    CFMachPortCreateRunLoopSource,
    CFRunLoopGetCurrent,
    CFRunLoopAddSource,
    kCFRunLoopCommonModes,
    CFRunLoopRun,
    CFRunLoopStop,
)

FN_KEYCODE = 63
FN_MASK = 0x800000  # kCGEventFlagMaskSecondaryFn


class FnKeyListener:
    def __init__(self, action_callback):
        """
        action_callback receives an action string: 'start', 'stop', or 'toggle'.
        """
        self.callback = action_callback
        self.thread = None
        self.run_loop = None
        self.press_start = 0.0
        self.is_recording_active = False
        self.is_running = False

    def start(self):
        self.is_running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def notify_state(self, is_recording: bool):
        """Allow backend to synchronize recording state."""
        self.is_recording_active = is_recording

    def _run(self):
        def event_callback(proxy, event_type, event, refcon):
            try:
                keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
                flags = CGEventGetFlags(event)

                if keycode == FN_KEYCODE:
                    is_down = bool(flags & FN_MASK)
                    now = time.time()

                    if is_down:
                        # Fn key pressed DOWN
                        if not self.is_recording_active:
                            # Start recording immediately
                            self.press_start = now
                            self.is_recording_active = True
                            if self.callback:
                                self.callback("start")
                        else:
                            # Already recording from a previous tap -> second tap stops it
                            self.is_recording_active = False
                            self.press_start = 0.0
                            if self.callback:
                                self.callback("stop")
                    else:
                        # Fn key RELEASED
                        if self.is_recording_active and self.press_start > 0:
                            duration = now - self.press_start
                            # If held for 350ms or longer, user was holding to speak (Kivi push-to-talk)
                            if duration >= 0.35:
                                self.is_recording_active = False
                                self.press_start = 0.0
                                if self.callback:
                                    self.callback("stop")
                            else:
                                # Quick tap (< 0.35s): leave recording active (tap-to-toggle mode)
                                pass

                    # Return None to swallow the Fn event so macOS does not pop up the Emoji picker
                    return None

            except Exception as e:
                print(f"[Scriber] Fn key listener error: {e}")
            return event

        tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionDefault,
            CGEventMaskBit(kCGEventFlagsChanged),
            event_callback,
            None,
        )

        if not tap:
            print("[Scriber] ⚠️ Could not create CGEventTap for Fn key. Ensure Accessibility permission is granted.")
            return

        source = CFMachPortCreateRunLoopSource(None, tap, 0)
        self.run_loop = CFRunLoopGetCurrent()
        CFRunLoopAddSource(self.run_loop, source, kCFRunLoopCommonModes)
        print("[Scriber] 🌐 Fn key listener active (Hold to speak like Kivi, or Tap to toggle)")
        CFRunLoopRun()

    def stop(self):
        self.is_running = False
        if self.run_loop:
            CFRunLoopStop(self.run_loop)
