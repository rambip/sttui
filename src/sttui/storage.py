"""Storage and filename helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def ensure_recordings_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def timestamp_label(now: datetime | None = None) -> str:
    dt = now or datetime.now()
    return dt.strftime("%Y%m%d-%H%M%S")


def next_audio_path(recordings_dir: Path, now: datetime | None = None) -> Path:
    base = f"sttui-{timestamp_label(now=now)}"
    ensure_recordings_dir(recordings_dir)
    return recordings_dir / f"{base}.wav"


def transcript_path_for_audio(audio_path: Path) -> Path:
    return audio_path.with_suffix(".txt")


def write_transcript(audio_path: Path, transcript: str) -> Path:
    text_path = transcript_path_for_audio(audio_path)
    text_path.write_text(transcript, encoding="utf-8")
    return text_path
