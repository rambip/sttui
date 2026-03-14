# sttui

No browser. No Web UI. Just fast speech-to-text in your terminal.

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
# Recommended: isolated install for CLI tools
pipx install sttui

# Verify install
sttui --help
```

Alternative with pip:

```bash
python -m pip install --user sttui
sttui --help
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

## Commands

```bash
# Show CLI help
uv run sttui --help

# Start interactive dictation TUI
uv run sttui

# TUI + write transcript to stdout on Enter
uv run sttui --stdout

# Override model and recording cap for this run
uv run sttui --model google/gemini-2.5-flash --max-seconds 120

# Use a custom config file
uv run sttui --config ~/.config/sttui/config.toml
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
- `--config <path>`

By default, recordings are stored in `~/.local/share/sttui/recordings/`.

## Development

```bash
uv sync
uv run sttui --help
uv run pytest
```
