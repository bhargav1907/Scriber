import unittest
import asyncio
import numpy as np
from backend.streaming_transcriber import StreamingTranscriber

class MockTranscriber:
    def __init__(self, output="hello world"):
        self.output = output

    def transcribe(self, audio_source, custom_vocabulary=None):
        return self.output

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

    def test_streaming_delta_calculation(self):
        st = StreamingTranscriber(
            transcriber=MockTranscriber(),
            cleaner=MockCleaner(),
            delivery_mode="live_typing",
        )
        delta = st._calculate_delta("hello", "hello world")
        self.assertEqual(delta, " world")

    def test_silence_detection(self):
        st = StreamingTranscriber(
            transcriber=MockTranscriber("Thank you."),
            cleaner=MockCleaner(),
        )
        self.assertTrue(st._is_silence_or_hallucination("Thank you."))
        self.assertTrue(st._is_silence_or_hallucination("[music]"))
        self.assertFalse(st._is_silence_or_hallucination("Testing the dictation pipeline"))

    def test_finalize_execution(self):
        st = StreamingTranscriber(
            transcriber=MockTranscriber("scriber test"),
            cleaner=MockCleaner(),
            delivery_mode="paste_on_finish",
            llm_enabled=False,
        )
        audio = np.zeros(16000, dtype=np.float32)
        result = asyncio.run(st.finalize(audio, auto_paste=False))
        self.assertEqual(result["raw_text"], "scriber test")
        self.assertEqual(result["cleaned_text"], "scriber test")
        self.assertGreaterEqual(result["whisper_ms"], 0)

if __name__ == "__main__":
    unittest.main()
