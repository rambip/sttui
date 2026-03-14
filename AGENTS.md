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

## Textual UI Patterns and Pitfalls

These notes come from implementing settings UI, custom keyboard navigation, and focus management.

### 1) Standalone Settings Widget Pattern

Use a dedicated widget class for settings state and messages rather than putting all logic in `App`.

```python
class SettingsPanel(Static):
    class ModelChanged(Message):
        def __init__(self, model: str) -> None:
            self.model = model
            super().__init__()

    is_open = reactive(False, recompose=True)
```

Why this helps:

- Keeps `App` orchestration simple.
- Encapsulates reactive state + keyboard behavior.
- Sends typed messages to parent for state sync.

### 2) Reactive + Recompose for Mode Switches

For "summary view" vs "interactive menu" in the same area, use a reactive flag with `recompose=True`.

```python
is_open = reactive(False, recompose=True)

def compose(self) -> ComposeResult:
    if not self.is_open:
        yield Static("Settings: ...")
        return
    yield SettingsMenu(...)
```

### 3) Focus After Recompose

When UI is rebuilt (`recompose=True`), focus can be lost. Use `call_after_refresh`.

```python
def set_open(self, open_state: bool) -> None:
    self.is_open = open_state
    if open_state:
        self.call_after_refresh(self.focus_first_control)
```

Also re-focus after async updates that trigger recompose (e.g., after loading models/devices).

### 4) Key Ownership with `inherit_bindings=False`

Some widgets (like `RadioSet`) have default bindings that can conflict with app-level keys (`left/right`, etc.).

```python
class SettingsRadioSet(RadioSet, inherit_bindings=False):
    BINDINGS = [
        Binding("up,k", "previous_button", show=False),
        Binding("down,j", "next_button", show=False),
        Binding("enter,space", "toggle_button", show=False),
    ]
```

Use this when you want deterministic keyboard routing and no inherited surprises.

### 5) Custom Tabs When Built-in Tabs Conflict

If `TabbedContent` focus/binding behavior conflicts with nested controls, keep tabs as simple reactive state.

```python
active_tab = reactive("audio", recompose=True)

def action_next_tab(self) -> None:
    self.active_tab = "models" if self.active_tab == "audio" else "audio"
```

Then conditionally render one pane at a time and focus its primary control.

### 6) Navigation Design Pattern Used Here

- `left/right` (or `h/l`) switch settings category (tab).
- `up/down` (or `k/j`) move inside the active radio list.
- `enter/space` select.
- `escape` closes settings.
- `q` closes settings first, quits app only when settings are already closed.

This keeps keyboard flows predictable in terminal-first UX.

### 7) Rich Style Strings vs Textual CSS

Trap: Rich inline style parsing is stricter than Textual CSS.

- In Textual CSS, `rgb(170, 170, 170)` is valid.
- In `Text(..., style="...")`, prefer hex color literals (`#AAAAAA`) to avoid parse errors.

Example:

```python
Text("[ Audio ]", style="bold black on #78B478")
```

### 8) Dynamic Height / Clipping Trap

If only first items are visible in a long `RadioSet`, container sizing is likely constrained.

Use:

- parent widget: `height: auto` / `min-height` as needed.
- radio list: `height: 1fr; overflow-y: auto;`

This prevents clipped lists while preserving layout.

### 9) Message-based Parent Sync

Keep app runtime settings in parent, send user picks via child messages.

```python
def on_settings_panel_model_changed(self, message: SettingsPanel.ModelChanged) -> None:
    self.current_model = message.model
```

This avoids tight coupling and makes future persistence easier.

## TODO

TODO: add architecture to this file.
