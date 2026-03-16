from __future__ import annotations

from pathlib import Path

from sttui.background import (
    BackgroundState,
    _load_live_state,
    _read_state,
    _write_state,
)


def test_read_write_state_round_trip(tmp_path: Path) -> None:
    state_path = tmp_path / "background.json"
    state = BackgroundState(
        pid=1234,
        audio_path=tmp_path / "sample.wav",
        started_at="2026-03-16T00:00:00+00:00",
    )
    _write_state(state_path, state)
    loaded = _read_state(state_path)
    assert loaded == state


def test_load_live_state_clears_stale_pid(tmp_path: Path) -> None:
    state_path = tmp_path / "background.json"
    stale = BackgroundState(
        pid=999999,
        audio_path=tmp_path / "stale.wav",
        started_at="2026-03-16T00:00:00+00:00",
    )
    _write_state(state_path, stale)
    loaded = _load_live_state(state_path)
    assert loaded is None
    assert not state_path.exists()
