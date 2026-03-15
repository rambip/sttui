"""Config loading and runtime settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import tomllib

from sttui.errors import ConfigError

DEFAULT_MODEL = "google/gemini-2.5-flash"
DEFAULT_PROMPT = "Please transcribe this audio file."
DEFAULT_MAX_SECONDS = 600
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "sttui" / "config.toml"
DEFAULT_AUTH_PATH = Path.home() / ".config" / "sttui" / "auth.json"
DEFAULT_RECORDINGS_DIR = Path.home() / ".local" / "share" / "sttui" / "recordings"


@dataclass(frozen=True)
class RuntimeSettings:
    api_key: str
    model: str = DEFAULT_MODEL
    prompt: str = DEFAULT_PROMPT
    max_seconds: int = DEFAULT_MAX_SECONDS
    input_device: int | None = None
    recordings_dir: Path = DEFAULT_RECORDINGS_DIR
    stdout_mode: bool = False
    debug: bool = False


def _config_hint(path: Path) -> str:
    return (
        "config missing or invalid. expected keys: "
        "transcription.model, transcription.prompt, transcription.max_seconds "
        f"in {path}"
    )


def _get_default_config() -> str:
    import sttui

    pkg_dir = Path(sttui.__file__).parent
    default_path = pkg_dir / "default_config.toml"
    return default_path.read_text(encoding="utf-8")


def load_config_file(path: Path = DEFAULT_CONFIG_PATH) -> dict:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        default_content = _get_default_config()
        path.write_text(default_content, encoding="utf-8")
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise ConfigError(_config_hint(path)) from exc
    if not isinstance(data, dict):
        raise ConfigError(_config_hint(path))
    return data


def load_auth_file(path: Path = DEFAULT_AUTH_PATH) -> dict:
    if not path.exists():
        raise ConfigError("no api key registered. Run `sttui auth` to setup")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise ConfigError("no api key registered. Run `sttui auth` to setup") from exc
    if not isinstance(data, dict):
        raise ConfigError("no api key registered. Run `sttui auth` to setup")
    return data


def load_api_key(*, auth_path: Path = DEFAULT_AUTH_PATH) -> str:
    auth = load_auth_file(auth_path)
    openrouter = _as_section(auth.get("openrouter"))
    api_key = str(openrouter.get("api_key", "")).strip()
    if not api_key:
        raise ConfigError("no api key registered. Run `sttui auth` to setup")
    return api_key


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


def _optional_non_negative_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _as_section(value: object) -> dict:
    if isinstance(value, dict):
        return value
    return {}


def load_runtime_settings(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    auth_path: Path = DEFAULT_AUTH_PATH,
    model_override: str | None = None,
    max_seconds_override: int | None = None,
    stdout_mode: bool = False,
    debug: bool = False,
) -> RuntimeSettings:
    cfg = load_config_file(config_path)
    transcription = _as_section(cfg.get("transcription"))
    audio = _as_section(cfg.get("audio"))

    api_key = load_api_key(auth_path=auth_path)

    model = str(transcription.get("model") or DEFAULT_MODEL)
    prompt = str(transcription.get("prompt") or DEFAULT_PROMPT)
    max_seconds = _int_or_default(transcription.get("max_seconds"), DEFAULT_MAX_SECONDS)
    input_device = _optional_non_negative_int(audio.get("input_device"))

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
        input_device=input_device,
        recordings_dir=recordings_dir,
        stdout_mode=stdout_mode,
        debug=debug,
    )
