"""Textual app for one-shot dictation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.content import Content
from textual.css.query import NoMatches
from textual.message import Message
from textual.timer import Timer
from textual.widgets import (
    ContentSwitcher,
    DataTable,
    Header,
    RadioButton,
    RadioSet,
    Static,
)

from sttui.clipboard import copy_text
from sttui.config import RuntimeSettings
from sttui.errors import (
    ClipboardError,
    RecordingError,
    RetryableTranscriptionError,
    TranscriptionError,
)
from sttui.send import SendConfig, execute_send
from sttui.storage import next_audio_path, write_transcript

if TYPE_CHECKING:
    from sttui.recording import RecorderSession


class StatusFooter(Static):
    DEFAULT_CSS = """
    StatusFooter {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text;
        content-align: center middle;
        text-align: center;
    }
    """

    BLUE_SHADES = [
        "rgb(80, 100, 200)",
        "rgb(100, 80, 180)",
        "rgb(120, 70, 160)",
    ]

    def set_bindings(self, groups: list[list[tuple[str, str]]]) -> None:
        desc_style = Style(color="#A0A0A0")
        parts: list[Text] = []
        for gi, group in enumerate(groups):
            key_style = Style(
                bold=True, color=self.BLUE_SHADES[gi % len(self.BLUE_SHADES)]
            )
            group_text = Text()
            group_text.append("[ ", style=Style(color="#808080"))
            bindings = Text()
            bindings.append_text(
                Text("  ").join(
                    Text(f"{key}", style=key_style)
                    + Text(":", style=Style(color="#808080"))
                    + Text(desc, style=desc_style)
                    for key, desc in group
                )
            )
            group_text.append_text(bindings)
            group_text.append(" ]", style=Style(color="#808080"))
            parts.append(group_text)
        result = Text("  ").join(parts)
        self.update(result)


class SettingsRadioSet(RadioSet, inherit_bindings=False):
    """RadioSet with only explicit settings-navigation bindings."""

    BINDINGS = [
        Binding("up,k", "previous_button", "Previous", show=False),
        Binding("down,j", "next_button", "Next", show=False),
        Binding("enter,space", "toggle_button", "Select", show=False),
    ]


class SettingsDataTable(DataTable, inherit_bindings=False):
    """DataTable with explicit navigation/select bindings for settings."""

    BINDINGS = [
        Binding("up,k", "cursor_up", "Up", show=False),
        Binding("down,j", "cursor_down", "Down", show=False),
        Binding("left,h", "cursor_left", "Left", show=False),
        Binding("right,l", "cursor_right", "Right", show=False),
        Binding("tab", "select_cursor", "Select", show=False),
    ]


class SettingsPanel(Static):
    """Settings summary and selector panel.

    ContentSwitcher has three fixed panes:
      - "settings_summary_pane": 2-row DataTable (always composed, never recomposed)
      - "settings_audio"    : audio device radio list
      - "settings_models"   : model radio list

    Switching between them is done by setting ContentSwitcher.current directly.
    No recompose is used, so reactive state drives only data updates, not
    widget reconstruction.
    """

    class InputDeviceChanged(Message):
        def __init__(self, input_device: int | None) -> None:
            self.input_device = input_device
            super().__init__()

    class ModelChanged(Message):
        def __init__(self, model: str) -> None:
            self.model = model
            super().__init__()

    def __init__(self, *, model: str, input_device: int | None) -> None:
        super().__init__(id="settings_widget")
        self.selected_model = model
        self.selected_input_device = input_device
        self.default_input_index: int | None = None
        self._is_open = False

    # ------------------------------------------------------------------
    # Compose: three fixed panes, no recompose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with ContentSwitcher(initial="settings_summary_pane"):
            with Vertical(id="settings_summary_pane"):
                yield SettingsDataTable(id="settings_summary")
                yield Static("", id="settings_summary_spacer")
            with Vertical(id="settings_audio"):
                yield Static("[ Audio ]", id="settings_audio_label")
                with SettingsRadioSet(id="audio_radio"):
                    pass  # populated in set_audio_devices
            with Vertical(id="settings_models"):
                yield Static("[ Models ]", id="settings_models_label")
                with SettingsRadioSet(id="model_radio"):
                    pass  # populated in set_models

    def on_mount(self) -> None:
        self._update_summary_table()
        self.query_one("#settings_summary", DataTable).focus()

    # ------------------------------------------------------------------
    # Summary table
    # ------------------------------------------------------------------

    def _update_summary_table(self) -> None:
        device = self._device_label()
        try:
            table = self.query_one("#settings_summary", DataTable)
            table.clear(columns=True)
            table.add_columns("Setting", "Value (press Tab to change)")
            table.add_row("Device", Text(device, style="silver"))
            table.add_row("Model", Text(self.selected_model, style="silver"))
        except NoMatches:
            pass

    def _device_label(self) -> str:
        if self.selected_input_device is None:
            return "Default"
        return next(
            (
                name
                for idx, name in (self._audio_devices or ())
                if idx == self.selected_input_device
            ),
            str(self.selected_input_device),
        )

    # ------------------------------------------------------------------
    # Open / close
    # ------------------------------------------------------------------

    def set_open(self, open_state: bool) -> None:
        self._is_open = open_state
        if not open_state:
            self.query_one(ContentSwitcher).current = "settings_summary_pane"
            self._update_summary_table()
            self.call_after_refresh(
                lambda: self.query_one("#settings_summary", DataTable).focus()
            )

    def action_close_settings(self) -> None:
        if self._is_open:
            self.post_message(SettingsPanel.CloseRequested())

    class CloseRequested(Message):
        pass

    class PaneOpened(Message):
        """Sent when the user opens any detail pane; app should load data."""

        pass

    def open_audio_pane(self) -> None:
        was_open = self._is_open
        self._is_open = True
        self.query_one(ContentSwitcher).current = "settings_audio"
        self.call_after_refresh(self._focus_audio)
        if not was_open:
            self.post_message(SettingsPanel.PaneOpened())

    def open_models_pane(self) -> None:
        was_open = self._is_open
        self._is_open = True
        self.query_one(ContentSwitcher).current = "settings_models"
        self.call_after_refresh(self._focus_models)
        if not was_open:
            self.post_message(SettingsPanel.PaneOpened())

    def _focus_audio(self) -> None:
        try:
            self.query_one("#audio_radio", SettingsRadioSet).focus()
        except NoMatches:
            pass

    def _focus_models(self) -> None:
        try:
            self.query_one("#model_radio", SettingsRadioSet).focus()
        except NoMatches:
            pass

    # ------------------------------------------------------------------
    # Data population
    # ------------------------------------------------------------------

    _audio_devices: list[tuple[int, str]] | None = None

    def set_audio_devices(
        self,
        devices: list[tuple[int, str]],
        *,
        default_index: int | None,
    ) -> None:
        self._audio_devices = devices
        self.default_input_index = default_index
        effective = self._effective_input_device()
        available_ids = {index for index, _ in devices}
        if effective is not None and effective not in available_ids:
            self.selected_input_device = default_index

        radio = self.query_one("#audio_radio", SettingsRadioSet)
        radio.remove_children()
        for index, label in devices:
            checked = index == self._effective_input_device()
            suffix = " (current)" if checked else ""
            radio.mount(RadioButton(f"{index}: {label}{suffix}", value=checked))

        if not self._is_open:
            self._update_summary_table()
        elif self.query_one(ContentSwitcher).current == "settings_audio":
            self.call_after_refresh(self._focus_audio)

    def set_models(self, models: list[str]) -> None:
        if self.selected_model not in models and models:
            self.selected_model = models[0]

        radio = self.query_one("#model_radio", SettingsRadioSet)
        radio.remove_children()
        for model in models:
            radio.mount(RadioButton(model, value=model == self.selected_model))

        if not self._is_open:
            self._update_summary_table()
        elif self.query_one(ContentSwitcher).current == "settings_models":
            self.call_after_refresh(self._focus_models)

    def _effective_input_device(self) -> int | None:
        if self.selected_input_device is not None:
            return self.selected_input_device
        return self.default_input_index

    # ------------------------------------------------------------------
    # Radio selection
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Summary row selection → open correct pane
    # ------------------------------------------------------------------

    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        if self._is_open:
            return
        if event.data_table.id != "settings_summary":
            return
        if event.data_table.cursor_row == 0:
            self.open_audio_pane()
        else:
            self.open_models_pane()


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

    TITLE = "Speak To TUI"

    DEFAULT_CSS = """
    Screen {
        layout: vertical;
    }

    Header {
        dock: top;
    }

    #layout {
        width: 100%;
        height: 1fr;
        align: center top;
    }

    #panel {
        width: 88;
        max-width: 100%;
        height: 100%;
        border: round green;
        padding: 1 2;
    }

    #state_line {
        height: 1;
        padding: 0 1;
        color: black;
    }

    #status_spacer {
        height: 1;
    }

    Screen.compact #status_spacer {
        height: 0;
    }

    #content_box {
        height: 60%;
        border: round gray;
    }

    #content_text {
        padding: 0 1;
    }

    #idle_message {
        height: 60%;
        border: round gray;
        content-align: center middle;
        color: rgb(150, 150, 150);
    }

    #idle_message.retry-hint {
        color: rgb(200, 150, 220);
        border: round rgb(180, 100, 220);
    }

    Screen.compact #content_box {
        margin-top: 0;
    }

    #state_line.state-idle {
        color: rgb(120, 120, 120);
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

    #state_line.state-retry_error {
        background: rgb(180, 100, 220);
    }

    #content_box {
        height: 60%;
        padding: 0 1;
        border: round gray;
        overflow-y: auto;
        content-align: center middle;
    }

    #audio_meta {
        color: rgb(180, 180, 180);
        height: auto;
        min-height: 0;
    }

    #settings_widget {
        min-height: 5;
        height: 1fr;
        padding: 0 1;
    }

    Screen.settings-open #settings_widget {
        min-height: 12;
        height: 3fr;
    }

    #spacer {
        height: 1fr;
        min-height: 0;
    }

    Screen.settings-open #spacer {
        height: 0;
    }

    Screen.compact #spacer {
        height: 0;
    }

    #settings_summary_spacer {
        min-height: 0;
        height: 1fr;
        max-height: 1;
    }

    #settings_summary {
        height: 3;
    }

    #settings_summary_pane {
        height: 1fr;
    }

    ContentSwitcher {
        height: 1fr;
    }

    DataTable {
        margin: 0;
    }

    #settings_hint {
        color: rgb(255, 210, 120);
    }

    #settings_audio_label {
        height: 1;
        margin-bottom: 1;
    }

    #settings_models_label {
        height: 1;
        margin-bottom: 1;
    }

    #settings_audio {
        height: 1fr;
    }

    #settings_models {
        height: 1fr;
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
        Binding("c,y", "copy_transcript", "Copy", show=True),
        Binding("backspace", "undo_last_transcript", "Undo", show=True),
        Binding("enter", "confirm_or_restart", "Enter", show=True),
        Binding("escape,ctrl+c", "cancel_or_close", "Cancel/Close", show=True),
        Binding("q", "quit_app", "Quit", show=True),
        Binding("r", "rerun_transcription", "Rerun", show=True),
    ]

    def __init__(
        self, settings: RuntimeSettings, send_config: SendConfig | None = None
    ):
        super().__init__()
        self.settings = settings
        self.send_config = send_config
        self.session: RecorderSession | None = None
        self.audio_path: Path | None = None
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
        self._last_volume: float = 0.0

    def format_title(self, title: str, sub_title: str) -> Content:
        markup = ""
        for char in title:
            if char.islower():
                markup += f"[i silver]{char}[/]"
            else:
                markup += f"[bold #FFFFFF]{char}[/]"
        return Content.from_markup(markup)

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="layout"):
            with Vertical(id="panel"):
                yield Static("", id="state_line")
                yield Static("", id="status_spacer")
                with VerticalScroll(id="content_box"):
                    yield Static("", id="content_text")
                yield Static("", id="idle_message")
                yield Static("", id="audio_meta")
                yield Static("", id="spacer")
                yield SettingsPanel(
                    model=self.current_model,
                    input_device=self.current_input_device,
                )
        yield StatusFooter("", id="footer")

    def on_mount(self) -> None:
        self.set_interval(0.12, self._tick)
        self._render_all()

    def on_resize(self, event: events.Resize) -> None:
        if event.size.height < 25:
            self.screen.add_class("compact")
        else:
            self.screen.remove_class("compact")

    def _tick(self) -> None:
        if self.status in {"recording", "transcribing"}:
            self._spinner_index = (self._spinner_index + 1) % 4
            self._render_state_line()

    def _render_all(self) -> None:
        self._render_state_line()
        self._render_content_box()
        self._render_audio_meta()
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
            "state-retry_error",
        )
        if self.status == "idle":
            widget.add_class("state-idle")
            widget.update(
                Text("record yourself, and let the AI transcribe.", style="italic dim")
            )
        elif self.status == "recording":
            widget.add_class("state-recording")
            power = self.session.current_power if self.session else 0.0
            normalized = min(power / 2000.0, 1.0)
            width = widget.size.width - 12
            if width < 10:
                width = 40
            bar_width = int(normalized * width)
            last_bar_width = int(self._last_volume * width)
            self._last_volume = normalized

            bar = Text()
            if bar_width > 0:
                bar.append("█" * bar_width, style="bold #FF8C00")
            if bar_width < last_bar_width:
                decay = last_bar_width - bar_width
                bar.append("░" * decay, style="dim")
            widget.update(Text.assemble("Recording ", bar))
        elif self.status == "transcribing":
            widget.add_class("state-transcribing")
            dots = [".", "..", "...", "...."][self._spinner_index]
            widget.update(f"Transcribing{dots}")
        elif self.status == "done":
            widget.add_class("state-done")
            widget.update("Transcript result:")
        elif self.status == "error":
            widget.add_class("state-error")
            widget.update(f"Error: {self.error_message or 'An error occurred'}")
        elif self.status == "retry_error":
            widget.add_class("state-retry_error")
            widget.update(f"Transcription failed: {self.error_message or 'Unknown error'}")

    def _render_content_box(self) -> None:
        """Render primary content area separate from status banner."""
        content_box = self.query_one("#content_box", VerticalScroll)
        idle_msg = self.query_one("#idle_message", Static)

        if self.status == "retry_error" and not self.transcripts:
            content_box.styles.display = "none"
            idle_msg.styles.display = "block"
            idle_msg.add_class("retry-hint")
            idle_msg.update("Press R to retry transcription")
        elif self.status == "error":
            idle_msg.styles.display = "none"
            idle_msg.remove_class("retry-hint")
            if self.transcripts:
                content_box.styles.display = "block"
                text = self.query_one("#content_text", Static)
                text.update(self._format_transcripts_for_display())
                content_box.scroll_end(y_axis=True)
            else:
                content_box.styles.display = "none"
                text = self.query_one("#content_text", Static)
                text.update("")
        elif self.transcripts:
            content_box.styles.display = "block"
            idle_msg.styles.display = "none"
            idle_msg.remove_class("retry-hint")
            text = self.query_one("#content_text", Static)
            text.update(self._format_transcripts_for_display())
            content_box.scroll_end(y_axis=True)
        else:
            content_box.styles.display = "none"
            idle_msg.styles.display = "block"
            idle_msg.remove_class("retry-hint")
            if self.send_config:
                idle_msg.update("Press Space to record, Enter to send transcript")
            else:
                idle_msg.update("Press Space to start recording")

    def _format_transcripts_for_display(self) -> str:
        blocks: list[str] = []
        for transcript in self.transcripts:
            normalized = transcript.replace("\r\n", "\n").replace("\r", "\n")
            lines = normalized.split("\n")
            prefixed_lines = [f"| {line}" if line else "|" for line in lines]
            blocks.append("\n".join(prefixed_lines))
        return "\n\n".join(blocks)

    def get_joined_transcript(self) -> str:
        return "\n\n".join(self.transcripts)

    def _render_audio_meta(self) -> None:
        """Render saved path info below the main box."""
        content = f"Audio: {self.audio_path}" if self.audio_path else ""
        self.query_one("#audio_meta", Static).update(content)

    def _render_hint(self) -> None:
        footer = self.query_one("#footer", StatusFooter)
        if self.status == "recording":
            footer.styles.display = "block"
            footer.set_bindings(
                [
                    [
                        ("Esc", "cancel audio"),
                        ("S", "stop"),
                    ]
                ]
            )
            return
        if self.status == "retry_error":
            footer.styles.display = "block"
            footer.set_bindings(
                [
                    [
                        ("R", "rerun"),
                        ("Esc", "discard"),
                        ("Q", "quit"),
                    ]
                ]
            )
            return
        if not self.transcripts:
            footer.update("")
            footer.styles.display = "none"
            return
        footer.styles.display = "block"
        if self.settings.stdout_mode:
            enter_desc = "write to stdout and exit"
        elif self.send_config:
            enter_desc = "send and continue"
        else:
            enter_desc = "new recording"
        groups = [
            [
                ("Space", "keep recording"),
                ("Backspace", "undo"),
                ("C", "copy"),
            ],
            [
                ("Enter", enter_desc),
                ("Q", "quit"),
            ],
        ]
        footer.set_bindings(groups)

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

    def action_cancel_or_close(self) -> None:
        if self.status == "recording":
            self._cancel_recording()
            return
        if self.status == "retry_error":
            self._discard_error()
            return
        self.action_close_settings()

    def _cancel_recording(self) -> None:
        if self.status != "recording":
            return
        if self._max_timer is not None:
            self._max_timer.stop()
            self._max_timer = None

        audio_path = self.audio_path
        if self.session is not None:
            try:
                self.session.stop()
            except RecordingError:
                pass
        self.session = None

        if audio_path is not None:
            try:
                audio_path.unlink(missing_ok=True)
            except OSError:
                pass

        self.audio_path = None
        self.transcript_path = None
        self.error_message = None
        self.status = "idle"
        self._last_volume = 0.0
        self._render_all()
        self._set_notification("Recording cancelled")

    def _start_recording(self) -> None:
        # Lazy import: recording stack pulls in sounddevice/numpy and is only
        # needed when recording actually starts.
        from sttui.recording import RecorderSession

        self._last_volume = 0.0
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

    async def on_settings_panel_pane_opened(
        self, message: SettingsPanel.PaneOpened
    ) -> None:
        """Load devices and models when the user first opens the settings detail."""
        # Lazy imports: settings open is optional and these endpoints are
        # expensive to import/initialize during initial TUI startup.
        from sttui.recording import list_input_devices
        from sttui.transcribe import list_audio_models

        self.settings_open = True
        self.screen.add_class("settings-open")
        panel = self.query_one(SettingsPanel)

        panel.set_audio_devices([], default_index=None)
        panel.set_models([])

        try:
            devices, default_index = await asyncio.to_thread(list_input_devices)
            panel.set_audio_devices(devices, default_index=default_index)
        except Exception as exc:
            self._set_notification(
                f"Failed to load audio devices: {exc}",
                severity="warning",
                timeout=4.0,
            )
            panel.set_audio_devices([], default_index=None)

        try:
            models = await asyncio.to_thread(
                list_audio_models,
                self.settings.api_key,
            )
            panel.set_models(models)
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
        self.screen.remove_class("settings-open")
        panel = self.query_one(SettingsPanel)
        panel.set_open(False)

    def on_settings_panel_close_requested(
        self, message: SettingsPanel.CloseRequested
    ) -> None:
        self.action_close_settings()

    def on_settings_panel_input_device_changed(
        self,
        message: SettingsPanel.InputDeviceChanged,
    ) -> None:
        self.current_input_device = message.input_device
        self.action_close_settings()

    def on_settings_panel_model_changed(
        self,
        message: SettingsPanel.ModelChanged,
    ) -> None:
        self.current_model = message.model
        self.action_close_settings()

    async def _run_transcription(self) -> None:
        # Lazy import: requests/OpenRouter client is only needed after stop.
        from sttui.transcribe import transcribe_audio

        assert self.audio_path is not None
        audio_path = self.audio_path
        try:
            transcript, malformed_json, model_answer = await asyncio.to_thread(
                transcribe_audio,
                api_key=self.settings.api_key,
                model=self.current_model,
                prompt=self.settings.prompt,
                audio_path=audio_path,
            )
        except RetryableTranscriptionError as exc:
            self.status = "retry_error"
            self.error_message = str(exc)
            self.last_error_for_stderr = str(exc)
            self._render_all()
            return
        except TranscriptionError as exc:
            self._set_error(str(exc))
            return
        if malformed_json:
            shown_answer = model_answer.strip() or "<empty>"
            self._set_notification(
                f"Model returned malformed JSON:\n {shown_answer}",
                severity="warning",
                timeout=4.0,
            )
        self.transcripts.append(transcript)
        self.transcript_path = write_transcript(audio_path, transcript)
        self.status = "done"
        self._render_all()

    def action_copy_transcript(self) -> None:
        if not self.transcripts:
            self._set_notification("No transcript to copy", severity="warning")
            return
        try:
            copy_text(self.get_joined_transcript())
        except ClipboardError as exc:
            self._set_error(str(exc))
            return
        self._set_notification("Transcript history copied", timeout=2.0)

    def action_undo_last_transcript(self) -> None:
        """Remove the most recent transcript from history or discard error."""
        if self.status == "retry_error":
            self._discard_error()
            return
        if self.status in {"recording", "transcribing"}:
            self._set_notification("Stop recording before undo")
            return
        if not self.transcripts:
            self._set_notification("Nothing to undo")
            return
        self.transcripts.pop()
        if not self.transcripts and self.status in {"done", "retry_error"}:
            self.status = "idle"
        self._render_all()
        self._set_notification("Removed last transcript")

    def _discard_error(self) -> None:
        """Discard retry error and return to idle."""
        self.status = "idle"
        self.error_message = None
        self._render_all()

    def action_rerun_transcription(self) -> None:
        """Rerun transcription on the last recorded audio."""
        if self.status != "retry_error":
            return
        if self.audio_path is None:
            self._set_notification("No audio to rerun", severity="warning")
            return
        self.status = "transcribing"
        self.error_message = None
        self._render_all()
        asyncio.create_task(self._run_transcription())

    def action_confirm_or_restart(self) -> None:
        if (
            self.status == "done"
            and self.settings.stdout_mode
            and self.get_joined_transcript()
        ):
            self.emit_stdout = True
            self.exit_code = 0
            self.exit()
            return
        if self.status == "done" and self.send_config and self.transcripts:
            asyncio.create_task(self._execute_send_and_clear())
            return
        if self.status in {"done", "error", "retry_error"}:
            self.status = "idle"
            self.transcripts.clear()
            self.transcript_path = None
            self.error_message = None
            self._render_all()

    async def _execute_send_and_clear(self) -> None:
        assert self.send_config is not None
        results = await asyncio.to_thread(
            execute_send, self.transcripts, self.send_config
        )
        all_ok = all(ok for ok, _ in results)
        for ok, msg in results:
            if ok:
                self._set_notification(msg, timeout=3.0)
            else:
                self._set_notification(msg, severity="error", timeout=6.0)
        if all_ok:
            self.exit_code = 0
        self.transcripts.clear()
        self.transcript_path = None
        self.error_message = None
        self.status = "idle"
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
