"""Clipboard support via the Python clipboard package."""

from __future__ import annotations

import clipboard

from sttui.errors import ClipboardError


def copy_text(text: str) -> None:
    try:
        clipboard.copy(text)
    except Exception as exc:  # pragma: no cover - backend/platform dependent
        raise ClipboardError(f"clipboard error: {exc}") from exc


def get_clipboard_text() -> str:
    """Get current clipboard content."""
    try:
        return clipboard.paste()
    except Exception as exc:  # pragma: no cover - backend/platform dependent
        raise ClipboardError(f"clipboard error: {exc}") from exc


def paste_text(text: str) -> None:
    """Paste text to active window using pydotool (if installed) or pynput.

    Uses clipboard sandwich technique:
    1. Save current clipboard
    2. Copy new text to clipboard
    3. Simulate paste (Ctrl+Shift+V)
    4. Restore original clipboard
    """
    import time
    import os

    # Set ydotool socket before import (if it exists)
    socket_path = os.environ.get("YDOTOOL_SOCKET", "/run/user/1000/.ydotool_socket")
    if os.path.exists(socket_path):
        os.environ["YDOTOOL_SOCKET"] = socket_path

    # Save current clipboard
    original = get_clipboard_text()

    # Copy new text
    copy_text(text)

    # Small delay to let clipboard propagate
    time.sleep(0.2)

    # Check if pydotool is available (python-ydotool package installed)
    pydotool_available = False
    try:
        import pydotool
        pydotool_available = True
    except ImportError:
        pass

    if pydotool_available:
        # pydotool is installed - require ydotoold daemon to be running
        if not os.path.exists(socket_path):
            raise ClipboardError(
                "ydotoold daemon not running. Start 'ydotoold' or install ydotoold."
            )
        try:
            pydotool.init()
            # Ctrl+Shift+V = paste from CLIPBOARD
            pydotool.key(pydotool.KEY_LEFTSHIFT, pydotool.DOWN)
            pydotool.key(pydotool.KEY_LEFTCTRL, pydotool.DOWN)
            pydotool.key(pydotool.KEY_V, pydotool.DOWN)
            pydotool.key(pydotool.KEY_V, pydotool.UP)
            pydotool.key(pydotool.KEY_LEFTCTRL, pydotool.UP)
            pydotool.key(pydotool.KEY_LEFTSHIFT, pydotool.UP)

            # Restore original clipboard after paste completes
            time.sleep(0.1)
            clipboard.copy(original)
            return
        except Exception as e:
            raise ClipboardError(f"ydotoold error: {e}") from e

    # No pydotool - fallback to pynput (Ctrl+Shift+V)
    try:
        from pynput.keyboard import Key, Controller

        keyboard = Controller()
        with keyboard.pressed(Key.ctrl, Key.shift):
            keyboard.press("v")
            keyboard.release("v")

        # Restore original clipboard after paste completes
        time.sleep(0.1)
        clipboard.copy(original)
        return
    except Exception:
        pass

    raise ClipboardError("no paste method available: ensure pynput has permission")
