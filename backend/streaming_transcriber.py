"""
Scriber — Streaming Transcription Manager
Handles real-time chunk transcription during recording, live typing into focused window,
or buffered instantaneous paste upon key release with latency profiling.
"""

import time
import re
import queue
import threading
import numpy as np

try:
    from backend.clipboard import paste_text, type_text
except ImportError:
    from clipboard import paste_text, type_text


class StreamingTranscriber:
    def __init__(
        self,
        transcriber,
        cleaner,
        delivery_mode: str = "paste_on_finish",
        custom_vocabulary: list[str] | None = None,
        word_replacements: dict[str, str] | None = None,
        app_name: str | None = None,
        mode: str = "general",
        llm_enabled: bool = True,
    ):
        self.transcriber = transcriber
        self.cleaner = cleaner
        self.delivery_mode = delivery_mode  # "paste_on_finish" | "live_typing"
        self.custom_vocabulary = custom_vocabulary or []
        self.word_replacements = word_replacements or {}
        self.app_name = app_name
        self.mode = mode
        self.llm_enabled = llm_enabled

        self._lock = threading.Lock()
        self._accumulated_text = ""
        self._typed_text = ""
        self._chunk_queue: queue.Queue = queue.Queue()
        self._worker_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        self.whisper_time: float = 0.0
        self.llm_time: float = 0.0

    def start(self):
        """Start the background chunk transcription worker."""
        self.reset()
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._process_chunks, daemon=True)
        self._worker_thread.start()

    def reset(self):
        """Reset internal buffers and timing metrics."""
        with self._lock:
            self._accumulated_text = ""
            self._typed_text = ""
            self.whisper_time = 0.0
            self.llm_time = 0.0
            while not self._chunk_queue.empty():
                try:
                    self._chunk_queue.get_nowait()
                except queue.Empty:
                    break

    def get_accumulated_text(self) -> str:
        with self._lock:
            return self._accumulated_text

    def on_chunk(self, chunk: np.ndarray, is_final: bool = False):
        """Called by AudioRecorder when a speech segment is available."""
        if chunk is not None and len(chunk) > 0:
            self._chunk_queue.put((chunk, is_final))

    def _calculate_delta(self, prev: str, current: str) -> str:
        """Calculate new characters or words to emit to the active cursor."""
        if not current:
            return ""
        if not prev:
            return current
        if current.startswith(prev):
            return current[len(prev):]
        # In case of minor acoustic boundary revisions, emit space + new trailing words
        prev_words = prev.split()
        curr_words = current.split()
        if len(curr_words) > len(prev_words) and curr_words[:len(prev_words)] == prev_words:
            return " " + " ".join(curr_words[len(prev_words):])
        return " " + current.strip()

    def _process_chunks(self):
        """Worker thread processing incoming chunks sequentially."""
        while not self._stop_event.is_set():
            try:
                chunk, is_final = self._chunk_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            t0 = time.time()
            try:
                raw_chunk_text = self.transcriber.transcribe(
                    chunk,
                    custom_vocabulary=self.custom_vocabulary,
                )
            except Exception as e:
                print(f"[Scriber] Streaming chunk transcription error: {e}")
                raw_chunk_text = ""
            dt = time.time() - t0

            with self._lock:
                self.whisper_time += dt

            if raw_chunk_text and raw_chunk_text.strip():
                # Apply fast deterministic phonetic normalization on chunk
                norm_chunk = self.cleaner.normalize_text(
                    raw_chunk_text.strip(),
                    custom_vocabulary=self.custom_vocabulary,
                    word_replacements=self.word_replacements,
                    app_name=self.app_name,
                )

                with self._lock:
                    if self._accumulated_text:
                        self._accumulated_text += " " + norm_chunk
                    else:
                        self._accumulated_text = norm_chunk

                    # If Live Typing mode is active, emit delta keystrokes in real time
                    if self.delivery_mode == "live_typing":
                        delta = self._calculate_delta(self._typed_text, self._accumulated_text)
                        if delta:
                            self._typed_text = self._accumulated_text
                            try:
                                type_text(delta)
                            except Exception as e:
                                print(f"[Scriber] Live typing error: {e}")

            self._chunk_queue.task_done()
            if is_final:
                break

    async def finalize(self, full_audio_np: np.ndarray | None, auto_paste: bool = True) -> dict:
        """
        Finalize transcription upon releasing the hotkey:
        - Waits for any in-flight chunk in worker queue.
        - If accumulated text is empty, falls back to full_audio_np transcription.
        - Applies optional Local AI cleanup (Ollama).
        - Executes paste if in paste_on_finish mode.
        - Returns structured metrics.
        """
        # Wait up to 300ms for in-flight chunk worker to finish
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=0.3)

        raw_text = self.get_accumulated_text().strip()

        # If streaming chunks yielded nothing (e.g. very short audio < 1s), transcribe full audio directly
        if not raw_text and full_audio_np is not None and len(full_audio_np) > 0:
            t0 = time.time()
            raw_text = self.transcriber.transcribe(
                full_audio_np,
                custom_vocabulary=self.custom_vocabulary,
            )
            with self._lock:
                self.whisper_time += (time.time() - t0)

        cleaned_text = raw_text
        if raw_text:
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
                    print(f"[Scriber] Final LLM cleanup error: {e}")
                    cleaned_text = self.cleaner.normalize_text(
                        raw_text,
                        custom_vocabulary=self.custom_vocabulary,
                        word_replacements=self.word_replacements,
                        app_name=self.app_name,
                    )
                self.llm_time = time.time() - t_l0
            else:
                cleaned_text = self.cleaner.normalize_text(
                    raw_text,
                    custom_vocabulary=self.custom_vocabulary,
                    word_replacements=self.word_replacements,
                    app_name=self.app_name,
                )

            # Deliver text
            if self.delivery_mode == "paste_on_finish" and auto_paste:
                paste_text(cleaned_text)
            elif self.delivery_mode == "live_typing" and not self._typed_text:
                # If nothing was typed during streaming, emit now
                type_text(cleaned_text)

        whisper_ms = int(round(self.whisper_time * 1000))
        llm_ms = int(round(self.llm_time * 1000))
        total_ms = whisper_ms + llm_ms

        return {
            "raw_text": raw_text,
            "cleaned_text": cleaned_text,
            "whisper_ms": whisper_ms,
            "llm_ms": llm_ms,
            "total_ms": total_ms,
            "delivery_mode": self.delivery_mode,
            "llm_enabled": self.llm_enabled,
        }
