# sttui Roadmap

## Motivation

`sttui` exists to make speech-to-text fast in terminal-first workflows.

The project goal is a small, dependable Linux-first tool that:

- records short speech from the microphone,
- shows clear interactive state in a TUI,
- transcribes through OpenRouter,
- and can hand transcript text to shell scripts through stdout when requested.

Design priorities:

- small surface area, good defaults, low setup friction,
- predictable behavior in scripting contexts,
- concise errors and recoverable failure modes,
- extension points for future streaming backends.

Cross-platform support is explicitly out of scope for now.

## Product Scope

### V1 (MVP): One-shot dictation

Core flow:

1. Open TUI.
2. Start recording.
3. Stop recording.
4. Save audio.
5. Transcribe via OpenRouter.
6. Show transcript in TUI.
7. Optionally copy to clipboard or emit to stdout (in stdout mode).

### V2 (Extensions)

- Streaming transcription mode (incremental text updates).
- Backend abstraction to support `openrouter` + `google-stream`.
- Optional headless/no-TUI mode for pure automation.
- Better history/search UX for prior recordings and transcripts.

## UX and Interaction

### Keybindings

- `space`: toggle record/stop.
- `r`: toggle record/stop.
- `s`: explicit stop recording.
- `c`: copy transcript to clipboard.
- `Enter`:
  - normal mode: start a new recording cycle,
  - `--stdout` mode: write transcript to stdout and exit.
- `q`: quit/cancel (no stdout output).

### Modes

Default mode:

- transcript is shown in TUI,
- no automatic stdout output,
- user can loop into another recording with `Enter`.

`--stdout` mode:

- still uses interactive TUI for recording and transcript preview,
- after successful transcription, prompt: "Press Enter to write transcript to stdout and exit",
- `q` exits without writing transcript to stdout.

### Recording Animation

- A large breathing ASCII circle animation during recording,
- target visual size around half terminal height,
- graceful fallback to simpler animation if terminal dimensions are small.

## Configuration

Location:

- `~/.config/sttui/config.toml`

Schema (sectioned TOML):

```toml
[openrouter]
api_key = "or-..."

[transcription]
model = "google/gemini-2.5-flash"
prompt = "Please transcribe this audio file."
max_seconds = 600
```

Behavior:

- `openrouter.api_key` is required.
- `transcription.model` defaults to `google/gemini-2.5-flash`.
- `transcription.prompt` defaults to "Please transcribe this audio file.".
- `transcription.max_seconds` defaults to `600` seconds.
- CLI values override config values.

If config is missing/invalid, show concise guidance with exact config path and expected key names.

## CLI Contract (V1)

Planned flags:

- `--stdout` (TUI + Enter-to-stdout-and-exit flow)
- `--model <name>` (override configured model)
- `--max-seconds <int>` (override recording cap)
- `--debug` (diagnostic details on stderr)

`--help` should explicitly mention:

- config path: `~/.config/sttui/config.toml`
- default recording storage: `~/.local/share/sttui/recordings/`

## Audio and Persistence

Recorder:

- use `pw-record` (Linux-first by design).
- WAV output for V1.

Limits:

- no explicit file-size limit,
- default recording duration cap: 10 minutes (`600s`), configurable.

Storage:

- save by default to: `~/.local/share/sttui/recordings/`
- single-folder storage strategy for V1,
- save both:
  - audio file (`.wav`)
  - transcript file (`.txt`) on successful transcription.

File naming recommendation:

- timestamp-based base name, e.g. `sttui-YYYYMMDD-HHMMSS.wav` and `.txt`.

User feedback:

- always show where audio/transcript was saved,
- on network/API failure, include saved audio path in the error.

## API Integration

Endpoint:

- `POST https://openrouter.ai/api/v1/chat/completions`

Transport:

- `requests` for HTTP,
- base64-encoded WAV sent as `input_audio` in chat message content.

Model:

- default: `google/gemini-2.5-flash`,
- override by config and CLI.

Prompt:

- use configured prompt when present,
- otherwise use default transcription prompt,
- preserve transcript text as returned (no post-cleaning in V1).

## Error Handling and Exit Behavior

Output policy:

- keep stdout clean unless transcript is intentionally written there,
- send errors/diagnostics to stderr.

Failure examples:

- missing API key/config,
- recorder invocation failure,
- network timeout/error,
- non-2xx API responses,
- malformed API response.

Error style:

- concise, actionable, path-aware.
- example: `network error, audio saved in /home/user/.local/share/sttui/recordings/sttui-...wav`

Exit codes:

- `0` success,
- non-zero for cancel/failure (important for scripting).

## Architecture

### High-level components

1. **CLI Layer**
   - parse flags,
   - load config,
   - construct runtime settings.

2. **TUI Layer (Textual)**
   - render recording states,
   - animate recording indicator,
   - handle keybindings,
   - display transcript/errors and mode-specific instructions.

3. **Recorder Adapter**
   - invoke `pw-record`,
   - enforce max duration,
   - return audio file path and metadata.

4. **Transcription Client**
   - encode WAV to base64,
   - build OpenRouter payload,
   - parse response text,
   - map API errors into concise app errors.

5. **Persistence Service**
   - create recordings directory,
   - generate timestamp filenames,
   - write `.wav` and `.txt` outputs.

6. **Clipboard Service**
   - try `wl-copy`, fallback `xclip`,
   - produce clear error if neither is available.

### Data flow

1. startup -> config load -> CLI overrides,
2. TUI idle -> user records -> recorder saves WAV,
3. WAV path -> transcription client -> transcript text,
4. transcript -> TUI display,
5. optional copy/stdout,
6. persist transcript file when transcription succeeds.

## Development and Packaging

- project and task runner: `uv`
- target: installable CLI package (`sttui` command)
- license: MIT

Initial suggested structure:

- `src/sttui/cli.py`
- `src/sttui/config.py`
- `src/sttui/tui.py`
- `src/sttui/recording.py`
- `src/sttui/transcribe.py`
- `src/sttui/storage.py`
- `src/sttui/clipboard.py`
- `tests/` (minimal)

## Testing Strategy (Minimal V1)

Only add unit tests where they prevent fragile behavior:

- config parsing/validation defaults and overrides,
- payload construction for OpenRouter request,
- response parsing and error mapping,
- filename generation and storage path behavior.

Avoid heavy integration test matrix in V1.

## Milestones

### M1 - Skeleton

- `uv` project setup,
- installable `sttui` entrypoint,
- config loader + concise validation errors,
- basic TUI shell and key handling.

### M2 - Recording + Persistence

- `pw-record` integration,
- max duration enforcement,
- save WAV to default recordings folder,
- show save path in UI/help.

### M3 - Transcription

- OpenRouter request/response implementation,
- model/prompt support from config + CLI override,
- transcript display and `.txt` persistence.

### M4 - UX Completion

- `--stdout` Enter-to-output flow,
- copy-to-clipboard key,
- large breathing circle animation,
- concise failure states and exit codes.

### M5 - Polish and Release

- `--help` completeness,
- targeted unit tests,
- README quickstart,
- MIT license and initial release tag.

## Risks and Mitigations

- **Terminal rendering variance**: provide fallback animation for small or slow terminals.
- **Clipboard utility absence**: detect and message clearly (`wl-copy`/`xclip` missing).
- **Network/API instability**: keep saved audio, concise retry-friendly errors.
- **Disk growth from always-save policy**: defer retention policy to V2.
