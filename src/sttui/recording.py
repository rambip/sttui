"""Audio recorder adapter using sounddevice."""

from __future__ import annotations

from pathlib import Path
import threading
import time
from typing import Any
import wave

import sounddevice as sd

from sttui.errors import RecordingError


class RecorderSession:
    def __init__(
        self, output_path: Path, max_seconds: int, input_device: int | None = None
    ):
        self.output_path = output_path
        self.max_seconds = max_seconds
        self.input_device = input_device
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
            device_info = _get_input_device_info(self.input_device)
            self._sample_rate = _device_sample_rate(
                device_info, fallback=self._sample_rate
            )
            max_channels = int(device_info.get("max_input_channels", 1))
            self._channels = 1 if max_channels >= 1 else max_channels
            if self._channels < 1:
                raise RecordingError("selected device has no input channels")
            with wave.open(str(self.output_path), "wb") as wav_file:
                wav_file.setnchannels(self._channels)
                wav_file.setsampwidth(self._sample_width)
                wav_file.setframerate(self._sample_rate)
                with sd.RawInputStream(
                    samplerate=self._sample_rate,
                    channels=self._channels,
                    device=self.input_device,
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


def _default_input_index() -> int | None:
    default_device = sd.default.device
    if isinstance(default_device, (tuple, list)) and default_device:
        maybe_index = default_device[0]
    else:
        maybe_index = default_device

    if maybe_index is None:
        return None
    if isinstance(maybe_index, int) and maybe_index >= 0:
        return maybe_index
    return None


def _get_input_device_info(input_device: int | None) -> dict[str, Any]:
    default_index = _default_input_index() if input_device is None else input_device
    if default_index is None:
        info = sd.query_devices(kind="input")
    else:
        info = sd.query_devices(default_index)
    return info if isinstance(info, dict) else dict(info)


def _device_sample_rate(info: dict[str, Any], fallback: int) -> int:
    value = info.get("default_samplerate")
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    return fallback


def list_input_devices() -> tuple[list[tuple[int, str]], int | None]:
    """Return available input devices and current default input index."""
    devices: list[tuple[int, str]] = []
    raw_devices = sd.query_devices()
    for index, device in enumerate(raw_devices):
        info = device if isinstance(device, dict) else dict(device)
        max_input = int(info.get("max_input_channels", 0))
        if max_input <= 0:
            continue
        name = str(info.get("name") or f"Device {index}")
        api = str(info.get("hostapi", "?"))
        devices.append((index, f"{name} (hostapi {api})"))
    return devices, _default_input_index()
