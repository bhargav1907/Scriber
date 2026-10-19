import unittest
from backend.llm_cleaner import LLMCleaner

class TestLLMCleaner(unittest.TestCase):
    def setUp(self):
        self.cleaner = LLMCleaner()

    def test_phonetic_fixes_claude(self):
        # cloud desktop -> Claude desktop
        text = "I opened the cloud desktop app"
        fixed = self.cleaner._apply_phonetic_fixes(text)
        self.assertIn("Claude desktop app", fixed)

        # ask cloud -> ask Claude
        text2 = "you should ask cloud about it"
        self.assertEqual(self.cleaner._apply_phonetic_fixes(text2), "you should ask Claude about it")

        # cloud wrote -> Claude wrote
        text3 = "cloud wrote the code"
        self.assertEqual(self.cleaner._apply_phonetic_fixes(text3), "Claude wrote the code")

        # frontmost app is Claude
        text4 = "using cloud for typing"
        self.assertEqual(self.cleaner._apply_phonetic_fixes(text4, app_name="Claude"), "using Claude for typing")

    def test_phonetic_fixes_tech_names(self):
        cases = [
            ("commit on get hub", "commit on GitHub"),
            ("runs on mac os", "runs on macOS"),
            ("built with chat gpt", "built with ChatGPT"),
            ("open in v s code", "open in VS Code"),
            ("developed in anti gravity", "developed in Antigravity"),
        ]
        for inp, expected in cases:
            self.assertEqual(self.cleaner._apply_phonetic_fixes(inp), expected)

    def test_custom_vocab_casing(self):
        custom_vocab = ["Scriber", "Bhargav", "Kivi", "Apple Silicon", "MLX"]
        text = "hello bhargav, scriber runs on apple silicon with mlx for kivi"
        normalized = self.cleaner._apply_custom_vocab(text, custom_vocab)
        self.assertIn("Bhargav", normalized)
        self.assertIn("Scriber", normalized)
        self.assertIn("Apple Silicon", normalized)
        self.assertIn("MLX", normalized)
        self.assertIn("Kivi", normalized)

    def test_shorthand_replacements(self):
        replacements = {"btw": "by the way", "lgtm": "Looks good to me!"}
        text = "btw this lgtm"
        expanded = self.cleaner._apply_replacements(text, replacements)
        self.assertEqual(expanded, "by the way this Looks good to me!")

    def test_sanitize_llm_output_preambles(self):
        raw = "I am going to test the app."
        preambles = [
            "Here is the cleaned text:\nI am going to test the app.",
            "Here's the cleaned text: I am going to test the app.",
            "Cleaned text: I am going to test the app.",
            "Sure! I am going to test the app.",
            '"I am going to test the app."',
        ]
        for p in preambles:
            sanitized = self.cleaner._sanitize_llm_output(p, raw)
            self.assertEqual(sanitized, "I am going to test the app.")

    def test_sanitize_llm_output_guards(self):
        raw = "Check the logs."
        # Numbered list echo guard
        list_echo = "1. Clean up text\n2. Remove filler words"
        self.assertEqual(self.cleaner._sanitize_llm_output(list_echo, raw), raw)

        # System instruction guard
        guard_echo = "Here's the cleaned developer text for spoken dictation"
        self.assertEqual(self.cleaner._sanitize_llm_output(guard_echo, raw), raw)

        # Runaway length guard
        exploded = "word " * 50
        self.assertEqual(self.cleaner._sanitize_llm_output(exploded, raw), raw)

if __name__ == "__main__":
    unittest.main()
