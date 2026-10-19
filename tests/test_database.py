import unittest
import tempfile
import os
from pathlib import Path
from backend.database import (
    init_db,
    save_transcription,
    get_history,
    delete_transcription,
    clear_history,
    get_stats,
)

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_scriber.db"
        init_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_database_creation_and_wal_mode(self):
        self.assertTrue(self.db_path.exists())

    def test_save_and_retrieve_history(self):
        row_id1 = save_transcription("hello world", "Hello world.", 2.5, "large-v3-turbo", db_path=self.db_path)
        row_id2 = save_transcription("testing scriber", "Testing Scriber.", 3.0, "large-v3-turbo", db_path=self.db_path)
        self.assertGreater(row_id2, row_id1)

        history = get_history(limit=10, db_path=self.db_path)
        self.assertEqual(len(history), 2)
        # Most recent first
        self.assertEqual(history[0]["raw_text"], "testing scriber")
        self.assertEqual(history[0]["cleaned_text"], "Testing Scriber.")
        self.assertEqual(history[1]["raw_text"], "hello world")

    def test_history_pagination(self):
        for i in range(15):
            save_transcription(f"raw {i}", f"Clean {i}", 1.0, "turbo", db_path=self.db_path)

        page1 = get_history(limit=10, offset=0, db_path=self.db_path)
        self.assertEqual(len(page1), 10)
        self.assertEqual(page1[0]["raw_text"], "raw 14")

        page2 = get_history(limit=10, offset=10, db_path=self.db_path)
        self.assertEqual(len(page2), 5)
        self.assertEqual(page2[0]["raw_text"], "raw 4")

    def test_delete_transcription(self):
        row_id = save_transcription("to delete", "To delete.", 1.2, "turbo", db_path=self.db_path)
        history = get_history(limit=10, db_path=self.db_path)
        self.assertEqual(len(history), 1)

        delete_transcription(row_id, db_path=self.db_path)
        history_after = get_history(limit=10, db_path=self.db_path)
        self.assertEqual(len(history_after), 0)

    def test_clear_history(self):
        for i in range(5):
            save_transcription(f"raw {i}", f"clean {i}", 1.0, "turbo", db_path=self.db_path)
        self.assertEqual(len(get_history(db_path=self.db_path)), 5)

        clear_history(db_path=self.db_path)
        self.assertEqual(len(get_history(db_path=self.db_path)), 0)

    def test_stats_calculation(self):
        # 10 words in total: "one two three four five" (5) + "six seven eight nine ten" (5)
        save_transcription("raw 1", "one two three four five", 5.0, "turbo", db_path=self.db_path)
        save_transcription("raw 2", "six seven eight nine ten", 10.0, "turbo", db_path=self.db_path)

        stats = get_stats(db_path=self.db_path)
        self.assertEqual(stats["total_transcriptions"], 2)
        self.assertEqual(stats["total_words"], 10)
        self.assertEqual(stats["total_duration_seconds"], 15.0)
        # 10 words * 0.01833 = 0.1833 -> rounded to 0.2
        self.assertAlmostEqual(stats["time_saved_minutes"], 0.2, places=1)

if __name__ == "__main__":
    unittest.main()
