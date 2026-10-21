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

# Known Whisper hallucinations triggered by silence, breath, or background noise
SILENCE_HALLUCINATIONS = {
    "thank you.", "thank you", "thanks for watching.", "thanks for watching!",
    "thank you very much.", "thank you very much", "thanks.", "thanks",
    "you", "bye.", "bye", "goodbye.", "goodbye",
    "please subscribe.", "subscribe", "[music]", "[applause]", "[silence]",
    "(music)", "(applause)", "(silence)", "[blank_audio]", "thank you for watching.",
    "thank you for watching", "so, thank you.", "so, thank you", "thank you so much.",
    "thank you so much", "thanks for listening.", "thanks for listening!",
    # Sound effect and reaction hallucinations
    "scream!", "scream", "screaming", "screams", "[scream]", "[screaming]",
    "gasp", "gasps", "[gasp]", "sigh", "sighs", "[sigh]",
    "groan", "groans", "yawn", "cough", "coughs", "[cough]",
    "laughter", "laughing", "[laughter]", "chuckle", "applause",
    "[applause]", "cheering", "[cheering]", "music",
    # Subtitle artifact hallucinations
    "subtitles by", "subtitles", "subtitles by the amara.org community",
    "translated by", "closed captioning",
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

    def _build_initial_prompt(self, custom_vocabulary: list[str] | None = None) -> str | None:
        """
        Build an acoustic decoder conditioning prompt for Whisper.
        Biases Whisper's token priors towards domain terms and proper nouns
        (e.g., 'Claude', 'Anthropic', 'ChatGPT', 'Ollama', 'Whisper') without hallucinating.
        """
        base_terms = ["Claude", "Anthropic", "ChatGPT", "Ollama", "Whisper", "Apple Silicon", "MLX", "GitHub"]
        terms = list(base_terms)
        if custom_vocabulary:
            for v in custom_vocabulary:
                if isinstance(v, str) and v.strip() and v.strip() not in terms:
                    terms.append(v.strip())
        prompt_str = ", ".join(terms[:25])
        return f"Vocabulary: {prompt_str}."

    def transcribe(self, audio_source: str | np.ndarray, custom_vocabulary: list[str] | None = None) -> str:
        """
        Transcribe an in-memory numpy float32 array or audio WAV file path to text
        using Apple Silicon Metal GPU (MLX) or greedy CPU search.
        Conditioned on custom vocabulary to recognize proper nouns accurately.
        """
        if not self.is_ready:
            self.load_model()

        with self._lock:
            # 1. Resolve audio source to float32 numpy array
            if isinstance(audio_source, np.ndarray):
                audio_np = audio_source.astype(np.float32)
            elif isinstance(audio_source, str):
                try:
                    with wave.open(audio_source, "rb") as wf:
                        frames = wf.readframes(wf.getnframes())
                        audio_np = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                except Exception as e:
                    print(f"[Scriber] Could not read audio file '{audio_source}': {e}")
                    return ""
            else:
                return ""

            if audio_np.size == 0:
                return ""

            # Energy gate: check if audio is near-silence / ambient floor
            max_amp = float(np.max(np.abs(audio_np)))
            rms = float(np.sqrt(np.mean(audio_np ** 2)))
            if max_amp < 0.015 or rms < 0.0035:
                print(f"[Scriber] 🔇 Audio signal below voice threshold (max_amp={max_amp:.4f}, rms={rms:.4f}), skipping.")
                return ""

            # Frame-based Voice Activity Detection (50ms frames = 800 samples at 16kHz)
            # Rejects long ambient recordings that only contain isolated mouse clicks or room rustle
            frame_len = 800
            num_frames = len(audio_np) // frame_len
            if num_frames > 0:
                frames = audio_np[:num_frames * frame_len].reshape(num_frames, frame_len)
                frame_rms = np.sqrt(np.mean(frames ** 2, axis=1))
                active_speech_frames = int(np.sum(frame_rms > 0.007))
                active_ratio = active_speech_frames / num_frames
                if active_speech_frames < 6 or (num_frames > 20 and active_ratio < 0.06):
                    print(f"[Scriber] 🔇 Insufficient sustained voice activity (active_frames={active_speech_frames}, ratio={active_ratio:.3f}), skipping.")
                    return ""

            initial_prompt = self._build_initial_prompt(custom_vocabulary)

            # 2. Apple Silicon MLX Metal GPU path (~0.4 - 0.7s)
            if self._use_mlx and self.model_size in MLX_MODEL_MAP:
                repo = MLX_MODEL_MAP[self.model_size]
                try:
                    res = mlx_whisper.transcribe(
                        audio_np,
                        path_or_hf_repo=repo,
                        language="en",
                        temperature=0.0,
                        condition_on_previous_text=False,
                        initial_prompt=initial_prompt,
                        word_timestamps=False,
                        fp16=True,
                    )
                    raw = res.get("text", "").strip()

                    # Strip any accidental prompt prefix echo
                    if raw.lower().startswith("vocabulary:"):
                        raw = raw[11:].strip()
                    elif raw.lower().startswith("vocabulary,"):
                        raw = raw[11:].strip()

                    # Reject if output contains no alphanumeric characters (e.g. "!", "...", ".", "?", etc.)
                    if not re.search(r"[a-zA-Z0-9]", raw):
                        if raw:
                            print(f"[Scriber] ⚠️ Discarded non-speech punctuation artifact: '{raw}'")
                        return ""

                    # Filter out silence hallucinations (e.g. "Thank you.", "Scream!", "Thanks for watching!")
                    norm_raw = raw.lower().strip(" .,!?:;\t\n\r")
                    if not norm_raw or norm_raw in SILENCE_HALLUCINATIONS or raw.lower().strip() in SILENCE_HALLUCINATIONS:
                        print(f"[Scriber] ⚠️ Discarded silence hallucination: '{raw}'")
                        return ""

                    # Strip any repetitive hallucination loops (e.g. "word, word, word...")
                    cleaned = re.sub(r"(\b\w+\b)(?:[,\s]+\1\b){2,}", r"\1", raw, flags=re.IGNORECASE).strip()
                    if not re.search(r"[a-zA-Z0-9]", cleaned):
                        return ""
                    norm_cleaned = cleaned.lower().strip(" .,!?:;\t\n\r")
                    if not norm_cleaned or norm_cleaned in SILENCE_HALLUCINATIONS or cleaned.lower().strip() in SILENCE_HALLUCINATIONS:
                        print(f"[Scriber] ⚠️ Discarded silence hallucination: '{cleaned}'")
                        return ""

                    return cleaned
                except Exception as e:
                    print(f"[Scriber] MLX transcription warning ({e}), falling back to CPU...")

            # 3. faster-whisper CPU fallback
            if self.model:
                segments, _ = self.model.transcribe(
                    audio_np,
                    language="en",
                    beam_size=1,
                    best_of=1,
                    temperature=0.0,
                    condition_on_previous_text=False,
                    initial_prompt=initial_prompt,
                    without_timestamps=True,
                    vad_filter=True,
                    vad_parameters=dict(
                        min_silence_duration_ms=400,
                        speech_pad_ms=150,
                    ),
                )
                raw = " ".join(seg.text.strip() for seg in segments).strip()
                if raw.lower().startswith("vocabulary:"):
                    raw = raw[11:].strip()
                elif raw.lower().startswith("vocabulary,"):
                    raw = raw[11:].strip()
                if not re.search(r"[a-zA-Z0-9]", raw):
                    return ""
                norm_raw = raw.lower().strip(" .,!?:;\t\n\r")
                if not norm_raw or norm_raw in SILENCE_HALLUCINATIONS or raw.lower().strip() in SILENCE_HALLUCINATIONS:
                    return ""
                cleaned = re.sub(r"(\b\w+\b)(?:[,\s]+\1\b){2,}", r"\1", raw, flags=re.IGNORECASE).strip()
                if not re.search(r"[a-zA-Z0-9]", cleaned):
                    return ""
                norm_cleaned = cleaned.lower().strip(" .,!?:;\t\n\r")
                if not norm_cleaned or norm_cleaned in SILENCE_HALLUCINATIONS or cleaned.lower().strip() in SILENCE_HALLUCINATIONS:
                    return ""
                return cleaned

        return ""
