# Architecture

`sttui` is a Linux-first speech-to-text terminal UI. It records audio, sends it to OpenRouter for transcription, and presents results in a Textual TUI.

## Package Layout

All source lives under `src/sttui/`.

| File | Role |
|------|------|
| `__init__.py` | Package metadata; exposes `__version__` from installed distribution. |
| `cli.py` | CLI entrypoint (`main`). Parses args, dispatches to subcommands (`run`, `auth`, `background`, `send`). Lazy-imports heavy modules (TUI, recording, transcribe) only when needed. |
| `tui.py` | Textual `App` (`SttuiApp`) and supporting widgets (`SettingsPanel`, `StatusFooter`, `SettingsRadioSet`, `SettingsDataTable`). Manages recording state machine (idle → recording → transcribing → done/error), keyboard bindings, and sends settings changes via child messages. |
| `config.py` | Config/auth file loading. Defines `RuntimeSettings` dataclass. Reads TOML config from `~/.config/sttui/config.toml` and API key from `~/.config/sttui/auth.json`. Applies CLI overrides. |
| `default_config.toml` | Shipped default config template (copied on first run). Sets model, transcription prompt, and JSON output format. |
| `recording.py` | `RecorderSession` — threaded WAV recorder using `sounddevice`. Computes RMS power for UI meter. `list_input_devices()` enumerates input hardware. |
| `transcribe.py` | OpenRouter client. `build_payload()` constructs the chat-completion request with base64 audio. `transcribe_audio()` sends the request and parses the JSON transcript. `list_audio_models()` fetches models that accept audio input. Handles JSON-in-markdown-fence extraction. |
| `send.py` | `SendConfig` / `SendTarget` dataclasses. `execute_send()` runs a sequence of HTTP POST requests and/or shell commands, piping transcript bodies. `format_body()` substitutes `$0`/`$1`/`$2` placeholders with JSON-escaped transcript parts. |
| `storage.py` | Path helpers. `next_audio_path()` generates timestamped `.wav` filenames. `write_transcript()` saves the `.txt` sidecar file. |
| `clipboard.py` | Thin wrapper around the `clipboard` package for copy-to-clipboard. |
| `notifications.py` | Thin wrapper around `notify-py` for desktop notifications (used by background mode). |
| `errors.py` | Custom exception hierarchy: `SttuiError` → `ConfigError`, `RecordingError`, `TranscriptionError`, `ClipboardError`. |
| `background.py` | Background recording lifecycle. `start_background()` spawns a detached worker subprocess. `stop_background()` sends SIGTERM. `toggle_background()` does one or the other. `run_background_worker()` is the long-running loop: records, transcribes, copies to clipboard. State is persisted as JSON in XDG_RUNTIME_DIR. |

## Tests

Located in `tests/`. Target fragile behavior only (config parsing, payload building, response parsing, path/naming logic, send body formatting, background state round-trips).

| File | Tests |
|------|-------|
| `test_config.py` | Auth loading, missing/empty key errors, defaults, CLI overrides, non-positive max_seconds. |
| `test_transcribe.py` | Payload structure, transcript parsing (string, chunk, markdown-fenced, null, invalid), model listing (filtering, HTTP errors, API key errors, network errors). |
| `test_storage.py` | Timestamped audio path generation, transcript sidecar path derivation. |
| `test_send.py` | `format_body` with no template, `$0`, `$1`/`$2` positional, mixed, missing index, single/empty parts. |
| `test_background.py` | State JSON read/write round-trip, stale PID cleanup. |

## Data Flow

```
User presses Space
  → tui.py starts RecorderSession (recording.py)
  → User presses Space again
  → tui.py calls transcribe_audio (transcribe.py)
    → encode audio to base64
    → POST to OpenRouter chat completions API
    → parse JSON response → extract "transcription" field
  → tui.py appends transcript to history
  → storage.py writes .txt sidecar file
  → if --stdout: write joined transcript to stdout and exit
  → if send mode: execute_send posts/commands with transcript
```

## Background Mode

```
sttui background start
  → background.py spawns: sttui __background_worker ...
  → child process records until SIGTERM or max_seconds
  → transcribes, writes .txt, copies to clipboard
  → state file (JSON in XDG_RUNTIME_DIR) tracks PID and audio path
sttui background stop
  → reads state file, sends SIGTERM to child PID
```
