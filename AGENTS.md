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

## Current Issue: Settings Select Flow (Textual)

There is an active UI regression in the settings flow introduced while adding `:`-driven menus and `Select` widgets for model/device configuration.

### Symptoms Reported

- Opening `:` and selecting `change device` works.
- Reopening `:` and selecting `change model` can auto-apply the current model without explicit user intent.
- The model selector can disappear unexpectedly.
- Reopening `:` may show the root selector already pre-selected (stuck behavior).
- In some terminal/runtime combos, users still report `illegal select value false`.

### Working Theory

The failure pattern strongly suggests a mismatch between Textual `Select` lifecycle and app-level state synchronization:

- Programmatic updates (`set_options`, setting `.value`) can emit `Select.Changed`.
- A hidden `Select` can still be in a problematic value/focus state if not reset cleanly.
- `Select.BLANK` maps to `False` in current Textual behavior, which can conflict with typed select values and trigger `illegal select value false`.
- Transition timing between `ContentSwitcher` current panel changes and immediate select value updates can create transient invalid states.

### Textual Limitations / Sharp Edges

- `Select` is strict about value membership in options.
- Empty options are invalid when blank selection is disallowed.
- `Select.BLANK` sentinel is bool-like (`False`) and may not be type-safe in `Select[str]` style workflows.
- Focus + hidden/disabled select interactions are easy to mishandle when multiple selectors exist in one view.

### Information Needed For A Clean Fix

Capture the following in the failing environment:

1. Textual version (`uv run python -c "import textual; print(textual.__version__)"`).
2. Python version and platform.
3. Exact key sequence and whether arrow keys/Enter or mouse click is used.
4. Full traceback for `illegal select value false` (including file/line in `tui.py`).
5. Runtime logs around settings transitions (current panel, select value before/after `set_options`, and event source user/programmatic).
6. Whether issue reproduces with all models loaded vs only current model option.

### Implementation Direction

The safest target design is:

- Keep three mounted selectors (root/model/device), but gate all non-user updates via explicit event-suppression context.
- Avoid using `Select.BLANK` in typed selectors; use explicit sentinel string options only.
- Reset root selector to sentinel each time menu opens/closes.
- Ensure only the visible selector is enabled/focused; all others disabled.
- Serialize menu transitions so switcher state updates happen before any dependent value writes.
