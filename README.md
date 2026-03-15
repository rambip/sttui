<div align="center">
  <img src="logo.png" alt="sttui logo" width="300" />

  # `sttui`: Speech To Text in your terminal
  
  **No browser. No Web UI. Fast speech-to-text with the best models**


  [![PyPI version](https://badge.fury.io/py/sttui.svg)](https://badge.fury.io/py/sttui)
</div>



# Setup

```
pip install sttui
```

(or if you have `uv` installed, `uvx sttui`)

Then, you must have an account on [openrouter](enrouter.ai/), and get an API key.

When you first start the app, you will be prompted for it.

<details>
  <summary>Storage of your key</summary>

  Your key will be stored inside ~/.config/sttui/config.toml
  Make sure you don't commit this file !
</details>

# Config

When you first start the app, a config file is created at:  `~/.config/sttui/config.toml`

You can specify the default model (without the `openrouter` prefix), the prompt, and the maximum audio length.
```toml
[transcription]
model = "google/gemini-2.5-flash"
prompt = "Please transcribe this audio file."
max_seconds = 600
```

# Commands

```bash

# Start interactive dictation TUI
sttui

# Show CLI help
sttui --help

# TUI + write transcript to stdout on Enter
sttui --stdout

# Override model and recording cap for this run
sttui --model google/gemini-2.5-flash --max-seconds 120

# Use a custom config file
sttui --config ~/.config/sttui/config.toml
```

All recordings and transcripts are stored in `~/.local/share/sttui/recordings/`.

# Contributing

This is a side-project of mine. I must admit there is mostly AI-generated code, but I try to review and ensure good practices.

I don't have strong opinions about how this project should evolve. If you find it useful, feel free to contribute !
