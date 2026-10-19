import unittest
import numpy as np
from backend.audio_recorder import AudioRecorder

class TestAudioRecorder(unittest.TestCase):
    def test_recorder_initialization(self):
        rec = AudioRecorder(sample_rate=16000)
        self.assertEqual(rec.sample_rate, 16000)
        self.assertFalse(rec.recording)
        self.assertEqual(len(rec.audio_chunks), 0)

    def test_audio_callback_level_and_accumulation(self):
        rec = AudioRecorder(sample_rate=16000)
        levels = []
        rec.level_callback = lambda lvl: levels.append(lvl)
        rec.recording = True

        # Simulate incoming audio block
        block = (np.sin(np.linspace(0, 10, 1024)) * 0.1).astype(np.float32).reshape(-1, 1)
        rec._audio_callback(block, 1024, None, None)

        self.assertEqual(len(rec.audio_chunks), 1)
        self.assertGreater(len(levels), 0)
        self.assertGreater(levels[0], 0.0)

if __name__ == "__main__":
    unittest.main()
