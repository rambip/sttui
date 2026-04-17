<div align="center">
  <img src="logo.png" alt="sttui logo" width="300" />

  # `sttui`: Speech To Text in your terminal
  
  **No browser. No Web UI. Fast speech-to-text with the best models**


  [![PyPI version](https://badge.fury.io/py/sttui.svg)](https://badge.fury.io/py/sttui)
</div>


https://github.com/user-attachments/assets/252ba77e-d3f3-4689-bcc1-77f536f10c60


# Setup

```bash
pip install sttui
```

(or if you have `uv` installed, `uvx sttui`)

Then, you must have an account on [openrouter](enrouter.ai/), and get an API key.

To register it, run:

```bash
sttui auth
```

<details>
  <summary>Storage of your key</summary>

  Your key will be stored inside ~/.config/sttui/auth.json
  
  Make sure you don't commit this file !
</details>

# Config

When you first start the app, a config file is created at: `~/.config/sttui/config.toml`

You can specify the default model (without the `openrouter` prefix), the prompt, and the maximum audio length.
```toml
[transcription]
model = "mistralai/voxtral-small-24b-2507"
prompt = """
You are a helpful assistant that can hear audio and write text.
Return a transcription of the user audio as json. If the user request is empty, return null.
<format>
{
  "transcription": ""
}
</format>
<format>
{
  "transcription": null
}
</format>
"""
max_seconds = 600
```

⚠️ Make sure that the prompt asks the model to answer in this json format, it's the one expected by `sttui`

# Commands

```bash

# Start interactive dictation TUI
sttui

# Equivalent explicit run command
sttui run

# Show CLI help
sttui --help

# Set or update API key
sttui auth

# TUI + write transcript to stdout on Enter
sttui --stdout

# Override model and recording cap for this run
sttui --model google/gemini-2.5-flash --max-seconds 120

# Use a custom config file
sttui --config ~/.config/sttui/config.toml

# Record, transcribe, and send to an HTTP endpoint
sttui send --post https://example.com --body '{"text": $0}'

# Send transcript to a shell command
sttui send --command 'xargs -I {} notify-send "{}"'

# Send transcript to a Unix socket (e.g., pi coding agent)
sttui send --socket /run/user/1000/pi/sttui.sock --body '{"message": $0}'

# Chain multiple sends (with 1s delay between them)
sttui send --post https://example.com/foo --body '{"a": $1}' \
           --post https://example.com/bar --body '{}' \
           --delay 1000

# Background lifecycle (no TUI)
sttui background start
sttui background stop
sttui background toggle

# Same with desktop notifications
sttui background --notify start
```

## Send Command Templates

In `--body` templates, use `$0` for the full transcript, `$1`/`$2`/etc. for individual parts.

Values are JSON-escaped automatically when a `--body` template is provided.

All recordings and transcripts are stored in `~/.local/share/sttui/recordings/`.

# Integrations

## pi coding agent

Dictate directly into pi using sttui's socket integration.

Copy the extension to your pi extensions folder:

```bash
mkdir -p ~/.pi/agent/extensions
cp integrations/pi.ts ~/.pi/agent/extensions/sttui.ts
```

After starting pi, you'll see the sttui command in the chat.

# Contributing

This is a side-project of mine. I must admit there is mostly AI-generated code, but I try to review and ensure good practices.

I don't have strong opinions about how this project should evolve. If you find it useful, feel free to contribute !
