"""Clipboard support with wl-copy/xclip."""

from __future__ import annotations

import os
import shutil
import subprocess

from sttui.errors import ClipboardError


def copy_text(text: str) -> None:
    has_wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
    has_x11 = bool(os.environ.get("DISPLAY"))
    timeout_seconds: float | None

    if has_wayland and shutil.which("wl-copy"):
        cmd = ["wl-copy"]
        timeout_seconds = None
    elif has_x11 and shutil.which("xclip"):
        cmd = ["xclip", "-selection", "clipboard"]
        timeout_seconds = 3
    elif shutil.which("wl-copy"):
        cmd = ["wl-copy"]
        timeout_seconds = None
    elif shutil.which("xclip"):
        cmd = ["xclip", "-selection", "clipboard"]
        timeout_seconds = 3
    else:
        raise ClipboardError("clipboard unavailable: install wl-copy or xclip")

    try:
        proc = subprocess.run(  # noqa: S603
            cmd,
            input=text.encode("utf-8"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise ClipboardError("clipboard command timed out") from exc
    except OSError as exc:
        raise ClipboardError(f"clipboard error: {exc}") from exc

    if proc.returncode != 0:
        details = proc.stderr.decode("utf-8", errors="replace").strip()
        if details:
            raise ClipboardError(f"clipboard error: {details.splitlines()[-1]}")
        raise ClipboardError("clipboard error")
