"""Config loading and runtime settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tomllib

from sttui.errors import ConfigError

DEFAULT_MODEL = "google/gemini-2.5-flash"
DEFAULT_PROMPT = "Please transcribe this audio file."
DEFAULT_MAX_SECONDS = 600
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "sttui" / "config.toml"
DEFAULT_RECORDINGS_DIR = Path.home() / ".local" / "share" / "sttui" / "recordings"


@dataclass(frozen=True)
class RuntimeSettings:
    api_key: str
    model: str = DEFAULT_MODEL
    prompt: str = DEFAULT_PROMPT
    max_seconds: int = DEFAULT_MAX_SECONDS
    recordings_dir: Path = DEFAULT_RECORDINGS_DIR
    stdout_mode: bool = False
    debug: bool = False


def _config_hint(path: Path) -> str:
    return (
        "config missing or invalid. expected keys: "
        "openrouter.api_key, transcription.model, transcription.prompt, transcription.max_seconds "
        f"in {path}"
    )


def load_config_file(path: Path = DEFAULT_CONFIG_PATH) -> dict:
    if not path.exists():
        raise ConfigError(_config_hint(path))
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise ConfigError(_config_hint(path)) from exc
    if not isinstance(data, dict):
        raise ConfigError(_config_hint(path))
    return data


def _int_or_default(value: object, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return default


def load_runtime_settings(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    model_override: str | None = None,
    max_seconds_override: int | None = None,
    stdout_mode: bool = False,
    debug: bool = False,
) -> RuntimeSettings:
    cfg = load_config_file(config_path)
    openrouter = (
        cfg.get("openrouter") if isinstance(cfg.get("openrouter"), dict) else {}
    )
    transcription = (
        cfg.get("transcription") if isinstance(cfg.get("transcription"), dict) else {}
    )

    api_key = str(openrouter.get("api_key", "")).strip()
    if not api_key:
        raise ConfigError(_config_hint(config_path))

    model = str(transcription.get("model") or DEFAULT_MODEL)
    prompt = str(transcription.get("prompt") or DEFAULT_PROMPT)
    max_seconds = _int_or_default(transcription.get("max_seconds"), DEFAULT_MAX_SECONDS)

    if model_override:
        model = model_override
    if max_seconds_override is not None:
        max_seconds = max_seconds_override

    if max_seconds <= 0:
        raise ConfigError("max seconds must be a positive integer")

    recordings_dir = Path(
        os.environ.get("STTUI_RECORDINGS_DIR", str(DEFAULT_RECORDINGS_DIR))
    ).expanduser()

    return RuntimeSettings(
        api_key=api_key,
        model=model,
        prompt=prompt,
        max_seconds=max_seconds,
        recordings_dir=recordings_dir,
        stdout_mode=stdout_mode,
        debug=debug,
    )
