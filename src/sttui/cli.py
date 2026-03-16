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
    load_runtime_settings,
)
from sttui.errors import ConfigError


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

    subparsers = parser.add_subparsers(dest="command", required=False)

    subparsers.add_parser(
        "auth",
        help="Register your OpenRouter API key",
    )

    subparsers.add_parser(
        "run",
        help="Run the TUI (default)",
    )

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
    return parser


def cmd_auth() -> int:
    print("Visit openrouter to create an API key:")
    print("https://openrouter.ai/settings/keys\n")
    print("Then, paste your API key below and press Enter.\n")
    api_key = input("API key: ").strip()

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
            api_key = load_api_key(auth_path=DEFAULT_AUTH_PATH)
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
        return run_background_worker(
            state_path=args.state_path,
            audio_path=args.audio_path,
            settings=settings,
            notify=args.notify,
        )

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "auth":
        return cmd_auth()

    if args.command == "background":
        # Lazy import: background lifecycle commands don't need TUI modules.
        from sttui.background import (
            start_background,
            stop_background,
            toggle_background,
        )

        if args.action == "stop":
            code, message = stop_background(notify=args.notify)
        else:
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
            if args.action == "start":
                code, message = start_background(settings, notify=args.notify)
            else:
                code, message = toggle_background(settings, notify=args.notify)
        stream = sys.stdout if code == 0 else sys.stderr
        print(message, file=stream)
        return code

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

    app = SttuiApp(settings=settings)
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
