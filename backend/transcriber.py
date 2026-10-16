"""
Scriber — Whisper Transcription Engine
Uses faster-whisper (CTranslate2) with optimized greedy decoding for fast local speech-to-text.
"""

import os
import threading
from faster_whisper import WhisperModel


class Transcriber:
    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self.model: WhisperModel | None = None
        self._lock = threading.Lock()
        self._loading = False
        # Allocate available CPU cores on Apple Silicon (e.g. 8 threads on a 10-core chip)
        self.cpu_threads = max(4, min(8, (os.cpu_count() or 6)))

    @property
    def is_ready(self) -> bool:
        return self.model is not None and not self._loading

    def load_model(self, model_size: str | None = None) -> bool:
        """
        Load (or reload) the Whisper model.
        Uses int8 quantization for high throughput and reduced memory bandwidth.
        """
        if model_size:
            self.model_size = model_size

        self._loading = True
        try:
            with self._lock:
                print(f"[Scriber] ⚡ Loading Whisper model: '{self.model_size}' (int8, threads={self.cpu_threads}) ...")
                self.model = WhisperModel(
                    self.model_size,
                    device="auto",
                    compute_type="int8",
                    cpu_threads=self.cpu_threads,
                )
                print(f"[Scriber] ✓ Whisper model '{self.model_size}' loaded successfully.")
            return True
        except Exception as e:
            print(f"[Scriber] Failed to load Whisper model: {e}")
            return False
        finally:
            self._loading = False

    def transcribe(self, audio_path: str) -> str:
        """
        Transcribe an audio file to text using ultra-fast greedy decoding:
        - beam_size=1, best_of=1 (greedy search: 3-5x faster than beam search with identical accuracy)
        - without_timestamps=True (skips computing timestamp tokens)
        - condition_on_previous_text=False (no prompt caching overhead)
        - temperature=0.0 (deterministic, fast single-pass decoding)
        - vad_filter=True (trims non-speech silence)
        """
        if not self.model:
            self.load_model()

        with self._lock:
            segments, info = self.model.transcribe(
                audio_path,
                language="en",
                beam_size=1,
                best_of=1,
                temperature=0.0,
                condition_on_previous_text=False,
                without_timestamps=True,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=400,
                    speech_pad_ms=150,
                ),
            )
            text = " ".join(seg.text.strip() for seg in segments)

        return text.strip()
