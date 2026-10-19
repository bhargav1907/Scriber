import unittest
from backend.context_detector import (
    BUNDLE_ID_MAP,
    APP_CATEGORIES,
    APP_ICONS,
    get_frontmost_app,
)

class TestContextDetector(unittest.TestCase):
    def test_bundle_id_mappings(self):
        # IDEs / Code
        self.assertEqual(BUNDLE_ID_MAP["com.google.antigravity-ide"], ("Antigravity", "code", "💻"))
        self.assertEqual(BUNDLE_ID_MAP["com.microsoft.VSCode"], ("VS Code", "code", "💻"))

        # Browsers
        self.assertEqual(BUNDLE_ID_MAP["com.brave.Browser"], ("Brave", "browser", "🌐"))
        self.assertEqual(BUNDLE_ID_MAP["com.apple.Safari"], ("Safari", "browser", "🌐"))

        # AI
        self.assertEqual(BUNDLE_ID_MAP["com.anthropic.claudefordesktop"], ("Claude", "chat", "🤖"))

        # Email
        self.assertEqual(BUNDLE_ID_MAP["com.apple.mail"], ("Mail", "email", "✉️"))

    def test_get_frontmost_app_execution(self):
        # Must return valid app dict without raising exception
        app_info = get_frontmost_app()
        self.assertIsInstance(app_info, dict)
        self.assertIn("name", app_info)
        self.assertIn("category", app_info)
        self.assertIn("icon", app_info)

if __name__ == "__main__":
    unittest.main()
