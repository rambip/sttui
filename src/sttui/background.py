"""Background recording lifecycle and worker execution."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import signal
import subprocess
import sys
import time

from dataclasses import asdict

from sttui.clipboard import copy_text
from sttui.config import RuntimeSettings
from sttui.errors import ClipboardError, RecordingError, TranscriptionError
from sttui.notifications import send_desktop_notification
from sttui.recording import RecorderSession
from sttui.send import SendConfig, execute_send
from sttui.storage import write_transcript
from sttui.transcribe import transcribe_audio

_STOP_REQUESTED = False


def _check_ydotool_available() -> None:
    """Check if paste tool is available (pydotool with daemon or pynput fallback).

    Raises AssertionError if neither tool is usable.
    """
    # Check if pydotool is installed
    try:
        import pydotool
    except ImportError:
        # No pydotool - check pynput fallback
        try:
            import pynput
        except ImportError:
            raise AssertionError(
                "no paste tool available: install python-ydotool or pynput"
            )
        # pynput available
        return

    # pydotool is installed - require daemon running
    socket_path = os.environ.get("YDOTOOL_SOCKET", "/run/user/1000/.ydotool_socket")
    assert os.path.exists(socket_path), (
        "ydotoold daemon not running. Start 'ydotoold' first."
    )


@dataclass(frozen=True)
class BackgroundState:
    pid: int
    audio_path: Path
    started_at: str


def default_state_path() -> Path:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "sttui" / "background.json"
    return Path(f"/tmp/sttui-{os.getuid()}") / "background.json"


def default_log_path() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home) / "sttui" / "background.log"
    return Path.home() / ".local" / "state" / "sttui" / "background.log"


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_state(path: Path) -> BackgroundState | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    pid = raw.get("pid")
    audio_path = raw.get("audio_path")
    started_at = raw.get("started_at")
    if not isinstance(pid, int) or pid <= 0:
        return None
    if not isinstance(audio_path, str) or not audio_path:
        return None
    if not isinstance(started_at, str) or not started_at:
        return None
    return BackgroundState(pid=pid, audio_path=Path(audio_path), started_at=started_at)


def _write_state(path: Path, state: BackgroundState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": state.pid,
        "audio_path": str(state.audio_path),
        "started_at": state.started_at,
    }
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload), encoding="utf-8")
    tmp_path.replace(path)


def _clear_state(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def _load_live_state(path: Path) -> BackgroundState | None:
    state = _read_state(path)
    if state is None:
        return None
    if _is_pid_alive(state.pid):
        return state
    _clear_state(path)
    return None


def start_background(
    settings: RuntimeSettings,
    *,
    notify: bool = False,
    send_config: SendConfig | None = None,
    output_clipboard: bool = True,
    output_stdout: bool = False,
    output_paste: bool = False,
    state_path: Path | None = None,
    log_path: Path | None = None,
) -> tuple[int, str]:
    # Check ydotoold if paste mode requested
    if output_paste:
        _check_ydotool_available()

    actual_state_path = state_path or default_state_path()
    actual_log_path = log_path or default_log_path()

    running = _load_live_state(actual_state_path)
    if running is not None:
        return 1, f"background recording already running (pid {running.pid})"

    audio_path = settings.recordings_dir / (
        f"sttui-bg-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.wav"
    )

    actual_log_path.parent.mkdir(parents=True, exist_ok=True)
    with actual_log_path.open("a", encoding="utf-8") as log_file:
        cmd = [
            sys.executable,
            "-m",
            "sttui.cli",
            "__background_worker",
            "--state-path",
            str(actual_state_path),
            "--audio-path",
            str(audio_path),
            "--model",
            settings.model,
            "--prompt",
            settings.prompt,
            "--max-seconds",
            str(settings.max_seconds),
            "--recordings-dir",
            str(settings.recordings_dir),
        ]
        if settings.input_device is not None:
            cmd.extend(["--input-device", str(settings.input_device)])
        if settings.debug:
            cmd.append("--debug")
        if notify:
            cmd.append("--notify")
        if send_config:
            # Serialize SendConfig to JSON
            config_dict = {
                "targets": [
                    {"kind": t.kind, "target": t.target, "body": t.body}
                    for t in send_config.targets
                ],
                "delay_ms": send_config.delay_ms,
            }
            cmd.extend(["--send-config", json.dumps(config_dict)])

        cmd.append("--output-clipboard")
        cmd.append("1" if output_clipboard else "0")
        cmd.append("--output-stdout")
        cmd.append("1" if output_stdout else "0")
        cmd.append("--output-paste")
        cmd.append("1" if output_paste else "0")

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )

    _write_state(
        actual_state_path,
        BackgroundState(
            pid=process.pid,
            audio_path=audio_path,
            started_at=datetime.now(timezone.utc).isoformat(),
        ),
    )
    if notify:
        send_desktop_notification(
            "sttui",
            f"Background recording started (pid {process.pid})",
        )
    return 0, f"background recording started (pid {process.pid})"


def stop_background(
    *,
    notify: bool = False,
    state_path: Path | None = None,
) -> tuple[int, str]:
    actual_state_path = state_path or default_state_path()
    running = _load_live_state(actual_state_path)
    if running is None:
        return 1, "background recording is not running"
    try:
        os.kill(running.pid, signal.SIGTERM)
    except ProcessLookupError:
        _clear_state(actual_state_path)
        return 1, "background recording already stopped"
    return 0, f"background recording stopping (pid {running.pid})"


def toggle_background(
    settings: RuntimeSettings,
    *,
    notify: bool = False,
    send_config: SendConfig | None = None,
    output_clipboard: bool = True,
    output_stdout: bool = False,
    output_paste: bool = False,
    state_path: Path | None = None,
    log_path: Path | None = None,
) -> tuple[int, str]:
    # Check ydotoold if paste mode requested (before starting)
    if output_paste:
        _check_ydotool_available()

    actual_state_path = state_path or default_state_path()
    running = _load_live_state(actual_state_path)
    if running is not None:
        return stop_background(notify=notify, state_path=actual_state_path)
    return start_background(
        settings,
        notify=notify,
        send_config=send_config,
        output_clipboard=output_clipboard,
        output_stdout=output_stdout,
        output_paste=output_paste,
        state_path=actual_state_path,
        log_path=log_path,
    )


def _handle_stop_signal(signum: int, frame: object) -> None:
    del signum, frame
    global _STOP_REQUESTED
    _STOP_REQUESTED = True


def run_background_worker(
    *,
    state_path: Path,
    audio_path: Path,
    settings: RuntimeSettings,
    notify: bool = False,
    send_config: SendConfig | None = None,
    output_clipboard: bool = True,
    output_stdout: bool = False,
    output_paste: bool = False,
) -> int:
    global _STOP_REQUESTED
    _STOP_REQUESTED = False

    signal.signal(signal.SIGTERM, _handle_stop_signal)
    signal.signal(signal.SIGINT, _handle_stop_signal)

    session = RecorderSession(
        output_path=audio_path,
        max_seconds=settings.max_seconds,
        input_device=settings.input_device,
    )
    transcript = ""
    try:
        session.start()
        while session.running and not _STOP_REQUESTED:
            time.sleep(0.1)
        session.stop()
        transcript, _, _ = transcribe_audio(
            api_key=settings.api_key,
            model=settings.model,
            prompt=settings.prompt,
            audio_path=audio_path,
        )
        write_transcript(audio_path, transcript)

        if output_clipboard:
            copy_text(transcript)
            if notify:
                send_desktop_notification("sttui", "Background transcript copied to clipboard")

        if output_paste:
            from sttui.clipboard import paste_text
            paste_text(transcript)
            if notify:
                send_desktop_notification("sttui", "Background transcript pasted at cursor")

        if output_stdout:
            print(transcript)

        if notify:
            pass  # Notification handled above for clipboard

        # Execute send config if provided
        if send_config and send_config.targets:
            parts = [transcript]
            results = execute_send(parts, send_config)
            for ok, msg in results:
                if ok:
                    print(f"[send] {msg}", file=sys.stderr)
                else:
                    print(f"[send] error: {msg}", file=sys.stderr)
            if notify:
                send_desktop_notification("sttui", "Background transcript sent")

        return 0
    except (RecordingError, TranscriptionError, ClipboardError) as exc:
        print(f"background worker error: {exc}", file=sys.stderr)
        if notify:
            send_desktop_notification("sttui", f"Background error: {exc}")
        return 1
    finally:
        state = _read_state(state_path)
        if state is not None and state.pid == os.getpid():
            _clear_state(state_path)
