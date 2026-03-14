# AGENTS

## What This Project Is

`sttui` is a small Linux-first speech-to-text terminal application written in Python.

- It records audio using `pw-record`.
- It provides an interactive Textual TUI while recording/transcribing.
- It sends audio to OpenRouter for transcription.
- It can write transcript text to stdout for scripting workflows.

This project intentionally prioritizes a minimal, reliable one-shot dictation experience in V1, with streaming and backend extensions later.

## Link to Roadmap

See `ROADMAP.md` for product scope, milestones, and implementation details.

## Code Style Considerations

These conventions are inferred from project goals and current decisions:

- Keep the codebase small and modular; avoid premature abstraction.
- Prefer explicit, readable control flow over cleverness.
- Keep user-facing messages concise and actionable.
- Keep stdout clean unless transcript output is explicitly requested.
- Send errors and diagnostics to stderr.
- Preserve transcript text as returned by the model in V1 (no cleanup transforms).
- Use pragmatic defaults with config/CLI override support.
- Keep Linux-first assumptions explicit (do not add cross-platform complexity in V1).
- Design TUI behavior around quick keyboard workflows and predictable state transitions.
- Keep failure handling path-aware (especially saved recording paths).

## Development Conventions

- Use `uv` for environment and task management.
- Keep dependencies lightweight.
- Add unit tests only where they protect fragile behavior (config parsing, payload building, response parsing, path/naming logic).
- Favor timestamped, deterministic file naming for saved outputs.
- Keep CLI contract stable and intentionally small.

## TODO

TODO: add architecture to this file.
