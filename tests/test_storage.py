from datetime import datetime
from pathlib import Path

from sttui.storage import next_audio_path, transcript_path_for_audio


def test_next_audio_path_uses_timestamp(tmp_path: Path) -> None:
    dt = datetime(2026, 1, 2, 3, 4, 5)
    p = next_audio_path(tmp_path, now=dt)
    assert p.name == "sttui-20260102-030405.wav"
    assert p.parent == tmp_path


def test_transcript_path_for_audio() -> None:
    audio = Path("/tmp/sttui-20260102-030405.wav")
    txt = transcript_path_for_audio(audio)
    assert str(txt).endswith(".txt")
