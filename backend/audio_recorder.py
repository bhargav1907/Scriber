"""
Scriber — Microphone Audio Recorder
Records audio from the default input device using sounddevice.
Saves recordings as 16 kHz mono WAV files for Whisper.
"""

import time
import wave
import numpy as np
import sounddevice as sd
from config import APP_DIR


class AudioRecorder:
    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.recording = False
        self.audio_chunks: list[np.ndarray] = []
        self.stream: sd.InputStream | None = None
        self.start_time: float = 0
        self.level_callback = None  # Called with (float) audio level 0..1

    def start(self) -> None:
        """Start recording from the microphone."""
        self.audio_chunks = []
        self.recording = True
        self.start_time = time.time()
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=self._audio_callback,
            blocksize=1024,
        )
        self.stream.start()

    def stop(self) -> tuple[str | None, float]:
        """Stop recording. Returns (filepath, duration_seconds)."""
        self.recording = False
        duration = time.time() - self.start_time if self.start_time else 0

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        filepath = self._save_audio()
        return filepath, duration

    def get_duration(self) -> float:
        """Get current recording duration in seconds."""
        if self.recording and self.start_time:
            return time.time() - self.start_time
        return 0.0

    def _audio_callback(self, indata, frames, time_info, status):
        """Called by sounddevice for each audio block."""
        if not self.recording:
            return
        self.audio_chunks.append(indata.copy())

        # Report audio level to the UI
        if self.level_callback:
            rms = float(np.sqrt(np.mean(indata ** 2)))
            # Normalize to 0..1 range (amplify since speech is usually quiet)
            level = min(rms * 8.0, 1.0)
            self.level_callback(level)

    def _save_audio(self) -> str | None:
        """Concatenate recorded chunks and save as WAV."""
        if not self.audio_chunks:
            return None

        audio = np.concatenate(self.audio_chunks, axis=0)
        filepath = APP_DIR / "last_recording.wav"
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Convert float32 [-1, 1] to int16
        audio_int16 = (audio * 32767).astype(np.int16)

        with wave.open(str(filepath), "w") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_int16.tobytes())

        return str(filepath)
