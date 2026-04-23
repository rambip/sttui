# sttui + AI coding agents

Dictate directly into coding agents via sttui's `send` command.

## OpenCode

Export the server URL once so every command below picks it up:

```sh
export OPENCODE_URL=http://localhost:4096
```

Start the agent server:

```sh
opencode serve
```

In another terminal, attach to it:

```sh
opencode attach $OPENCODE_URL
```

### Send dictation as a prompt

Pipe your spoken transcript straight into the agent's prompt input:

```sh
sttui run \
  --send-post $OPENCODE_URL/tui/append-prompt \
  --send-body '{"text": $0}'
```

Or use background recording with toggle:

```sh
sttui background toggle \
  --send-post $OPENCODE_URL/tui/append-prompt \
  --send-body '{"text": $0}' \
  --send-post $OPENCODE_URL/tui/submit-prompt
```

- The first POST appends your transcript to the prompt.
- The second POST submits the prompt.
- Both fire in sequence after a single dictation.

### Tips

- Add `--send-delay 500` if you have multiple --send-post and need a moment between the two requests.
- Use `sttui run` or `sttui background` with `--send-command` to pipe transcripts into other CLI agents.

## pi

Copy the extension to your pi extensions folder:

```sh
mkdir -p ~/.pi/agent/extensions
cp integrations/pi.ts ~/.pi/agent/extensions/sttui.ts
```

After starting pi, run `/sttui` to see the available commands.

### Send dictation

Dictate while pi is running. The transcript is sent to pi via a Unix socket.

```sh
sttui run --send-socket ~/.local/share/sttui/sttui.sock --send-body '{"message": $0, "deliverAs": "steer"}'
```

- `deliverAs: "steer"` — delivered after the current tool finishes, before the next LLM call
- `deliverAs: "followUp"` — waits until pi is completely idle before processing

The socket path is shown when you run `/sttui` in pi.

See also: https://github.com/rambip/sttui/tree/main/integrations/pi.ts