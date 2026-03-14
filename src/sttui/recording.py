"""Audio recorder adapter using sounddevice."""

from __future__ import annotations

from pathlib import Path
import threading
import time
import wave

import sounddevice as sd

from sttui.errors import RecordingError


class RecorderSession:
    def __init__(self, output_path: Path, max_seconds: int):
        self.output_path = output_path
        self.max_seconds = max_seconds
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._error: Exception | None = None
        self._sample_rate = 16000
        self._channels = 1
        self._sample_width = 2
        self._frames_per_chunk = 1024

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._ready_event.clear()
        self._error = None
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()
        if not self._ready_event.wait(timeout=2):
            self._stop_event.set()
            self._thread.join(timeout=2)
            self._thread = None
            raise RecordingError("failed to start recorder: input device unavailable")
        if self._error is not None:
            err = self._error
            self._thread = None
            raise RecordingError(f"failed to start recorder: {err}") from err

    def _record_loop(self) -> None:
        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(self.output_path), "wb") as wav_file:
                wav_file.setnchannels(self._channels)
                wav_file.setsampwidth(self._sample_width)
                wav_file.setframerate(self._sample_rate)
                with sd.RawInputStream(
                    samplerate=self._sample_rate,
                    channels=self._channels,
                    dtype="int16",
                    blocksize=self._frames_per_chunk,
                ) as stream:
                    self._ready_event.set()
                    deadline = time.monotonic() + float(self.max_seconds)
                    while not self._stop_event.is_set():
                        if time.monotonic() >= deadline:
                            break
                        data, overflowed = stream.read(self._frames_per_chunk)
                        if overflowed:
                            continue
                        wav_file.writeframes(data)
        except Exception as exc:
            self._error = exc
            self._ready_event.set()

    def stop(self) -> None:
        if self._thread is None:
            return
        thread = self._thread
        self._stop_event.set()
        thread.join(timeout=5)
        self._thread = None

        if thread.is_alive():
            raise RecordingError("recorder did not stop cleanly")

        try:
            has_audio = (
                self.output_path.exists() and self.output_path.stat().st_size > 44
            )
        except OSError:
            has_audio = False
        if has_audio:
            return

        if self._error is not None:
            raise RecordingError(f"recorder failed: {self._error}") from self._error

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
