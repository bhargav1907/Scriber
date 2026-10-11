"""
Scriber — macOS Fn / Globe Key Global Listener
Uses Quartz CGEventTap to capture the hardware Fn key (keycode 63).
"""

import time
import threading
from Quartz import (
    CGEventTapCreate,
    kCGSessionEventTap,
    kCGHeadInsertEventTap,
    kCGEventTapOptionListenOnly,
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
    def __init__(self, on_toggle_callback):
        self.callback = on_toggle_callback
        self.thread = None
        self.run_loop = None
        self.last_press = 0.0
        self.is_running = False

    def start(self):
        self.is_running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        def event_callback(proxy, event_type, event, refcon):
            try:
                keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
                flags = CGEventGetFlags(event)
                if keycode == FN_KEYCODE:
                    is_down = bool(flags & FN_MASK)
                    now = time.time()
                    if is_down and (now - self.last_press > 0.4):
                        self.last_press = now
                        if self.callback:
                            self.callback()
            except Exception as e:
                print(f"[Scriber] Fn key listener error: {e}")
            return event

        tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly,
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
        print("[Scriber] 🌐 Fn key listener active — press Fn key to toggle")
        CFRunLoopRun()

    def stop(self):
        self.is_running = False
        if self.run_loop:
            CFRunLoopStop(self.run_loop)
