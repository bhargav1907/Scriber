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

try:
    from needle.agent.whistle import Whistle as CactusWhistle
    HAS_CACTUS_WHISTLE = True
except ImportError:
    HAS_CACTUS_WHISTLE = False


# Map friendly model size names to MLX Hugging Face repos
MLX_MODEL_MAP = {
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "large-v3": "mlx-community/whisper-large-v3-turbo",
    "distil-large-v3": "mlx-community/distil-whisper-large-v3",
    "whisper-distil-large-v3": "mlx-community/distil-whisper-large-v3",
    "medium": "mlx-community/whisper-medium",
    "small": "mlx-community/whisper-small",
    "base": "mlx-community/whisper-base",
    "tiny": "mlx-community/whisper-tiny",
}

# Comprehensive compiled regex patterns targeting Whisper silence/noise hallucinations
# (closed caption credits, YouTube outros, subtitle scrapers, sound effect tags, web domains)
HALLUCINATION_PATTERNS = [
    # Subtitle / Closed Captioning / Transcriber credits
    re.compile(r"(?i)\b(closed\s+caption(s|ing)?|subtitles?|captions?|transcrib(ed|ing|er)?)\b"),
    # Isolated web domains (e.g. Brandhagen.com, amara.org)
    re.compile(r"(?i)^\s*([a-zA-Z0-9_-]+\s+){0,2}[a-zA-Z0-9_-]+\.(com|org|net|io|tv|cc|fm|gg)\s*[.!]?\s*$"),
    # Outros & YouTube artifact phrases
    re.compile(r"(?i)\b(thank\s+you\s+for\s+watching|thanks\s+for\s+watching|thank\s+you\s+for\s+listening|thanks\s+for\s+listening|please\s+subscribe|like\s+and\s+subscribe|see\s+you\s+(in\s+the\s+)?next\s+(video|time)|all\s+rights\s+reserved|copyright)\b"),
    # Isolated gratitude or greetings when they make up the whole phrase
    re.compile(r"(?i)^\s*(thank\s+you(\s+(very|so)\s+much)?|thanks|you|bye|goodbye|welcome)\s*[.!]?\s*$"),
    # Reaction / Sound effect hallucinations
    re.compile(r"(?i)^\s*(\[|\()? *(music|applause|silence|blank_audio|laughter|cheering|scream|screaming|gasp|sigh|cough|groan|yawn) *(\]|\))? *[!.]?\s*$"),
    re.compile(r"(?i)^\s*(scream|screaming|gasp|sigh|laughter|laughing|chuckle|applause|music)\s*[!.]?\s*$"),
    # Isolated prompt prefix / vocabulary echo
    re.compile(r"(?i)^\s*vocabulary\s*[:.,]?\s*$"),
]


def is_hallucination(text: str, custom_vocabulary: list[str] | None = None) -> bool:
    """
    Multi-layer defense against Whisper hallucinations during silence, noise, or pauses:
    1. Rejects empty or purely non-alphanumeric punctuation output.
    2. Matches closed-caption credits, URLs, YouTube outros, and sound effect artifacts via regex.
    3. Detects prompt prefix echoes.
    """
    if not text or not text.strip():
        return True

    stripped = text.strip()

    # Reject non-alphanumeric punctuation (e.g. "!", "...", ".", "?", etc.)
    if not re.search(r"[a-zA-Z0-9]", stripped):
        return True

    # Check compiled regex patterns
    for p in HALLUCINATION_PATTERNS:
        if p.search(stripped):
            return True

    # Check custom vocabulary prompt echoing
    if custom_vocabulary:
        words = [w.strip().lower() for w in re.split(r'[,.\s:;]+', stripped) if w.strip()]
        vocab_set = {w.strip().lower() for v in custom_vocabulary for w in v.split()} | {"vocabulary"}
        if words == ["vocabulary"]:
            return True
        if words and all(w in vocab_set for w in words) and len(set(words)) >= max(2, len(vocab_set) * 0.5):
            return True

    return False


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
                # 0. Cactus Whistle (Ultra-lightweight ~16.9MB CPU engine)
                if self.model_size == "cactus-whistle":
                    if HAS_CACTUS_WHISTLE:
                        print("[Scriber] ⚡ Loading Cactus Whistle engine (~16.9 MB) ...")
                        self.model = CactusWhistle()
                        self._use_mlx = False
                        print("[Scriber] ✓ Cactus Whistle engine ready!")
                        return True
                    else:
                        print("[Scriber] Cactus Whistle not installed, falling back to MLX Whisper...")

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
                        no_speech_threshold=0.45,
                        compression_ratio_threshold=2.2,
                        fp16=True,
                    )
                    raw = res.get("text", "").strip()

                    # Strip any accidental prompt prefix echo
                    if raw.lower().startswith("vocabulary:"):
                        raw = raw[11:].strip()
                    elif raw.lower().startswith("vocabulary,"):
                        raw = raw[11:].strip()

                    # Comprehensive anti-hallucination check
                    if is_hallucination(raw, custom_vocabulary):
                        if raw:
                            print(f"[Scriber] ⚠️ Discarded silence/noise hallucination: '{raw}'")
                        return ""

                    # Strip any repetitive hallucination loops (e.g. "word, word, word...")
                    cleaned = re.sub(r"(\b\w+\b)(?:[,\s]+\1\b){2,}", r"\1", raw, flags=re.IGNORECASE).strip()
                    if is_hallucination(cleaned, custom_vocabulary):
                        if cleaned:
                            print(f"[Scriber] ⚠️ Discarded silence/noise hallucination: '{cleaned}'")
                        return ""

                    return cleaned
                except Exception as e:
                    print(f"[Scriber] MLX transcription warning ({e}), falling back to CPU...")

            # 3. Cactus Whistle CPU inference
            if HAS_CACTUS_WHISTLE and isinstance(self.model, CactusWhistle):
                try:
                    res = self.model.transcribe(audio_np)
                    raw = (res.get("text") or "").strip()
                    if is_hallucination(raw, custom_vocabulary):
                        return ""
                    return raw
                except Exception as e:
                    print(f"[Scriber] Cactus Whistle transcription warning ({e})")
                    return ""

            # 4. faster-whisper CPU fallback
            if self.model and hasattr(self.model, "transcribe"):
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
                if is_hallucination(raw, custom_vocabulary):
                    return ""
                cleaned = re.sub(r"(\b\w+\b)(?:[,\s]+\1\b){2,}", r"\1", raw, flags=re.IGNORECASE).strip()
                if is_hallucination(cleaned, custom_vocabulary):
                    return ""
                return cleaned

        return ""
