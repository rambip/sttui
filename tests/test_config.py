from pathlib import Path

import pytest

from sttui.config import (
    DEFAULT_MAX_SECONDS,
    DEFAULT_MODEL,
    DEFAULT_PROMPT,
    load_runtime_settings,
)
from sttui.errors import ConfigError


def write_config(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_runtime_settings_defaults(tmp_path: Path) -> None:
    cfg = write_config(
        tmp_path,
        """
[openrouter]
api_key = "or-test"
""",
    )
    settings = load_runtime_settings(config_path=cfg)
    assert settings.api_key == "or-test"
    assert settings.model == DEFAULT_MODEL
    assert settings.prompt == DEFAULT_PROMPT
    assert settings.max_seconds == DEFAULT_MAX_SECONDS


def test_cli_overrides_take_precedence(tmp_path: Path) -> None:
    cfg = write_config(
        tmp_path,
        """
[openrouter]
api_key = "or-test"

[transcription]
model = "a"
max_seconds = 10
""",
    )
    settings = load_runtime_settings(
        config_path=cfg,
        model_override="b",
        max_seconds_override=45,
    )
    assert settings.model == "b"
    assert settings.max_seconds == 45


def test_missing_api_key_errors(tmp_path: Path) -> None:
    cfg = write_config(
        tmp_path,
        """
[openrouter]
api_key = ""
""",
    )
    with pytest.raises(ConfigError):
        load_runtime_settings(config_path=cfg)


def test_non_positive_max_seconds_errors(tmp_path: Path) -> None:
    cfg = write_config(
        tmp_path,
        """
[openrouter]
api_key = "or-test"

[transcription]
max_seconds = 0
""",
    )
    with pytest.raises(ConfigError):
        load_runtime_settings(config_path=cfg)
