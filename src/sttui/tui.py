"""Textual app for one-shot dictation."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import ContentSwitcher, Select, Static
from textual.timer import Timer

from sttui.clipboard import copy_text
from sttui.config import RuntimeSettings
from sttui.errors import ClipboardError, RecordingError, TranscriptionError
from sttui.recording import RecorderSession, list_input_devices
from sttui.storage import next_audio_path, write_transcript
from sttui.transcribe import list_audio_models, transcribe_audio


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

    #notification {
        height: 1;
        margin-top: 1;
        color: green;
    }

    #settings_info {
        margin-top: 1;
        color: rgb(200, 210, 180);
    }

    #settings_hint {
        color: rgb(160, 170, 150);
    }

    #settings_menu {
        margin-top: 1;
        border: round rgb(120, 170, 120);
        padding: 1;
        display: none;
    }

    #settings_title {
        text-style: bold;
        margin-bottom: 1;
    }

    #settings_subtitle {
        color: rgb(180, 200, 170);
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("space", "toggle_record", "Record/Stop", show=True),
        Binding("s", "stop_record", "Stop", show=True),
        Binding("c", "copy_transcript", "Copy", show=True),
        Binding("u", "undo_last_transcript", "Undo", show=True),
        Binding("backspace", "undo_last_transcript", "Undo", show=True),
        Binding("enter", "confirm_or_restart", "Enter", show=True),
        Binding("colon,shift:semicolon", "open_settings", "Settings", show=True),
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
        self._notification_timer: Timer | None = None
        self.notification_message: str = ""
        self.last_error_for_stderr: str | None = None
        self.transcripts: list[str] = []
        self.settings_menu_open = False
        self.settings_menu_step = "root"
        self.active_model = settings.model
        self.selected_input_device: int | None = None
        self.selected_input_device_label = "default"
        self._root_options: list[tuple[str, str]] = [
            ("Select setting...", "__none__"),
            ("Change model", "change_model"),
            ("Change device", "change_device"),
        ]
        self._device_options: list[tuple[str, int]] = []
        self._model_options: list[tuple[str, str]] = [
            (self.active_model, self.active_model)
        ]
        self._models_loaded = False
        self._loading_models = False
        self._suspend_select_events = False
        self._load_input_devices()

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
                yield Static("", id="notification")
                yield Static("", id="settings_info")
                yield Static("type ':' to change settings", id="settings_hint")
                with Vertical(id="settings_menu"):
                    yield Static("Settings", id="settings_title")
                    yield Static("Choose a settings category", id="settings_subtitle")
                    with ContentSwitcher(
                        initial="settings_root_select", id="settings_switcher"
                    ):
                        yield Select[str](
                            self._root_options,
                            prompt="Settings",
                            allow_blank=False,
                            disabled=True,
                            id="settings_root_select",
                        )
                        yield Select[int](
                            self._device_options,
                            prompt="Recording device",
                            allow_blank=False,
                            disabled=True,
                            id="device_select",
                        )
                        yield Select[str](
                            self._model_options,
                            prompt="Transcription model",
                            allow_blank=False,
                            disabled=True,
                            id="model_select",
                        )

    def on_mount(self) -> None:
        self.set_interval(0.12, self._tick)
        self._apply_selected_device_to_widget()
        self._apply_selected_model_to_widget()
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
        self._render_notification()
        self._render_settings_info()
        self._render_settings_menu()

    def _load_input_devices(self) -> None:
        try:
            devices, default_index = list_input_devices()
        except Exception:
            self._device_options = [("Default input device", -1)]
            self.selected_input_device = None
            self.selected_input_device_label = "default"
            return

        if not devices:
            self._device_options = [("No input device available", -1)]
            self.selected_input_device = None
            self.selected_input_device_label = "none"
            return

        self._device_options = [(label, index) for index, label in devices]
        selected = default_index
        if selected is None:
            selected = devices[0][0]
        self.selected_input_device = selected
        label_map = {idx: label for idx, label in devices}
        self.selected_input_device_label = label_map.get(selected, devices[0][1])

    def _apply_selected_device_to_widget(self) -> None:
        select = self.query_one("#device_select", Select)
        if self.selected_input_device is not None:
            self._suspend_select_events = True
            select.value = self.selected_input_device
            self._suspend_select_events = False

    def _apply_selected_model_to_widget(self) -> None:
        select = self.query_one("#model_select", Select)
        if self._model_options:
            self._suspend_select_events = True
            select.value = self.active_model
            self._suspend_select_events = False

    def _reset_root_selection(self) -> None:
        root_select = self.query_one("#settings_root_select", Select)
        self._suspend_select_events = True
        root_select.value = "__none__"
        self._suspend_select_events = False

    def _render_settings_info(self) -> None:
        text = (
            f"◯ model={self.active_model}\n◯ device={self.selected_input_device_label}"
        )
        self.query_one("#settings_info", Static).update(text)

    def _render_settings_menu(self) -> None:
        menu = self.query_one("#settings_menu", Vertical)
        switcher = self.query_one("#settings_switcher", ContentSwitcher)
        root_select = self.query_one("#settings_root_select", Select)
        device_select = self.query_one("#device_select", Select)
        model_select = self.query_one("#model_select", Select)
        subtitle = self.query_one("#settings_subtitle", Static)
        is_open = self.settings_menu_open
        menu.styles.display = "block" if is_open else "none"
        switcher.current = {
            "root": "settings_root_select",
            "device": "device_select",
            "model": "model_select",
        }.get(self.settings_menu_step, "settings_root_select")
        show_root = is_open and self.settings_menu_step == "root"
        show_device = is_open and self.settings_menu_step == "device"
        show_model = is_open and self.settings_menu_step == "model"
        root_select.disabled = not show_root
        device_select.disabled = not show_device
        model_select.disabled = not show_model
        if show_root:
            subtitle.update("Choose a settings category")
            self.set_focus(root_select)
        elif show_device:
            subtitle.update("Choose recording device")
            self.set_focus(device_select)
        elif show_model:
            subtitle.update("Choose transcription model")
            self.set_focus(model_select)
        elif self.focused in {device_select, root_select, model_select}:
            self.set_focus(None)

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
        if self.status == "done" and self.settings.stdout_mode:
            hint = "Press Enter to write transcript to stdout and exit, Q to quit"
        else:
            hint = "Press Enter to create a new recording, Q to quit"
        self.query_one("#hint", Static).update(hint)

    def _render_notification(self) -> None:
        self.query_one("#notification", Static).update(self.notification_message)

    def _set_notification(self, message: str, seconds: float = 2.0) -> None:
        """Show a short-lived notification message."""
        self.notification_message = message
        self._render_notification()
        if self._notification_timer is not None:
            self._notification_timer.stop()
        self._notification_timer = self.set_timer(seconds, self._clear_notification)

    def _clear_notification(self) -> None:
        self.notification_message = ""
        self._render_notification()

    def _set_error(self, message: str) -> None:
        self.status = "error"
        self.error_message = message
        self.notification_message = ""
        self.last_error_for_stderr = message
        self._render_all()

    def action_open_settings(self) -> None:
        if self.status in {"recording", "transcribing"}:
            self._set_notification("Stop recording before changing settings")
            return
        if self.settings_menu_open:
            self.settings_menu_open = False
            self.settings_menu_step = "root"
            self._reset_root_selection()
            self._render_settings_menu()
            return
        self.settings_menu_open = True
        self.settings_menu_step = "root"
        self._reset_root_selection()
        self._render_settings_menu()

    @on(Select.Changed, "#settings_root_select")
    def on_settings_root_select_changed(self, event: Select.Changed) -> None:
        if self._suspend_select_events:
            return
        value = event.value
        if value == "change_device":
            self.settings_menu_step = "device"
            self._render_settings_menu()
            return
        if value == "change_model":
            self.settings_menu_step = "model"
            self._render_settings_menu()
            if not self._models_loaded and not self._loading_models:
                asyncio.create_task(self._load_models_async())
            return
        if value == "__none__":
            return

    @on(Select.Changed, "#device_select")
    def on_device_select_changed(self, event: Select.Changed) -> None:
        if self._suspend_select_events:
            return
        value = event.value
        if not isinstance(value, int) or value < 0:
            self.selected_input_device = None
            self.selected_input_device_label = "default"
            self._render_settings_info()
            return
        self.selected_input_device = value
        label_map = {v: l for l, v in self._device_options}
        self.selected_input_device_label = label_map.get(value, str(value))
        self.settings_menu_open = False
        self.settings_menu_step = "root"
        self._render_all()
        self._set_notification("Recording device updated")

    @on(Select.Changed, "#model_select")
    def on_model_select_changed(self, event: Select.Changed) -> None:
        if self._suspend_select_events:
            return
        value = event.value
        if not isinstance(value, str) or not value or value == "__none__":
            return
        self.active_model = value
        self.settings_menu_open = False
        self.settings_menu_step = "root"
        self._render_all()
        self._set_notification("Model updated")

    async def _load_models_async(self) -> None:
        self._loading_models = True
        self._set_notification("Loading models...")
        try:
            models = await asyncio.to_thread(list_audio_models, self.settings.api_key)
        except TranscriptionError as exc:
            self._loading_models = False
            self._set_notification(f"Model list failed: {exc}")
            return
        self._loading_models = False
        self._models_loaded = True
        if not models:
            self._model_options = [("No audio-input models found", "__none__")]
            self.query_one("#model_select", Select).set_options(self._model_options)
            self.query_one("#model_select", Select).disabled = True
            self._set_notification("No audio-input models available")
            return
        self._model_options = [(model, model) for model in models]
        model_select = self.query_one("#model_select", Select)
        self._suspend_select_events = True
        model_select.set_options(self._model_options)
        self._suspend_select_events = False
        if self.active_model not in models:
            self.active_model = models[0]
            self._render_settings_info()
        self._apply_selected_model_to_widget()
        self._render_settings_menu()
        self._set_notification("Models loaded")

    async def action_toggle_record(self) -> None:
        if self.settings_menu_open:
            return
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
            input_device=self.selected_input_device,
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
        if self.settings_menu_open:
            return
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

    async def _run_transcription(self) -> None:
        assert self.audio_path is not None
        audio_path = self.audio_path
        try:
            transcript = await asyncio.to_thread(
                transcribe_audio,
                api_key=self.settings.api_key,
                model=self.active_model,
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
        if self.settings_menu_open:
            return
        if not self.transcripts:
            self._set_notification("No transcript to copy")
            return
        self.transcript = self.transcripts[-1]
        asyncio.create_task(self._copy_transcript_async())
        self._set_notification("Copying transcript...")

    async def _copy_transcript_async(self) -> None:
        """Run clipboard copy off the UI thread to avoid hangs."""
        if not self.transcript:
            self._set_notification("No transcript to copy")
            return
        try:
            await asyncio.to_thread(copy_text, self.transcript)
        except ClipboardError as exc:
            self._set_error(str(exc))
            return
        self._set_notification("Text copied to clipboard")

    def action_undo_last_transcript(self) -> None:
        """Remove the most recent transcript from history."""
        if self.settings_menu_open:
            return
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
        if self.settings_menu_open:
            self.settings_menu_open = False
            self.settings_menu_step = "root"
            self._render_settings_menu()
            return
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
        self.emit_stdout = False
        self.last_error_for_stderr = None
        if self._max_timer is not None:
            self._max_timer.stop()
            self._max_timer = None
        if self._notification_timer is not None:
            self._notification_timer.stop()
            self._notification_timer = None
        if self.status == "recording" and self.session is not None:
            try:
                self.session.stop()
            except RecordingError:
                pass
        if self.status == "done" and not self.settings.stdout_mode:
            self.exit_code = 0
        self.exit()
