"""
Scriber — Whisper Transcription Engine
Uses Apple Silicon MLX (Metal GPU) for ultra-fast sub-second transcription on Mac,
with graceful fallback to faster-whisper (CTranslate2).
"""

import os
import re
import wave
import threading
import numpy as np

try:
    import mlx_whisper
    HAS_MLX = True
except ImportError:
    HAS_MLX = False

try:
    from faster_whisper import WhisperModel
    HAS_FASTER_WHISPER = True
except ImportError:
    HAS_FASTER_WHISPER = False


# Map friendly model size names to MLX Hugging Face repos
MLX_MODEL_MAP = {
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "large-v3": "mlx-community/whisper-large-v3-turbo",
    "base": "mlx-community/whisper-base",
    "small": "mlx-community/whisper-small",
    "medium": "mlx-community/whisper-medium",
    "tiny": "mlx-community/whisper-tiny",
}


class Transcriber:
    def __init__(self, model_size: str = "large-v3-turbo"):
        self.model_size = model_size
        self.model: WhisperModel | None = None
        self._lock = threading.Lock()
        self._loading = False
        self._use_mlx = False
        self.cpu_threads = max(4, min(8, (os.cpu_count() or 6)))

    @property
    def is_ready(self) -> bool:
        return (self._use_mlx or self.model is not None) and not self._loading

    def load_model(self, model_size: str | None = None) -> bool:
        """
        Load and pre-warm the Whisper model in unified memory.
        Prioritizes Apple Silicon Metal GPU via MLX.
        """
        if model_size:
            self.model_size = model_size

        self._loading = True
        try:
            with self._lock:
                # 1. Try Apple Silicon MLX GPU
                if HAS_MLX and self.model_size in MLX_MODEL_MAP:
                    repo = MLX_MODEL_MAP[self.model_size]
                    print(f"[Scriber] ⚡ Pre-warming Apple Silicon Metal GPU Whisper: '{repo}' ...")
                    # Run a warm-up dummy pass on silence so model weights reside in Metal GPU memory
                    dummy_pcm = np.zeros(16000, dtype=np.float32)
                    mlx_whisper.transcribe(
                        dummy_pcm,
                        path_or_hf_repo=repo,
                        language="en",
                        temperature=0.0,
                        condition_on_previous_text=False,
                        word_timestamps=False,
                        fp16=True,
                    )
                    self._use_mlx = True
                    print(f"[Scriber] ✓ Metal GPU Whisper model '{self.model_size}' pre-warmed & ready in unified memory!")
                    return True

                # 2. Fallback to faster-whisper CPU
                if HAS_FASTER_WHISPER:
                    print(f"[Scriber] ⚡ Loading faster-whisper CPU model: '{self.model_size}' (int8, threads={self.cpu_threads}) ...")
                    self.model = WhisperModel(
                        self.model_size,
                        device="auto",
                        compute_type="int8",
                        cpu_threads=self.cpu_threads,
                    )
                    self._use_mlx = False
                    print(f"[Scriber] ✓ faster-whisper model '{self.model_size}' loaded successfully.")
                    return True

            return False
        except Exception as e:
            print(f"[Scriber] Failed to load Whisper model: {e}")
            # Try CPU fallback if MLX failed
            if HAS_FASTER_WHISPER and self.model is None:
                try:
                    self.model = WhisperModel(self.model_size, device="auto", compute_type="int8", cpu_threads=self.cpu_threads)
                    self._use_mlx = False
                    return True
                except Exception:
                    pass
            return False
        finally:
            self._loading = False

    def transcribe(self, audio_path: str) -> str:
        """
        Transcribe an audio file to text using Metal GPU or greedy CPU search.
        Transcribes strictly the spoken acoustic signal without prompt hallucination.
        """
        if not self.is_ready:
            self.load_model()

        with self._lock:
            # 1. Apple Silicon MLX Metal GPU path (~0.4 - 0.7s)
            if self._use_mlx and self.model_size in MLX_MODEL_MAP:
                repo = MLX_MODEL_MAP[self.model_size]
                try:
                    # Read PCM directly with Python wave (no external ffmpeg binary needed)
                    with wave.open(audio_path, "rb") as wf:
                        frames = wf.readframes(wf.getnframes())
                        audio_np = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

                    res = mlx_whisper.transcribe(
                        audio_np,
                        path_or_hf_repo=repo,
                        language="en",
                        temperature=0.0,
                        condition_on_previous_text=False,
                        word_timestamps=False,
                        fp16=True,
                    )
                    raw = res.get("text", "").strip()
                    # Strip any repetitive hallucination loops (e.g. "word, word, word...")
                    cleaned = re.sub(r"(\b\w+\b)(?:[,\s]+\1\b){2,}", r"\1", raw, flags=re.IGNORECASE)
                    return cleaned.strip()
                except Exception as e:
                    print(f"[Scriber] MLX transcription warning ({e}), falling back to CPU...")

            # 2. faster-whisper CPU fallback
            if self.model:
                segments, _ = self.model.transcribe(
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
                raw = " ".join(seg.text.strip() for seg in segments).strip()
                cleaned = re.sub(r"(\b\w+\b)(?:[,\s]+\1\b){2,}", r"\1", raw, flags=re.IGNORECASE)
                return cleaned.strip()

        return ""
