import unittest
import numpy as np
from backend.streaming_transcriber import StreamingTranscriber

class MockTranscriber:
    def transcribe(self, audio_source, custom_vocabulary=None):
        return "hello world"

class MockCleaner:
    async def cleanup(self, raw_text, mode="general", custom_vocabulary=None, word_replacements=None, app_name=None):
        return raw_text.capitalize()
    def normalize_text(self, text, custom_vocabulary=None, word_replacements=None, app_name=None):
        return text

class TestStreamingPipeline(unittest.TestCase):
    def test_streaming_transcriber_initialization(self):
        st = StreamingTranscriber(
            transcriber=MockTranscriber(),
            cleaner=MockCleaner(),
            delivery_mode="paste_on_finish",
        )
        self.assertEqual(st.delivery_mode, "paste_on_finish")
        self.assertEqual(st.get_accumulated_text(), "")

    def test_streaming_delta_calculation(self):
        st = StreamingTranscriber(
            transcriber=MockTranscriber(),
            cleaner=MockCleaner(),
            delivery_mode="live_typing",
        )
        delta = st._calculate_delta("hello", "hello world")
        self.assertEqual(delta, " world")

if __name__ == "__main__":
    unittest.main()
