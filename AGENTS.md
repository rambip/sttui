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
```

Why this helps:

- Keeps `App` orchestration simple.
- Encapsulates state + keyboard behavior.
- Sends typed messages to parent for state sync.

### 2) CRITICAL: `recompose=True` Destroys ContentSwitcher State

**Never use `recompose=True` on a reactive that changes while a `ContentSwitcher` is
open.** Recompose tears down and recreates all child widgets, including the
`ContentSwitcher` itself, which resets to its `initial=` pane — silently undoing
any `.current` assignment you made just before.

**Minimal reproducer:**

```python
class BrokenPanel(Static):
    current_tab = reactive("a", recompose=True)   # BUG

    def compose(self) -> ComposeResult:
        with ContentSwitcher(initial="a"):         # always resets to "a"
            yield Static("Pane A", id="a")
            yield Static("Pane B", id="b")

    def show_b(self) -> None:
        self.current_tab = "b"                    # triggers recompose...
        self.query_one(ContentSwitcher).current = "b"  # ...set on old widget,
                                                       # then overwritten by recompose
```

After `show_b()`, the widget shows Pane A, not Pane B.

**Fix: don't recompose. Populate children imperatively, switch via `.current`.**

```python
class FixedPanel(Static):
    def compose(self) -> ComposeResult:
        with ContentSwitcher(initial="a"):
            yield Static("Pane A", id="a")
            yield Static("Pane B", id="b")   # always composed, never rebuilt

    def show_b(self) -> None:
        self.query_one(ContentSwitcher).current = "b"  # direct, no recompose
```

For dynamic children (e.g. radio buttons loaded async), use
`widget.remove_children()` + `widget.mount(...)` instead of recompose.

### 3) Focus After ContentSwitcher Switch

After calling `.current = "..."`, focus the primary control with
`call_after_refresh` to let the layout settle first.

```python
def show_b(self) -> None:
    self.query_one(ContentSwitcher).current = "b"
    self.call_after_refresh(lambda: self.query_one("#b").focus())
```

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

### 5) Use ContentSwitcher for Multi-Pane Settings

Use `ContentSwitcher` with one fixed pane per view. Switch by setting `.current`
directly. This avoids all recompose issues and keeps each pane's widget state
intact (scroll position, focus, etc.) between visits.

```python
with ContentSwitcher(initial="summary"):
    yield DataTable(id="summary")
    with Vertical(id="audio"):
        yield SettingsRadioSet(id="audio_radio")
    with Vertical(id="models"):
        yield SettingsRadioSet(id="model_radio")
```

Populate radio buttons once via `mount()` when data arrives; re-populate on
subsequent opens with `remove_children()` + `mount()`.

### 6) Navigation Design Pattern Used Here

- `up/down` (or `k/j`) move inside the active radio list.
- `enter/space` select.
- `escape` closes settings, returns focus to the summary DataTable.
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
