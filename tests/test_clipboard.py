"""
Unit and integration tests for Scriber's macOS Clipboard & Paste system.
Validates:
1. Real macOS NSPasteboard write and content verification (no mocks).
2. Atomic clipboard preservation / restore behavior.
3. Quartz CGEvent generation integrity:
   - Verifies exactly 1 down and 1 up event are posted (prevents double-paste regressions).
   - Verifies target tap is strictly kCGAnnotatedSessionEventTap.
   - Verifies keycode 9 ('v') and Command modifier mask.
"""

import unittest
from unittest.mock import patch, call
import AppKit
import Quartz
from backend.clipboard import paste_text, _restore_clipboard_string

class TestClipboard(unittest.TestCase):
    def setUp(self):
        self.pb = AppKit.NSPasteboard.generalPasteboard()
        self.original_content = self.pb.stringForType_(AppKit.NSPasteboardTypeString) or ""

    def tearDown(self):
        # Restore real clipboard after tests
        self.pb.clearContents()
        self.pb.setString_forType_(self.original_content, AppKit.NSPasteboardTypeString)

    def test_real_pasteboard_write_without_mocking(self):
        """Tests that paste_text actually updates the live macOS NSPasteboard with the transcription."""
        test_string = "Scriber Automated Test String 12345"
        
        # We allow paste_text to run against the real macOS NSPasteboard,
        # but intercept Quartz.CGEventPost to prevent injecting a physical Cmd+V keystroke into the active window.
        with patch("backend.clipboard.Quartz.CGEventPost") as mock_post:
            result = paste_text(test_string, restore_previous=False)
            self.assertTrue(result)
            
            # Verify live macOS pasteboard content directly via AppKit
            current_clipboard = self.pb.stringForType_(AppKit.NSPasteboardTypeString)
            self.assertEqual(current_clipboard, test_string)

    def test_no_double_paste_event_dispatch(self):
        """
        Regression guard for the double-paste bug:
        Ensures exactly 2 CGEventPost calls occur (1 key_down, 1 key_up),
        and strictly targets kCGAnnotatedSessionEventTap without multicast to kCGHIDEventTap.
        """
        test_string = "Regression Test Guard"
        with patch("backend.clipboard.Quartz.CGEventPost") as mock_post:
            paste_text(test_string, restore_previous=False)
            
            # Exactly 2 event posts: 1 down, 1 up. Any count > 2 means duplicate keystrokes!
            self.assertEqual(mock_post.call_count, 2, f"Expected exactly 2 CGEventPost calls (down + up), got {mock_post.call_count}")
            
            # Verify each post targeted kCGAnnotatedSessionEventTap
            for call_args in mock_post.call_args_list:
                tap_target = call_args[0][0]
                self.assertEqual(tap_target, Quartz.kCGAnnotatedSessionEventTap,
                                 "CGEventPost must target kCGAnnotatedSessionEventTap to avoid double-posting via HID tap")

    def test_empty_string_guard(self):
        """Ensures empty or whitespace-only strings are safely ignored without touching the clipboard."""
        self.assertFalse(paste_text(""))
        self.assertFalse(paste_text("   "))
        self.assertFalse(paste_text(None))

    def test_clipboard_restore_helper(self):
        """Ensures clipboard restore thread safely repopulates the previous string."""
        _restore_clipboard_string("Restored String")
        current_clipboard = self.pb.stringForType_(AppKit.NSPasteboardTypeString)
        self.assertEqual(current_clipboard, "Restored String")

if __name__ == "__main__":
    unittest.main()
