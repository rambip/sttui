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
from sttui.tui import SttuiApp


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

    parser.set_defaults(command="run")
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
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "auth":
        return cmd_auth()

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

    app = SttuiApp(settings=settings)
    app.run()

    if app.last_error_for_stderr:
        print(f"Error: {app.last_error_for_stderr}", file=sys.stderr)

    if app.emit_stdout and app.transcripts:
        output = "\n\n".join(app.transcripts)
        sys.stdout.write(output)
        if not output.endswith("\n"):
            sys.stdout.write("\n")

    return app.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
