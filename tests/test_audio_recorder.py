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

    def test_process_audio_resampling(self):
        rec = AudioRecorder(sample_rate=16000)
        # Simulate recording at 48000 Hz for 1 second (48000 samples)
        rec.active_sample_rate = 48000
        rec.audio_chunks = [np.ones((48000, 1), dtype=np.float32) * 0.5]

        audio_np, filepath = rec._process_audio()
        self.assertIsNotNone(audio_np)
        # Should be resampled to 16000 samples
        self.assertEqual(len(audio_np), 16000)

    def test_device_query(self):
        devices = AudioRecorder.get_input_devices()
        self.assertIsInstance(devices, dict)
        self.assertIn("devices", devices)
        self.assertIn("default_name", devices)

if __name__ == "__main__":
    unittest.main()
