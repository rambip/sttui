"""CLI entrypoint for sttui."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sttui.config import (
    DEFAULT_AUTH_PATH,
    DEFAULT_CONFIG_PATH,
    DEFAULT_RECORDINGS_DIR,
    NeedMigrationError,
    find_auth_path,
    is_interactive,
    load_runtime_settings,
)
from sttui.errors import ConfigError
from sttui.send import SendConfig, SendTarget


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sttui",
        description="Linux-first speech-to-text terminal UI.",
        epilog=(
            f"config path: {DEFAULT_CONFIG_PATH} | "
            f"auth path: {DEFAULT_AUTH_PATH} | "
            f"default recordings: {DEFAULT_RECORDINGS_DIR}"
        ),
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Use TUI, then Enter writes transcript to stdout and exits.",
    )
    parser.add_argument(
        "--model",
        help=(
            "Override configured transcription model using <provider/model> "
            "(for example: google/gemini-2.5-flash). Do not prefix with openrouter/."
        ),
    )
    parser.add_argument(
        "--max-seconds",
        type=int,
        help="Override recording duration cap in seconds.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print diagnostics to stderr.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to config file (default: {DEFAULT_CONFIG_PATH}).",
    )

    # Send arguments (usable by run, background, etc.)
    parser.add_argument(
        "--send-post",
        action="append",
        default=[],
        metavar="URL",
        help="HTTP POST endpoint (can be repeated, sends done in sequence)",
    )
    parser.add_argument(
        "--send-command",
        dest="send_commands",
        action="append",
        default=[],
        metavar="CMD",
        help="Shell command to pipe transcript to (can be repeated, run in sequence)",
    )
    parser.add_argument(
        "--send-socket",
        action="append",
        default=[],
        metavar="PATH",
        help="Unix socket path to send to (can be repeated, sends done in sequence)",
    )
    parser.add_argument(
        "--send-body",
        action="append",
        default=[],
        metavar="FMT",
        help="JSON body template for associated --send-post/--send-socket. "
             "Sets Content-Type to JSON. In the template, $0 is replaced by the transcript.",
    )
    parser.add_argument(
        "--send-delay",
        type=int,
        default=None,
        metavar="MS",
        help="When multiple --send-post or --send-socket in sequence, set delay (ms) between sends",
    )

    subparsers = parser.add_subparsers(dest="command", required=False)

    subparsers.add_parser(
        "auth",
        help="Register your OpenRouter API key",
    )

    # Run subcommand
    run_parser = subparsers.add_parser(
        "run",
        help="Run the TUI (default)",
    )
    # Send arguments for run subcommand
    run_parser.add_argument(
        "--send-post",
        action="append",
        default=[],
        metavar="URL",
        help="HTTP POST endpoint (can be repeated, sends done in sequence)",
    )
    run_parser.add_argument(
        "--send-command",
        dest="send_commands",
        action="append",
        default=[],
        metavar="CMD",
        help="Shell command to pipe transcript to (can be repeated, run in sequence)",
    )
    run_parser.add_argument(
        "--send-socket",
        action="append",
        default=[],
        metavar="PATH",
        help="Unix socket path to send to (can be repeated, sends done in sequence)",
    )
    run_parser.add_argument(
        "--send-body",
        action="append",
        default=[],
        metavar="FMT",
        help="JSON body template for associated --send-post/--send-socket. "
             "Sets Content-Type to JSON. In the template, $0 is replaced by the transcript.",
    )
    run_parser.add_argument(
        "--send-delay",
        type=int,
        default=None,
        metavar="MS",
        help="When multiple --send-post or --send-socket in sequence, set delay (ms) between sends",
    )

    # Background recording subcommand
    background_parser = subparsers.add_parser(
        "background",
        help="Control background recording lifecycle",
    )
    background_parser.add_argument(
        "action",
        choices=["start", "stop", "toggle"],
        help="Background action to execute",
    )
    background_parser.add_argument(
        "--notify",
        action="store_true",
        help="Send desktop notifications for background events.",
    )
    background_parser.add_argument(
        "--clipboard",
        action="store_true",
        help="Copy transcript to clipboard (default behavior).",
    )
    background_parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write transcript to stdout.",
    )
    # Send arguments for background subcommand
    background_parser.add_argument(
        "--send-post",
        action="append",
        default=[],
        metavar="URL",
        help="HTTP POST endpoint (can be repeated, sends done in sequence)",
    )
    background_parser.add_argument(
        "--send-command",
        dest="send_commands",
        action="append",
        default=[],
        metavar="CMD",
        help="Shell command to pipe transcript to (can be repeated, run in sequence)",
    )
    background_parser.add_argument(
        "--send-socket",
        action="append",
        default=[],
        metavar="PATH",
        help="Unix socket path to send to (can be repeated, sends done in sequence)",
    )
    background_parser.add_argument(
        "--send-body",
        action="append",
        default=[],
        metavar="FMT",
        help="JSON body template for associated --send-post/--send-socket. "
             "Sets Content-Type to JSON. In the template, $0 is replaced by the transcript.",
    )
    background_parser.add_argument(
        "--send-delay",
        type=int,
        default=None,
        metavar="MS",
        help="When multiple --send-post or --send-socket in sequence, set delay (ms) between sends",
    )

    recipes_parser = subparsers.add_parser(
        "recipes",
        help="Show practical recipes for using sttui",
    )
    recipes_sub = recipes_parser.add_subparsers(dest="recipe", required=False)

    from sttui.recipes import list_recipes
    for recipe in list_recipes():
        recipes_sub.add_parser(
            recipe,
            help=f"Show {recipe} recipe",
        )

    parser.set_defaults(command="run")
    return parser


def build_background_worker_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sttui __background_worker")
    parser.add_argument("--state-path", type=Path, required=True)
    parser.add_argument("--audio-path", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--max-seconds", type=int, required=True)
    parser.add_argument("--recordings-dir", type=Path, required=True)
    parser.add_argument("--input-device", type=int)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--notify", action="store_true")
    parser.add_argument(
        "--send-config",
        type=str,
        default=None,
        help="JSON-serialized SendConfig for background worker",
    )
    parser.add_argument(
        "--output-clipboard",
        type=str,
        default="1",
        help="Whether to copy transcript to clipboard (0 or 1)",
    )
    parser.add_argument(
        "--output-stdout",
        type=str,
        default="0",
        help="Whether to write transcript to stdout (0 or 1)",
    )
    return parser


def cmd_auth() -> int:
    import getpass

    print("Visit openrouter to create an API key:")
    print("https://openrouter.ai/settings/keys\n")
    print("Then, paste your API key below and press Enter.\n")
    print("(Use Shift+Insert to paste without echoing)\n")
    api_key = getpass.getpass("API key: ").strip()

    if not api_key:
        print("No API key provided.", file=sys.stderr)
        return 1

    auth_path = DEFAULT_AUTH_PATH
    auth_path.parent.mkdir(parents=True, exist_ok=True)

    data = {"openrouter": {"api_key": api_key}}
    with auth_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"\nAPI key saved to {auth_path}")
    print("You can now start sttui!")
    return 0


def _print_md(text: str) -> None:
    from rich.console import Console
    from rich.markdown import Markdown

    console = Console(highlight=False)
    console.print(Markdown(text))
    console.print()
    console.rule(style="dim")


def _load_recipe(name: str) -> str:
    """Load a recipe markdown file by name."""
    from sttui.recipes import load_recipe
    return load_recipe(name)


def cmd_recipes_index() -> int:
    from sttui.recipes import get_index_markdown
    _print_md(get_index_markdown())
    return 0


def cmd_recipes_agents() -> int:
    _print_md(_load_recipe("agents"))
    return 0
def cmd_recipes_desktop() -> int:
    _print_md(_load_recipe("desktop"))
    return 0
def _build_send_config(args: argparse.Namespace) -> SendConfig | None:
    """Build SendConfig from send-* arguments."""
    targets: list[SendTarget] = []
    bodies = args.send_body or []
    body_idx = 0

    for url in args.send_post:
        body = bodies[body_idx] if body_idx < len(bodies) else None
        if body:
            body_idx += 1
        targets.append(SendTarget(kind="post", target=url, body=body))

    for sock_path in args.send_socket:
        body = bodies[body_idx] if body_idx < len(bodies) else None
        if body:
            body_idx += 1
        targets.append(SendTarget(kind="socket", target=sock_path, body=body))

    for cmd in args.send_commands:
        targets.append(SendTarget(kind="command", target=cmd, body=None))

    if not targets:
        return None

    return SendConfig(targets=targets, delay_ms=args.send_delay)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    if argv and argv[0] == "__background_worker":
        # Lazy import: this internal worker path is background-only.
        # Keeping imports local avoids pulling recording/transcribe deps
        # during normal CLI startup.
        args = build_background_worker_parser().parse_args(argv[1:])
        from sttui.background import run_background_worker
        from sttui.config import RuntimeSettings, load_api_key

        try:
            auth_path, _ = find_auth_path(interactive=False)
            api_key = load_api_key(auth_path=auth_path)
        except ConfigError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        settings = RuntimeSettings(
            api_key=api_key,
            model=args.model,
            prompt=args.prompt,
            max_seconds=args.max_seconds,
            input_device=args.input_device,
            recordings_dir=args.recordings_dir,
            stdout_mode=False,
            debug=args.debug,
        )

        # Deserialize send_config if provided
        send_config = None
        if args.send_config:
            import dataclasses
            import json

            data = json.loads(args.send_config)
            targets = [
                SendTarget(
                    kind=t["kind"],
                    target=t["target"],
                    body=t.get("body"),
                )
                for t in data.get("targets", [])
            ]
            send_config = SendConfig(targets=targets, delay_ms=data.get("delay_ms"))

        output_clipboard = args.output_clipboard == "1"
        output_stdout = args.output_stdout == "1"

        return run_background_worker(
            state_path=args.state_path,
            audio_path=args.audio_path,
            settings=settings,
            notify=args.notify,
            send_config=send_config,
            output_clipboard=output_clipboard,
            output_stdout=output_stdout,
        )

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "auth":
        return cmd_auth()

    if args.command == "recipes":
        if args.recipe:
            _print_md(_load_recipe(args.recipe))
        else:
            cmd_recipes_index()
        return 0

    if args.command == "background":
        # Lazy import: background lifecycle commands don't need TUI modules.
        from sttui.background import (
            start_background,
            stop_background,
            toggle_background,
        )

        # Build send config for background actions
        send_config = _build_send_config(args)

        # Count output options for validation
        output_count = 0
        if args.clipboard:
            output_count += 1
        if args.stdout:
            output_count += 1
        send_targets_count = len(args.send_post) + len(args.send_socket) + len(args.send_commands)
        output_count += send_targets_count

        if args.action == "stop":
            # stop doesn't need output options, but we don't error if provided
            code, message = stop_background(notify=args.notify)
        elif args.action == "start":
            # start requires exactly 1 output option
            if output_count != 1:
                print(
                    "Error: exactly one output option is required "
                    "(--clipboard, --stdout, --send-post, --send-socket, or --send-command)",
                    file=sys.stderr,
                )
                return 2
            try:
                settings = load_runtime_settings(
                    config_path=args.config,
                    model_override=args.model,
                    max_seconds_override=args.max_seconds,
                    stdout_mode=False,
                    debug=args.debug,
                )
            except ConfigError as exc:
                print(str(exc), file=sys.stderr)
                return 2
            code, message = start_background(
                settings,
                notify=args.notify,
                send_config=send_config,
                output_clipboard=args.clipboard,
                output_stdout=args.stdout,
            )
        else:  # toggle
            # toggle also requires exactly 1 output option
            if output_count != 1:
                print(
                    "Error: exactly one output option is required "
                    "(--clipboard, --stdout, --send-post, --send-socket, or --send-command)",
                    file=sys.stderr,
                )
                return 2
            try:
                settings = load_runtime_settings(
                    config_path=args.config,
                    model_override=args.model,
                    max_seconds_override=args.max_seconds,
                    stdout_mode=False,
                    debug=args.debug,
                )
            except ConfigError as exc:
                print(str(exc), file=sys.stderr)
                return 2
            code, message = toggle_background(
                settings,
                notify=args.notify,
                send_config=send_config,
                output_clipboard=args.clipboard,
                output_stdout=args.stdout,
            )
        stream = sys.stdout if code == 0 else sys.stderr
        print(message, file=stream)
        return code

    # Build send config for run command (or default)
    send_config = _build_send_config(args)

    # Check for auth migration (interactive mode only)
    interactive = is_interactive()
    if interactive:
        try:
            auth_path, _ = find_auth_path(interactive=True)
        except NeedMigrationError as exc:
            print(
                f"\nMigration needed: sttui now stores auth at {exc.new}\n"
                f"Legacy auth found at {exc.legacy}\n",
                file=sys.stderr,
            )
            response = input("Move auth file to new location? [Y/n]: ").strip().lower()
            if response in ("", "y", "yes"):
                # Check if new path already exists
                if exc.new.exists():
                    print(
                        f"Error: {exc.new} already exists. Please resolve manually.\n",
                        file=sys.stderr,
                    )
                    return 1
                # Create directory and move file
                exc.new.parent.mkdir(parents=True, exist_ok=True)
                exc.legacy.rename(exc.new)
                print(f"Moved auth to {exc.new}", file=sys.stderr)
            else:
                # User said no - continue with legacy (silently)
                print("Using legacy auth location.", file=sys.stderr)
    else:
        # Non-interactive: check legacy, print warning if using it
        _, using_legacy = find_auth_path(interactive=False)

    try:
        settings = load_runtime_settings(
            config_path=args.config,
            model_override=args.model,
            max_seconds_override=args.max_seconds,
            stdout_mode=args.stdout,
            debug=args.debug,
        )
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    # Lazy import: loading the Textual app is expensive, so only import it
    # for the foreground run path.
    from sttui.tui import SttuiApp

    app = SttuiApp(settings=settings, send_config=send_config)
    app.run()

    if app.last_error_for_stderr:
        print(f"Error: {app.last_error_for_stderr}", file=sys.stderr)

    output = app.get_joined_transcript()
    if app.emit_stdout and output:
        sys.stdout.write(output)
        if not output.endswith("\n"):
            sys.stdout.write("\n")

    return app.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
