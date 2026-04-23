# sttui desktop keybindings

Toggle background recording from a keyboard shortcut.

```sh
sttui background toggle --clipboard --notify
```

The `--clipboard` flag copies the transcript to clipboard when recording stops. Use `--stdout` instead to write to stdout, or `--send-socket` to send to a socket.

## GNOME

Open **Settings → Keyboard → Custom Shortcuts**, add:

- **Name:** sttui toggle
- **Command:** `sttui background toggle --clipboard --notify`
- **Shortcut:** your preferred key combo

## KDE

Open **System Settings → Shortcuts → Custom Shortcuts**, add:

- **Name:** sttui toggle
- **Command:** `sttui background toggle --clipboard --notify`
- **Trigger:** your preferred key combo

## Hyprland

Add to `~/.config/hypr/hyprland.conf`:

```sh
bind = SUPER, D, exec, sttui background toggle --clipboard --notify
```

## Sway

Add to `~/.config/sway/config`:

```sh
bindsym $mod+d exec sttui background toggle --clipboard --notify
```

## i3

Add to `~/.config/i3/config`:

```sh
bindsym $mod+d exec --no-startup-id sttui background toggle --clipboard --notify
```

## Tips

- Use `--stdout` instead of `--clipboard` if you prefer stdout output.
- Use `--send-socket` to send transcript directly to an agent.
- Remove `--notify` if you prefer silent toggling.
- Use `sttui background start` / `stop` if you want separate bindings.
- Transcripts land in `~/.local/share/sttui/recordings/`.