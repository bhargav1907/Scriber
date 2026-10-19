import unittest
import numpy as np
from backend.audio_recorder import AudioRecorder

class TestStreamingRecorder(unittest.TestCase):
    def test_chunk_callback_registration(self):
        rec = AudioRecorder()
        self.assertTrue(hasattr(rec, "chunk_callback"))
        
        received_chunks = []
        def on_chunk(chunk, is_final):
            received_chunks.append((chunk, is_final))
            
        rec.chunk_callback = on_chunk
        self.assertEqual(rec.chunk_callback, on_chunk)

    def test_feed_streaming_audio(self):
        rec = AudioRecorder(sample_rate=16000)
        received = []
        rec.chunk_callback = lambda chunk, is_final: received.append((chunk, is_final))
        
        # Simulate feeding 1.2 seconds of speech (above voice energy threshold)
        samples = (np.sin(np.linspace(0, 100, 16000 + 3200)) * 0.1).astype(np.float32)
        # Feed in blocks of 1024
        rec.recording = True
        for i in range(0, len(samples), 1024):
            block = samples[i:i+1024].reshape(-1, 1)
            rec._audio_callback(block, len(block), None, None)
            
        self.assertGreater(len(received), 0)
        chunk, is_final = received[0]
        self.assertFalse(is_final)
        self.assertGreater(len(chunk), 0)

if __name__ == "__main__":
    unittest.main()
