"""
Scriber — Microphone Audio Recorder
Records audio from the selected (or dynamically resolved system default) input device.
Saves recordings as 16 kHz mono WAV files for Whisper.
"""

import time
import wave
import numpy as np
import sounddevice as sd
try:
    from backend.config import APP_DIR
except ImportError:
    from config import APP_DIR


import os
import sys
import threading

class AudioRecorder:
    _is_any_recording: bool = False
    _last_devices_signature: tuple | None = None
    _sd_lock = threading.Lock()

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
        print(f"[Scriber] Audio input device set to: {device if device is not None else 'System Default'}")

    @classmethod
    def refresh_devices(cls) -> None:
        """Force PortAudio to re-enumerate CoreAudio devices so newly connected Bluetooth/USB devices appear.
        Silences low-level PortAudio C AUHAL stderr output for dormant virtual devices (Zoom, Virtual Desktop).
        """
        if cls._is_any_recording:
            return
        with cls._sd_lock:
            # Temporarily redirect OS-level file descriptor 2 (stderr) to /dev/null
            saved_stderr = None
            try:
                stderr_fd = sys.stderr.fileno()
                saved_stderr = os.dup(stderr_fd)
                devnull = os.open(os.devnull, os.O_WRONLY)
                os.dup2(devnull, stderr_fd)
                os.close(devnull)
            except Exception:
                pass

            try:
                sd._terminate()
                sd._initialize()
            except Exception as e:
                print(f"[Scriber] Could not refresh sounddevice: {e}")
            finally:
                if saved_stderr is not None:
                    try:
                        os.dup2(saved_stderr, sys.stderr.fileno())
                        os.close(saved_stderr)
                    except Exception:
                        pass

    @classmethod
    def get_input_devices(cls, force_refresh: bool = False) -> dict:
        """Return dict with available devices and currently active system default device info."""
        if force_refresh and not cls._is_any_recording:
            cls.refresh_devices()

        with cls._sd_lock:
            devices = []
            default_name = "Unknown"
            default_idx = None
            try:
                default_info = sd.query_devices(kind="input")
                default_name = default_info.get("name", "Unknown")
                default_idx = default_info.get("index", None)
            except Exception as e:
                print(f"[Scriber] Could not query default input device: {e}")

            try:
                raw_devices = sd.query_devices()
                for idx, dev in enumerate(raw_devices):
                    if dev.get("max_input_channels", 0) > 0:
                        devices.append({
                            "id": idx,
                            "name": dev["name"],
                            "channels": dev["max_input_channels"],
                            "default_samplerate": int(dev.get("default_samplerate", 16000)),
                            "is_default": (idx == default_idx),
                        })
            except Exception as e:
                print(f"[Scriber] Error querying input devices: {e}")

            return {
                "devices": devices,
                "default_name": default_name,
                "default_id": default_idx,
            }

    @classmethod
    def check_for_device_changes(cls) -> tuple[bool, dict]:
        """Check if devices or default input changed without tearing down PortAudio. Returns (has_changed, current_devices_dict)."""
        if cls._is_any_recording:
            return False, {}

        # Query devices directly from CoreAudio without destructive PortAudio teardown
        info = cls.get_input_devices(force_refresh=False)
        sig = (info.get("default_name"), tuple(d["name"] for d in info.get("devices", [])))
        if cls._last_devices_signature is None:
            cls._last_devices_signature = sig
            return False, info

        if sig != cls._last_devices_signature:
            cls._last_devices_signature = sig
            return True, info

        return False, info

    def start(self) -> bool:
        """Start recording from the microphone. Returns True on success, False on failure."""
        if self.recording:
            return True

        with self._sd_lock:
            if self.stream:
                try:
                    self.stream.stop()
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None

            self.audio_chunks = []
            self.start_time = time.time()
            self.active_sample_rate = self.sample_rate

            # Dynamically resolve target device
            target_device = self.device
            device_label = "System Default"
            dev_sr = None

            if target_device is None or target_device == "default":
                # Query the currently active macOS system default input device in real-time
                try:
                    def_info = sd.query_devices(kind="input")
                    target_device = def_info.get("index", None)
                    device_label = f"System Default ({def_info.get('name', 'Unknown')})"
                    dev_sr = int(def_info.get("default_samplerate", 16000))
                except Exception as e:
                    print(f"[Scriber] Warning: could not query real-time default input: {e}")
                    target_device = None
            else:
                try:
                    info = sd.query_devices(target_device, kind="input")
                    device_label = info.get("name", str(target_device))
                    dev_sr = int(info.get("default_samplerate", 16000))
                    target_device = info.get("index", target_device)
                except Exception as e:
                    print(f"[Scriber] Warning: specified device '{target_device}' not found ({e}), falling back to System Default")
                    try:
                        def_info = sd.query_devices(kind="input")
                        target_device = def_info.get("index", None)
                        device_label = f"System Default ({def_info.get('name', 'Unknown')})"
                        dev_sr = int(def_info.get("default_samplerate", 16000))
                    except Exception:
                        target_device = None

            print(f"[Scriber] 🎙️ Opening microphone stream on: '{device_label}' (device_id={target_device})")

            # Attempt to open stream at 16000 Hz. If device rejects it, fallback to device default rate
            opened = False
            candidates = [self.sample_rate]
            if dev_sr and dev_sr not in candidates:
                candidates.append(dev_sr)
            candidates.extend([48000, 44100])

            for sr in candidates:
                try:
                    self.stream = sd.InputStream(
                        device=target_device,
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
                except Exception:
                    self.stream = None
                    continue

            if not opened:
                print(f"[Scriber] ❌ Failed to open microphone stream on device '{device_label}'. Please verify microphone permissions in macOS System Settings → Privacy & Security → Microphone.")
                self.recording = False
                AudioRecorder._is_any_recording = False
                return False

            self.recording = True
            AudioRecorder._is_any_recording = True
            return True

    def stop(self) -> tuple[np.ndarray | None, float, str | None]:
        """Stop recording. Returns (audio_np, duration_seconds, filepath)."""
        if not self.recording and not self.stream:
            return None, 0.0, None

        self.recording = False
        AudioRecorder._is_any_recording = False
        duration = time.time() - self.start_time if self.start_time else 0

        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        audio_np, filepath = self._process_audio()
        return audio_np, duration, filepath

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

    def _process_audio(self) -> tuple[np.ndarray | None, str | None]:
        """Concatenate recorded chunks, resample to 16kHz, filter, normalize, and asynchronously persist WAV."""
        if not self.audio_chunks:
            return None, None

        audio = np.concatenate(self.audio_chunks, axis=0).flatten()
        self.audio_chunks = []

        # 1. Resample to 16 kHz if recorded at a different rate
        if self.active_sample_rate != self.sample_rate and len(audio) > 0:
            target_len = int(round(len(audio) * self.sample_rate / self.active_sample_rate))
            audio = np.interp(
                np.linspace(0, len(audio), target_len, endpoint=False),
                np.arange(len(audio)),
                audio,
            ).astype(np.float32)

        # 2. DC Offset Removal (zero-center the waveform)
        audio = audio - np.mean(audio)

        # 3. High-Pass Filter (> 80 Hz) to eliminate desk thumps, mic pops, and low-frequency rumble
        try:
            from scipy import signal
            sos = signal.butter(4, 80, "hp", fs=self.sample_rate, output="sos")
            audio = signal.sosfilt(sos, audio).astype(np.float32)
        except Exception as e:
            print(f"[Scriber] High-pass filter warning: {e}")

        # 4. Smart Peak Gain Normalization
        # Automatically boosts quiet microphones (like Bluetooth open-earbuds) to Whisper's ideal sweet spot
        max_val = float(np.max(np.abs(audio)))
        if max_val > 1e-4:
            target_peak = 0.85  # ~ -1.4 dBFS
            gain = min(target_peak / max_val, 12.0)  # Max +21.5 dB boost to prevent noise amplification
            audio = audio * gain
            print(f"[Scriber] 🎚️ Audio cleaned & normalized (peak: {max_val:.3f} → {np.max(np.abs(audio)):.3f}, gain: {gain:.2f}x)")

        filepath = APP_DIR / "last_recording.wav"

        # 5. Non-blocking asynchronous WAV save in a background daemon thread
        def _save_wav_async(audio_data: np.ndarray, path, channels: int, rate: int):
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                audio_int16 = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)
                with wave.open(str(path), "w") as wf:
                    wf.setnchannels(channels)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(rate)
                    wf.writeframes(audio_int16.tobytes())
            except Exception as ex:
                print(f"[Scriber] Async WAV save error: {ex}")

        threading.Thread(
            target=_save_wav_async,
            args=(audio.copy(), filepath, self.channels, self.sample_rate),
            daemon=True,
        ).start()

        return audio, str(filepath)
