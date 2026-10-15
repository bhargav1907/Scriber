"""
Scriber — Microphone Audio Recorder
Records audio from the selected (or default) input device using sounddevice.
Saves recordings as 16 kHz mono WAV files for Whisper.
"""

import time
import wave
import numpy as np
import sounddevice as sd
from config import APP_DIR


class AudioRecorder:
    def __init__(self, sample_rate: int = 16000, channels: int = 1, device: int | str | None = None):
        self.sample_rate = sample_rate
        self.active_sample_rate = sample_rate
        self.channels = channels
        self.device = device
        self.recording = False
        self.audio_chunks: list[np.ndarray] = []
        self.stream: sd.InputStream | None = None
        self.start_time: float = 0
        self.level_callback = None  # Called with (float) audio level 0..1

    def set_device(self, device: int | str | None) -> None:
        """Update selected input device."""
        self.device = device
        print(f"[Scriber] Audio input device set to: {device}")

    @staticmethod
    def get_input_devices() -> list[dict]:
        """Return list of available audio input devices."""
        devices = []
        try:
            raw_devices = sd.query_devices()
            default_in = sd.default.device[0]
            for idx, dev in enumerate(raw_devices):
                if dev.get("max_input_channels", 0) > 0:
                    devices.append({
                        "id": idx,
                        "name": dev["name"],
                        "channels": dev["max_input_channels"],
                        "default_samplerate": int(dev.get("default_samplerate", 16000)),
                        "is_default": (idx == default_in),
                    })
        except Exception as e:
            print(f"[Scriber] Error querying input devices: {e}")
        return devices

    def start(self) -> None:
        """Start recording from the microphone."""
        if self.recording:
            return

        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        self.audio_chunks = []
        self.recording = True
        self.start_time = time.time()
        self.active_sample_rate = self.sample_rate

        # Attempt to open stream at 16000 Hz. If device rejects it, fallback to device default rate
        opened = False
        candidates = [self.sample_rate]
        if self.device is not None:
            try:
                info = sd.query_devices(self.device, kind="input")
                dev_sr = int(info.get("default_samplerate", 48000))
                if dev_sr not in candidates:
                    candidates.append(dev_sr)
            except Exception:
                pass
        candidates.extend([48000, 44100])

        for sr in candidates:
            try:
                self.stream = sd.InputStream(
                    device=self.device,
                    samplerate=sr,
                    channels=self.channels,
                    dtype="float32",
                    callback=self._audio_callback,
                    blocksize=1024,
                )
                self.stream.start()
                self.active_sample_rate = sr
                opened = True
                break
            except Exception as e:
                self.stream = None
                continue

        if not opened:
            print(f"[Scriber] ❌ Failed to open microphone stream on device {self.device}")
            self.recording = False

    def stop(self) -> tuple[str | None, float]:
        """Stop recording. Returns (filepath, duration_seconds)."""
        if not self.recording and not self.stream:
            return None, 0.0

        self.recording = False
        duration = time.time() - self.start_time if self.start_time else 0

        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
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
        """Concatenate recorded chunks, resample if needed, and save as 16kHz WAV."""
        if not self.audio_chunks:
            return None

        audio = np.concatenate(self.audio_chunks, axis=0).flatten()

        # Resample to 16 kHz if recorded at a different rate
        if self.active_sample_rate != self.sample_rate and len(audio) > 0:
            target_len = int(round(len(audio) * self.sample_rate / self.active_sample_rate))
            audio = np.interp(
                np.linspace(0, len(audio), target_len, endpoint=False),
                np.arange(len(audio)),
                audio,
            ).astype(np.float32)

        filepath = APP_DIR / "last_recording.wav"
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Convert float32 [-1, 1] to int16
        audio_int16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)

        with wave.open(str(filepath), "w") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_int16.tobytes())

        return str(filepath)
