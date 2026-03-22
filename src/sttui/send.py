"""Send transcript to external endpoints and commands."""

from __future__ import annotations

import json
import logging
import subprocess
import os
from dataclasses import dataclass, field
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


@dataclass
class SendTarget:
    """A single send destination (POST endpoint or command)."""

    kind: str  # "post" or "command"
    target: str  # URL or shell command
    body: str | None = None  # JSON body template (POST only, $0/$1 placeholders)


@dataclass
class SendConfig:
    """Configuration for a send operation."""

    targets: list[SendTarget] = field(default_factory=list)
    delay_ms: int | None = None  # None = auto (0 for first, 100 for rest)


def send_post(
    url: str,
    body: str,
    *,
    as_json: bool = False,
    timeout: float = 30.0,
) -> tuple[bool, str]:
    """Send HTTP POST with body.

    If as_json is True, sends as JSON with Content-Type application/json.
    Otherwise sends as plain text.

    Returns (success, message).
    """
    try:
        if as_json:
            resp = requests.post(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            )
        else:
            resp = requests.post(
                url,
                data=body,
                headers={"Content-Type": "text/plain"},
                timeout=timeout,
            )
        if 200 <= resp.status_code < 300:
            return True, f"POST {url}: {resp.status_code}"
        return False, f"POST {url}: HTTP {resp.status_code}"
    except requests.RequestException as exc:
        return False, f"POST {url}: {exc}"


def send_command(
    command: str,
    body: str,
    *,
    timeout: float = 30.0,
) -> tuple[bool, str]:
    """Execute a command, piping body to stdin.

    Returns (success, message). On failure, message includes log file path.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            input=body,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, f"Command OK: {command}"
        log_path = _write_command_log(command, result.stderr)
        return (
            False,
            f"Command failed (exit {result.returncode}): {command}\n  Log: {log_path}",
        )
    except subprocess.TimeoutExpired:
        log_path = _write_command_log(command, "Timed out")
        return False, f"Command timed out: {command}\n  Log: {log_path}"
    except OSError as exc:
        log_path = _write_command_log(command, str(exc))
        return False, f"Command error: {exc}\n  Log: {log_path}"


def _write_command_log(command: str, stderr: str) -> Path:
    """Write command failure details to a log file."""
    if state_home := os.environ.get("XDG_STATE_HOME"):
        log_dir = Path(state_home) / "sttui"
    else:
        log_dir = Path.home() / ".local" / "state" / "sttui"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "send_errors.log"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n--- Command: {command} ---\n")
        f.write(stderr or "<no stderr>\n")
    return log_path


def format_body(format_str: str | None, parts: list[str]) -> str:
    """Build the send body from transcript parts.

    $0 = all parts joined by \\n\\n
    $1 = first part, $2 = second part, etc.
    If no format_str, returns $0 (all parts joined).

    When format_str is provided, values are JSON-escaped so that
    inserting them into a JSON template produces valid JSON.
    """
    all_text = "\n\n".join(parts)
    if format_str is None:
        return all_text
    result = format_str.replace("$0", json.dumps(all_text))
    for i, part in enumerate(parts, start=1):
        result = result.replace(f"${i}", json.dumps(part))
    return result


def execute_send(
    parts: list[str],
    config: SendConfig,
) -> list[tuple[bool, str]]:
    """Execute all send targets in sequence with configured delays.

    Returns list of (success, message) for each target.
    """
    import time

    results: list[tuple[bool, str]] = []
    for i, target in enumerate(config.targets):
        if i > 0:
            delay = config.delay_ms if config.delay_ms is not None else 100
            if delay > 0:
                time.sleep(delay / 1000.0)

        body = format_body(target.body, parts)

        if target.kind == "post":
            success, msg = send_post(
                target.target, body, as_json=target.body is not None
            )
        else:
            success, msg = send_command(target.target, body)

        results.append((success, msg))
        logger.debug("Send result: %s %s", success, msg)

    return results
