import unittest

class TestPackageImports(unittest.TestCase):
    def test_database_import(self):
        from backend.database import init_db, get_stats, save_transcription
        self.assertTrue(callable(init_db))
        self.assertTrue(callable(get_stats))
        self.assertTrue(callable(save_transcription))

    def test_main_import(self):
        from backend.main import app, AppState
        self.assertIsNotNone(app)
        self.assertIsNotNone(AppState)

    def test_all_backend_modules_importable(self):
        import backend.config
        import backend.database
        import backend.audio_recorder
        import backend.transcriber
        import backend.llm_cleaner
        import backend.clipboard
        import backend.context_detector
        import backend.streaming_transcriber
        import backend.main
        self.assertIsNotNone(backend.config)
        self.assertIsNotNone(backend.main)

if __name__ == "__main__":
    unittest.main()
