"""Audio recorder adapter using pw-record."""

from __future__ import annotations

from pathlib import Path
import signal
import shutil
import subprocess

from sttui.errors import RecordingError


class RecorderSession:
    def __init__(self, output_path: Path, max_seconds: int):
        self.output_path = output_path
        self.max_seconds = max_seconds
        self._proc: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        if shutil.which("pw-record") is None:
            raise RecordingError("pw-record not found; install pipewire tools")
        if self._proc is not None:
            return
        cmd = ["pw-record", str(self.output_path)]
        try:
            self._proc = subprocess.Popen(  # noqa: S603
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise RecordingError(f"failed to start recorder: {exc}") from exc

    def stop(self) -> None:
        if self._proc is None:
            return
        proc = self._proc
        self._proc = None
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
        try:
            _, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise RecordingError("recorder did not stop cleanly")

        if proc.returncode in (0, -2, -15, 130):
            return

        try:
            has_audio = (
                self.output_path.exists() and self.output_path.stat().st_size > 44
            )
        except OSError:
            has_audio = False
        if has_audio:
            return

        if proc.returncode not in (0, -2, -15, 130):
            details = (stderr or b"").decode("utf-8", errors="replace").strip()
            msg = f"recorder failed (exit {proc.returncode})"
            if details:
                msg = f"{msg}: {details.splitlines()[-1]}"
            raise RecordingError(msg)

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None
