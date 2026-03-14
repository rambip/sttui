"""Textual app for one-shot dictation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import RadioButton, RadioSet, Static
from textual.timer import Timer

from sttui.clipboard import copy_text
from sttui.config import RuntimeSettings
from sttui.errors import ClipboardError, RecordingError, TranscriptionError
from sttui.recording import RecorderSession, list_input_devices
from sttui.storage import next_audio_path, write_transcript
from sttui.transcribe import list_audio_models, transcribe_audio


class SettingsRadioSet(RadioSet, inherit_bindings=False):
    """RadioSet with only explicit settings-navigation bindings."""

    BINDINGS = [
        Binding("up,k", "previous_button", "Previous", show=False),
        Binding("down,j", "next_button", "Next", show=False),
        Binding("enter,space", "toggle_button", "Select", show=False),
    ]


class SettingsPanel(Static):
    """Settings summary and selector panel."""

    BINDINGS = [
        Binding("up,k", "radio_previous", "Previous", show=False),
        Binding("down,j", "radio_next", "Next", show=False),
        Binding("left,h", "previous_tab", "Prev Tab"),
        Binding("right,l", "next_tab", "Next Tab"),
    ]

    class InputDeviceChanged(Message):
        def __init__(self, input_device: int | None) -> None:
            self.input_device = input_device
            super().__init__()

    class ModelChanged(Message):
        def __init__(self, model: str) -> None:
            self.model = model
            super().__init__()

    is_open = reactive(False, recompose=True)
    audio_devices = reactive((), recompose=True)
    model_ids = reactive((), recompose=True)
    active_tab = reactive("audio", recompose=True)

    def __init__(self, *, model: str, input_device: int | None) -> None:
        super().__init__(id="settings_widget")
        self.selected_model = model
        self.selected_input_device = input_device
        self.default_input_index: int | None = None

    def compose(self) -> ComposeResult:
        if not self.is_open:
            device = (
                "Default"
                if self.selected_input_device is None
                else str(self.selected_input_device)
            )
            hint = Text("Type ':' to change settings", style="bold rgb(255,210,120)")
            yield Static("Settings:", id="settings_title")
            yield Static(f"\u25e6 Audio device: {device}", id="settings_line_audio")
            yield Static(
                f"\u25e6 Transciption model: {self.selected_model}",
                id="settings_line_model",
            )
            yield Static(hint, id="settings_hint")
            return

        yield Static(self._tabs_bar_text(), id="settings_tabs_bar")
        if self.active_tab == "audio":
            with SettingsRadioSet(id="audio_radio"):
                for index, label in self.audio_devices:
                    checked = index == self._effective_input_device()
                    suffix = " (current)" if checked else ""
                    yield RadioButton(f"{index}: {label}{suffix}", value=checked)
        else:
            with SettingsRadioSet(id="model_radio"):
                for model in self.model_ids:
                    yield RadioButton(model, value=model == self.selected_model)

    def on_mount(self) -> None:
        if self.is_open:
            self.focus_first_control()

    def _effective_input_device(self) -> int | None:
        if self.selected_input_device is not None:
            return self.selected_input_device
        return self.default_input_index

    def set_open(self, open_state: bool) -> None:
        self.is_open = open_state
        if open_state:
            self.active_tab = "audio"
            self.call_after_refresh(self.focus_first_control)
            self.call_after_refresh(self._focus_active_tab_controls)

    def set_audio_devices(
        self,
        devices: list[tuple[int, str]],
        *,
        default_index: int | None,
    ) -> None:
        self.default_input_index = default_index
        self.audio_devices = tuple(devices)
        effective = self._effective_input_device()
        available_ids = {index for index, _ in devices}
        if effective is not None and effective not in available_ids:
            self.selected_input_device = default_index
        if self.is_open:
            self.call_after_refresh(self._focus_active_tab_controls)

    def set_models(self, models: list[str]) -> None:
        self.model_ids = tuple(models)
        if self.selected_model not in self.model_ids and self.model_ids:
            self.selected_model = self.model_ids[0]
        if self.is_open:
            self.call_after_refresh(self._focus_active_tab_controls)

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        radio_set = event.radio_set
        if radio_set.id == "audio_radio":
            pressed = event.pressed.label.plain
            maybe_index = pressed.split(":", 1)[0].strip()
            if maybe_index.isdigit():
                index = int(maybe_index)
                self.selected_input_device = index
                self.post_message(self.InputDeviceChanged(index))
        elif radio_set.id == "model_radio":
            model = event.pressed.label.plain.strip()
            if model:
                self.selected_model = model
                self.post_message(self.ModelChanged(model))

    def focus_first_control(self) -> None:
        if not self.is_open:
            return
        controls = list(self.query("RadioSet"))
        if controls:
            controls[0].focus()

    def _focus_active_tab_controls(self) -> None:
        if not self.is_open:
            return
        if self.active_tab == "models":
            radio = self.query_one("#model_radio", SettingsRadioSet)
        else:
            radio = self.query_one("#audio_radio", SettingsRadioSet)
        radio.focus()

    def action_previous_tab(self) -> None:
        self._switch_tab(-1)

    def action_next_tab(self) -> None:
        self._switch_tab(1)

    def _switch_tab(self, delta: int) -> None:
        if not self.is_open:
            return
        tabs = ["audio", "models"]
        active = self.active_tab if self.active_tab in tabs else tabs[0]
        idx = tabs.index(active)
        self.active_tab = tabs[(idx + delta) % len(tabs)]
        self.call_after_refresh(self._focus_active_tab_controls)

    def action_radio_previous(self) -> None:
        radio = self._active_radio_set()
        if radio is not None:
            radio.action_previous_button()

    def action_radio_next(self) -> None:
        radio = self._active_radio_set()
        if radio is not None:
            radio.action_next_button()

    def _active_radio_set(self) -> SettingsRadioSet | None:
        try:
            if self.active_tab == "models":
                return self.query_one("#model_radio", SettingsRadioSet)
            return self.query_one("#audio_radio", SettingsRadioSet)
        except NoMatches:
            return None

    def _tabs_bar_text(self) -> Text:
        text = Text()
        if self.active_tab == "audio":
            text.append("[ Audio ]", style="bold black on #78B478")
            text.append(" ")
            text.append("[ Models ]", style="#AAAAAA")
        else:
            text.append("[ Audio ]", style="#AAAAAA")
            text.append(" ")
            text.append("[ Models ]", style="bold black on #78B478")
        return text


class SttuiApp(App[None]):
    """Interactive one-shot dictation UI.

    Layout:
    - title bar
    - one-line colored state bar
    - content box (spinner/result/error)
    - saved-path metadata line
    - instructions
    - short-lived notification line
    """

    DEFAULT_CSS = """
    Screen {
        layout: vertical;
    }

    #title {
        dock: top;
        height: 3;
        content-align: center middle;
        text-style: bold;
    }

    #layout {
        width: 100%;
        height: 1fr;
        align: center top;
    }

    #panel {
        width: 88;
        max-width: 100%;
        border: round green;
        padding: 1 2;
    }

    #state_line {
        height: 1;
        margin-bottom: 1;
        padding: 0 1;
        color: black;
        background: rgb(180, 180, 180);
    }

    #state_line.state-idle {
        background: rgb(180, 180, 180);
    }

    #state_line.state-recording {
        background: rgb(255, 200, 0);
    }

    #state_line.state-transcribing {
        background: rgb(0, 180, 220);
    }

    #state_line.state-done {
        background: rgb(100, 210, 100);
    }

    #state_line.state-error {
        background: rgb(255, 90, 90);
    }

    #content_box {
        height: 12;
        padding: 1 1;
        margin-bottom: 1;
        border: round gray;
        overflow-y: auto;
    }

    #hint {
        color: rgb(190, 210, 230);
        margin-top: 0;
    }

    #quick_actions {
        layout: horizontal;
        height: auto;
        margin-bottom: 1;
    }

    .action_box {
        width: auto;
        border: round rgb(120, 170, 220);
        padding: 0 1;
        margin-right: 1;
        color: rgb(210, 230, 250);
    }

    #audio_meta {
        color: rgb(180, 180, 180);
        margin-bottom: 1;
    }

    #settings_widget {
        min-height: 5;
        height: auto;
        margin-top: 1;
        padding: 0 1;
        color: rgb(228, 210, 140);
    }

    #settings_title {
        color: rgb(245, 220, 130);
        text-style: bold;
    }

    #settings_line_audio {
        color: rgb(236, 215, 145);
    }

    #settings_line_model {
        color: rgb(236, 215, 145);
    }

    #settings_hint {
        color: rgb(255, 210, 120);
    }

    #settings_tabs_bar {
        height: 1;
        margin-bottom: 1;
    }

    #audio_radio {
        height: 1fr;
        overflow-y: auto;
    }

    #model_radio {
        height: 1fr;
        overflow-y: auto;
    }

    Toast.-information {
        background: rgb(26, 52, 70);
        color: rgb(220, 236, 246);
        border: wide rgb(120, 170, 220);
    }

    Toast.-warning {
        background: rgb(64, 50, 18);
        color: rgb(252, 236, 170);
        border: wide rgb(210, 180, 80);
    }

    Toast.-error {
        background: rgb(70, 24, 24);
        color: rgb(255, 220, 220);
        border: wide rgb(220, 90, 90);
    }
    """

    BINDINGS = [
        Binding("space", "toggle_record", "Record/Stop", show=True),
        Binding("s", "stop_record", "Stop", show=True),
        Binding("c", "copy_transcript", "Copy", show=True),
        Binding("u", "undo_last_transcript", "Undo", show=True),
        Binding("backspace", "undo_last_transcript", "Undo", show=True),
        Binding("enter", "confirm_or_restart", "Enter", show=True),
        Binding("colon", "toggle_settings", "Settings", show=False),
        Binding("escape", "close_settings", "Close Settings", show=False),
        Binding("q", "quit_app", "Quit", show=True),
    ]

    def __init__(self, settings: RuntimeSettings):
        super().__init__()
        self.settings = settings
        self.session: RecorderSession | None = None
        self.audio_path: Path | None = None
        self.transcript: str | None = None
        self.transcript_path: Path | None = None
        self.error_message: str | None = None
        self.status = "idle"
        self.exit_code = 1
        self.emit_stdout = False
        self._spinner_index = 0
        self._max_timer: Timer | None = None
        self.last_error_for_stderr: str | None = None
        self.transcripts: list[str] = []
        self.current_input_device = settings.input_device
        self.current_model = settings.model
        self.settings_open = False

    def compose(self) -> ComposeResult:
        yield Static("sttui - speech to text", id="title")
        with Vertical(id="layout"):
            with Vertical(id="panel"):
                yield Static("", id="state_line")
                yield Static("", id="content_box")
                yield Static("", id="audio_meta")
                with Horizontal(id="quick_actions"):
                    yield Static("Space: keep recording", classes="action_box")
                    yield Static("C: copy transcript", classes="action_box")
                    yield Static("U/Backspace: undo last", classes="action_box")
                yield Static("", id="hint")
                yield SettingsPanel(
                    model=self.current_model,
                    input_device=self.current_input_device,
                )

    def on_mount(self) -> None:
        self.set_interval(0.12, self._tick)
        self._render_all()

    def _tick(self) -> None:
        if self.status in {"recording", "transcribing"}:
            self._spinner_index = (self._spinner_index + 1) % 4
            self._render_state_line()

    def _render_all(self) -> None:
        self._render_state_line()
        self._render_content_box()
        self._render_audio_meta()
        self._render_quick_actions()
        self._render_hint()

    def _render_state_line(self) -> None:
        """Render one-line state banner with status-specific color."""
        widget = self.query_one("#state_line", Static)
        widget.remove_class(
            "state-idle",
            "state-recording",
            "state-transcribing",
            "state-done",
            "state-error",
        )
        if self.status == "idle":
            widget.add_class("state-idle")
            widget.update("Idle")
        elif self.status == "recording":
            widget.add_class("state-recording")
            spinner = ["/", "|", "\\", "-"][self._spinner_index]
            widget.update(f"Recording {spinner}")
        elif self.status == "transcribing":
            widget.add_class("state-transcribing")
            dots = [".", "..", "...", "...."][self._spinner_index]
            widget.update(f"Transcribing{dots}")
        elif self.status == "done":
            widget.add_class("state-done")
            widget.update("Transcript result:")
        elif self.status == "error":
            widget.add_class("state-error")
            widget.update("Error")

    def _render_content_box(self) -> None:
        """Render primary content area separate from status banner."""
        if self.status == "error":
            content = self.error_message or ""
        elif self.transcripts:
            content = "\n\n".join(self.transcripts)
        else:
            content = "\nPress Space to start recording"
        self.query_one("#content_box", Static).update(content)

    def _render_quick_actions(self) -> None:
        """Show action boxes only after at least one transcript exists."""
        actions = self.query_one("#quick_actions", Horizontal)
        actions.styles.display = "block" if self.transcripts else "none"

    def _render_audio_meta(self) -> None:
        """Render saved path info below the main box."""
        lines: list[str] = []
        if self.audio_path:
            lines.append(f"Audio: {self.audio_path}")
        if self.transcript_path:
            lines.append(f"Transcript: {self.transcript_path}")
        self.query_one("#audio_meta", Static).update("\n".join(lines))

    def _render_hint(self) -> None:
        if not self.transcripts:
            hint = ""
        elif self.status == "done" and self.settings.stdout_mode:
            hint = "Press Enter to write transcript to stdout and exit, Q to quit"
        else:
            hint = "Press Enter to create a new recording, Q to quit"
        self.query_one("#hint", Static).update(hint)

    def _set_notification(
        self,
        message: str,
        *,
        severity: Literal["information", "warning", "error"] = "information",
        timeout: float = 2.0,
    ) -> None:
        """Show a toast notification."""
        self.notify(message, severity=severity, timeout=timeout)

    def _set_error(self, message: str) -> None:
        self.status = "error"
        self.error_message = message
        self.last_error_for_stderr = message
        self._render_all()

    async def action_toggle_record(self) -> None:
        if self.status == "recording":
            await self.action_stop_record()
            return
        if self.status in {"idle", "done", "error"}:
            self._start_recording()

    def _start_recording(self) -> None:
        self.transcript = None
        self.transcript_path = None
        self.error_message = None
        self.audio_path = next_audio_path(self.settings.recordings_dir)
        self.session = RecorderSession(
            output_path=self.audio_path,
            max_seconds=self.settings.max_seconds,
            input_device=self.current_input_device,
        )
        try:
            self.session.start()
        except RecordingError as exc:
            self._set_error(str(exc))
            return
        if self._max_timer is not None:
            self._max_timer.stop()
        self._max_timer = self.set_timer(
            self.settings.max_seconds, self._auto_stop_recording
        )
        self.status = "recording"
        self._render_all()

    def _auto_stop_recording(self) -> None:
        if self.status == "recording":
            asyncio.create_task(self.action_stop_record())

    async def action_stop_record(self) -> None:
        if self.status != "recording" or self.session is None:
            return
        if self._max_timer is not None:
            self._max_timer.stop()
            self._max_timer = None
        try:
            self.session.stop()
        except RecordingError as exc:
            self._set_error(str(exc))
            return
        self.session = None
        self.status = "transcribing"
        self._render_all()
        await self._run_transcription()

    async def action_toggle_settings(self) -> None:
        self.settings_open = not self.settings_open
        panel = self.query_one(SettingsPanel)
        panel.set_open(self.settings_open)
        if not self.settings_open:
            return

        panel.set_audio_devices([], default_index=None)
        panel.set_models([])

        self._set_notification("Loading available models...", timeout=1.5)

        try:
            devices, default_index = await asyncio.to_thread(list_input_devices)
            panel.set_audio_devices(devices, default_index=default_index)
        except Exception:
            panel.set_audio_devices([], default_index=None)

        try:
            models = await asyncio.to_thread(
                list_audio_models,
                self.settings.api_key,
            )
            panel.set_models(models)
            self._set_notification(
                f"Loaded {len(models)} audio model(s)",
                timeout=2.5,
            )
        except TranscriptionError as exc:
            panel.set_models([])
            self._set_notification(
                f"Failed to load models: {exc}",
                severity="warning",
                timeout=4.0,
            )

    def action_close_settings(self) -> None:
        if not self.settings_open:
            return
        self.settings_open = False
        panel = self.query_one(SettingsPanel)
        panel.set_open(False)

    def on_settings_panel_input_device_changed(
        self,
        message: SettingsPanel.InputDeviceChanged,
    ) -> None:
        self.current_input_device = message.input_device

    def on_settings_panel_model_changed(
        self,
        message: SettingsPanel.ModelChanged,
    ) -> None:
        self.current_model = message.model

    async def _run_transcription(self) -> None:
        assert self.audio_path is not None
        audio_path = self.audio_path
        try:
            transcript = await asyncio.to_thread(
                transcribe_audio,
                api_key=self.settings.api_key,
                model=self.current_model,
                prompt=self.settings.prompt,
                audio_path=audio_path,
            )
        except TranscriptionError as exc:
            self._set_error(f"{exc}, audio saved in {audio_path}")
            return
        self.transcript = transcript
        self.transcripts.append(transcript)
        self.transcript_path = write_transcript(audio_path, transcript)
        self.status = "done"
        self._render_all()

    def action_copy_transcript(self) -> None:
        if not self.transcripts:
            self._set_notification("No transcript to copy", severity="warning")
            return
        self.transcript = self.transcripts[-1]
        asyncio.create_task(self._copy_transcript_async())
        self._set_notification("Copying transcript...")

    async def _copy_transcript_async(self) -> None:
        """Run clipboard copy off the UI thread to avoid hangs."""
        if not self.transcript:
            self._set_notification("No transcript to copy", severity="warning")
            return
        try:
            await asyncio.to_thread(copy_text, self.transcript)
        except ClipboardError as exc:
            self._set_error(str(exc))
            return
        self._set_notification("Text copied to clipboard", timeout=2.0)

    def action_undo_last_transcript(self) -> None:
        """Remove the most recent transcript from history."""
        if self.status in {"recording", "transcribing"}:
            self._set_notification("Stop recording before undo")
            return
        if not self.transcripts:
            self._set_notification("Nothing to undo")
            return
        self.transcripts.pop()
        self.transcript = self.transcripts[-1] if self.transcripts else None
        if not self.transcripts and self.status == "done":
            self.status = "idle"
        self._render_all()
        self._set_notification("Removed last transcript")

    def action_confirm_or_restart(self) -> None:
        if self.status == "done" and self.settings.stdout_mode and self.transcript:
            self.emit_stdout = True
            self.exit_code = 0
            self.exit()
            return
        if self.status in {"done", "error"}:
            self.status = "idle"
            self.transcript = None
            self.transcript_path = None
            self.error_message = None
            self._render_all()

    async def action_quit_app(self) -> None:
        if self.settings_open:
            self.action_close_settings()
            return
        self.emit_stdout = False
        self.last_error_for_stderr = None
        if self._max_timer is not None:
            self._max_timer.stop()
            self._max_timer = None
        if self.status == "recording" and self.session is not None:
            try:
                self.session.stop()
            except RecordingError:
                pass
        if self.status == "done" and not self.settings.stdout_mode:
            self.exit_code = 0
        self.exit()
