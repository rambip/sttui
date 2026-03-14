"""Clipboard support via the Python clipboard package."""

from __future__ import annotations

import clipboard

from sttui.errors import ClipboardError


def copy_text(text: str) -> None:
    try:
        clipboard.copy(text)
    except Exception as exc:  # pragma: no cover - backend/platform dependent
        raise ClipboardError(f"clipboard error: {exc}") from exc
