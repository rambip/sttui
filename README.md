# sttui

Linux-first speech-to-text terminal UI for fast one-shot dictation.

## Features

- Records audio with `pw-record`.
- Shows an interactive Textual TUI with record/transcribe states.
- Sends WAV audio to OpenRouter as `input_audio`.
- Saves `.wav` and `.txt` outputs in a timestamped naming scheme.
- Supports `--stdout` mode for script-friendly output.

## Requirements

- Linux with PipeWire (`pw-record`)
- Python 3.11+
- OpenRouter API key
- Optional clipboard tools: `wl-copy` or `xclip`

## Install

```bash
uv sync
uv run sttui --help
```

## Config

Create `~/.config/sttui/config.toml`:

```toml
[openrouter]
api_key = "or-..."

[transcription]
model = "google/gemini-2.5-flash"
prompt = "Please transcribe this audio file."
max_seconds = 600
```

## Usage

```bash
uv run sttui
```

Keybindings:

- `space` / `r`: toggle record/stop
- `s`: stop recording
- `c`: copy transcript
- `Enter`: new cycle (or stdout confirm in `--stdout` mode)
- `q`: quit

CLI flags:

- `--stdout`
- `--model <name>`
- `--max-seconds <int>`
- `--debug`

By default, recordings are stored in `~/.local/share/sttui/recordings/`.

## Development

```bash
uv run pytest
```
