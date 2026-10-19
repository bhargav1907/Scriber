import unittest
from backend import clipboard

class TestTyping(unittest.TestCase):
    def test_type_empty_string(self):
        # Empty string should safely return False or do nothing without error
        res = clipboard.type_text("")
        self.assertFalse(res)

    def test_type_text_signature(self):
        # type_text should exist and be callable
        self.assertTrue(hasattr(clipboard, "type_text"))
        self.assertTrue(callable(clipboard.type_text))

if __name__ == "__main__":
    unittest.main()
