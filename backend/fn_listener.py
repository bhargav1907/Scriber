"""
Scriber — macOS Fn / Globe Key Global Listener
Uses Quartz CGEventTap at kCGHIDEventTap to capture and swallow the hardware Fn key (keycode 63).
Intercepts key events before WindowServer processes them, preventing the emoji picker.
Tapping Fn toggles recording: Tap Fn to record -> Tap Fn to paste.
"""

import time
import threading
from Quartz import (
    CGEventTapCreate,
    kCGHIDEventTap,
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
    kCGEventTapDisabledByTimeout,
    kCGEventTapDisabledByUserInput,
    CGEventTapEnable,
)

FN_KEYCODE = 63
FN_MASK = 0x800000  # kCGEventFlagMaskSecondaryFn


class FnKeyListener:
    def __init__(self, toggle_callback):
        self.callback = toggle_callback
        self.thread = None
        self.run_loop = None
        self.last_press = 0.0
        self.is_running = False
        self._tap = None

    def start(self):
        self.is_running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        def event_callback(proxy, event_type, event, refcon):
            # Auto-recover tap if disabled by macOS sleep or system timeout
            if event_type in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
                if self._tap:
                    CGEventTapEnable(self._tap, True)
                return event

            try:
                keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
                if keycode == FN_KEYCODE:
                    flags = CGEventGetFlags(event)
                    is_down = bool(flags & FN_MASK)
                    now = time.time()

                    # Trigger toggle on press down with debounce
                    if is_down and (now - self.last_press > 0.35):
                        self.last_press = now
                        if self.callback:
                            self.callback()

                    # Return None for both press and release to swallow the Fn key at HID level
                    # so macOS WindowServer never receives the event and never triggers the Emoji picker!
                    return None

            except Exception as e:
                print(f"[Scriber] Fn key listener error: {e}")
            return event

        self._tap = CGEventTapCreate(
            kCGHIDEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionDefault,
            CGEventMaskBit(kCGEventFlagsChanged),
            event_callback,
            None,
        )

        if not self._tap:
            print("[Scriber] ⚠️ Could not create HID CGEventTap for Fn key. Ensure Accessibility permission is granted.")
            return

        source = CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self.run_loop = CFRunLoopGetCurrent()
        CFRunLoopAddSource(self.run_loop, source, kCFRunLoopCommonModes)
        print("[Scriber] 🌐 Fn key listener active (Tap Fn to record → Tap Fn to paste)")
        CFRunLoopRun()

    def stop(self):
        self.is_running = False
        if self._tap:
            CGEventTapEnable(self._tap, False)
            self._tap = None
        if self.run_loop:
            CFRunLoopStop(self.run_loop)

