"""CLI entrypoint for sttui."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sttui.config import (
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
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

    if app.emit_stdout and app.transcript:
        sys.stdout.write(app.transcript)
        if not app.transcript.endswith("\n"):
            sys.stdout.write("\n")

    return app.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
