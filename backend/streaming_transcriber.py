"""
Scriber — Dictation Pipeline Orchestrator
Transcribes complete, pristine audio waveforms on Apple Silicon Metal GPU Whisper,
executes contextual LLM cleanup or fast phonetic normalization, delivers text via
instantaneous native AppKit Cmd+V (<0.5ms), and collects precise latency benchmarks.
"""

import time
import re
import numpy as np

try:
    from backend.clipboard import paste_text
    from backend.transcriber import is_hallucination
except ImportError:
    from clipboard import paste_text
    from transcriber import is_hallucination



class StreamingTranscriber:
    """
    Scriber dictation pipeline orchestrator.
    Manages end-to-end full-waveform transcription, acoustic anti-hallucination defense,
    contextual LLM polishing, native paste delivery, and millisecond latency profiling.
    """
    def __init__(
        self,
        transcriber,
        cleaner,
        custom_vocabulary: list[str] | None = None,
        word_replacements: dict[str, str] | None = None,
        app_name: str | None = None,
        mode: str = "general",
        llm_enabled: bool = True,
    ):
        self.transcriber = transcriber
        self.cleaner = cleaner
        self.custom_vocabulary = custom_vocabulary or []
        self.word_replacements = word_replacements or {}
        self.app_name = app_name
        self.mode = mode
        self.llm_enabled = llm_enabled

    def _is_silence_or_hallucination(self, text: str) -> bool:
        """Filter out Whisper silence phantom outputs, non-speech punctuation, and prompt echoing hallucinations."""
        return is_hallucination(text, self.custom_vocabulary)

    async def finalize(self, full_audio_np: np.ndarray | None, auto_paste: bool = True) -> dict:
        """
        Transcribe complete, unchopped audio on Apple Silicon Metal GPU Whisper,
        perform contextual LLM cleanup or phonetic normalization, deliver via
        native AppKit Cmd+V paste with clipboard restoration (<0.5ms),
        and return exact millisecond latency benchmarks.
        """
        if full_audio_np is None or len(full_audio_np) == 0:
            return {
                "raw_text": "",
                "cleaned_text": "",
                "whisper_ms": 0,
                "llm_ms": 0,
                "total_ms": 0,
                "llm_enabled": self.llm_enabled,
            }

        # 1. Full-waveform Whisper transcription on Metal GPU (unified memory, unchopped attention)
        t_w0 = time.time()
        try:
            raw_text = self.transcriber.transcribe(
                full_audio_np,
                custom_vocabulary=self.custom_vocabulary,
            )
        except Exception as e:
            print(f"[Scriber] Transcription error: {e}")
            raw_text = ""
        whisper_ms = int(round((time.time() - t_w0) * 1000))

        # 2. Anti-hallucination defense: discard silence hallucinations BEFORE any delivery
        if self._is_silence_or_hallucination(raw_text):
            if raw_text:
                print(f"[Scriber] ⚠️ Discarded silence/prompt hallucination: '{raw_text}'")
            return {
                "raw_text": "",
                "cleaned_text": "",
                "whisper_ms": whisper_ms,
                "llm_ms": 0,
                "total_ms": whisper_ms,
                "llm_enabled": self.llm_enabled,
            }

        # 3. LLM Cleanup or Fast Phonetic Normalization
        cleaned_text = raw_text
        llm_ms = 0

        if self.llm_enabled and self.mode != "raw":
            t_l0 = time.time()
            try:
                cleaned_text = await self.cleaner.cleanup(
                    raw_text,
                    mode=self.mode,
                    custom_vocabulary=self.custom_vocabulary,
                    word_replacements=self.word_replacements,
                    app_name=self.app_name,
                )
            except Exception as e:
                print(f"[Scriber] LLM cleanup error: {e}")
                cleaned_text = self.cleaner.normalize_text(
                    raw_text,
                    custom_vocabulary=self.custom_vocabulary,
                    word_replacements=self.word_replacements,
                    app_name=self.app_name,
                )
            llm_ms = int(round((time.time() - t_l0) * 1000))
        else:
            cleaned_text = self.cleaner.normalize_text(
                raw_text,
                custom_vocabulary=self.custom_vocabulary,
                word_replacements=self.word_replacements,
                app_name=self.app_name,
            )

        total_ms = whisper_ms + llm_ms

        # 4. Reliable Text Delivery via Native AppKit Cmd+V (<0.5ms) with clipboard preservation
        if auto_paste and cleaned_text and cleaned_text.strip():
            try:
                paste_text(cleaned_text)
            except Exception as e:
                print(f"[Scriber] Paste text error: {e}")

        return {
            "raw_text": raw_text,
            "cleaned_text": cleaned_text,
            "whisper_ms": whisper_ms,
            "llm_ms": llm_ms,
            "total_ms": total_ms,
            "llm_enabled": self.llm_enabled,
        }
