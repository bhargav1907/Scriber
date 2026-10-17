"""
Scriber — Audio Ducking Manager
Temporarily reduces or restores system output volume during active recording
to prevent speaker playback bleed into the microphone.
"""

import subprocess


class AudioDucker:
    def __init__(self):
        self._previous_volume: int | None = None
        self._is_ducked: bool = False

    def duck(self, target_volume: int = 12) -> None:
        """Lower system audio to target_volume percentage."""
        if self._is_ducked:
            return
        try:
            res = subprocess.run(
                ["osascript", "-e", "output volume of (get volume settings)"],
                capture_output=True,
                text=True,
                check=True,
                timeout=1.5,
            )
            vol = int(res.stdout.strip())
            if vol > target_volume:
                self._previous_volume = vol
                subprocess.run(
                    ["osascript", "-e", f"set volume output volume {target_volume}"],
                    check=True,
                    timeout=1.5,
                )
                self._is_ducked = True
        except Exception:
            pass

    def unduck(self) -> None:
        """Restore previous system audio volume."""
        if not self._is_ducked or self._previous_volume is None:
            return
        try:
            subprocess.run(
                ["osascript", "-e", f"set volume output volume {self._previous_volume}"],
                check=True,
                timeout=1.5,
            )
        except Exception:
            pass
        finally:
            self._previous_volume = None
            self._is_ducked = False
