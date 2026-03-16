"""Desktop notification helpers."""

from __future__ import annotations

from notifypy import Notify  # pyright: ignore[reportMissingImports]


def send_desktop_notification(title: str, message: str) -> None:
    try:
        notification = Notify()
        notification.application_name = "sttui"
        notification.title = title
        notification.message = message
        notification.send()
    except Exception:
        return
