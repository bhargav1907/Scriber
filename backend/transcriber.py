"""
Scriber — Whisper Transcription Engine
Uses faster-whisper (CTranslate2) for fast local speech-to-text.
"""

import threading
from faster_whisper import WhisperModel


class Transcriber:
    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self.model: WhisperModel | None = None
        self._lock = threading.Lock()
        self._loading = False

    @property
    def is_ready(self) -> bool:
        return self.model is not None and not self._loading

    def load_model(self, model_size: str | None = None) -> bool:
        """
        Load (or reload) the Whisper model.
        First run will download the model (~150 MB for base, ~1 GB for large-v3-turbo).
        """
        if model_size:
            self.model_size = model_size

        self._loading = True
        try:
            with self._lock:
                print(f"[Scriber] Loading Whisper model: {self.model_size} ...")
                self.model = WhisperModel(
                    self.model_size,
                    device="auto",
                    compute_type="auto",
                )
                print(f"[Scriber] Whisper model '{self.model_size}' loaded successfully.")
            return True
        except Exception as e:
            print(f"[Scriber] Failed to load Whisper model: {e}")
            return False
        finally:
            self._loading = False

    def transcribe(self, audio_path: str) -> str:
        """
        Transcribe an audio file to text.
        Returns the raw transcription string.
        """
        if not self.model:
            self.load_model()

        with self._lock:
            segments, info = self.model.transcribe(
                audio_path,
                language="en",
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                    speech_pad_ms=200,
                ),
            )
            text = " ".join(seg.text.strip() for seg in segments)

        return text.strip()
