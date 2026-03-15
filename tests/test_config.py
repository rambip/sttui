import json
from pathlib import Path

import pytest

from sttui.config import (
    DEFAULT_AUTH_PATH,
    DEFAULT_MAX_SECONDS,
    DEFAULT_MODEL,
    DEFAULT_PROMPT,
    load_api_key,
    load_runtime_settings,
)
from sttui.errors import ConfigError


def write_config(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(text, encoding="utf-8")
    return p


def write_auth(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "auth.json"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_api_key_from_auth_json(tmp_path: Path) -> None:
    auth = write_auth(
        tmp_path,
        json.dumps({"openrouter": {"api_key": "or-test"}}),
    )
    key = load_api_key(auth_path=auth)
    assert key == "or-test"


def test_missing_auth_file_errors(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    with pytest.raises(ConfigError, match="no api key registered"):
        load_api_key(auth_path=auth)


def test_missing_openrouter_key_errors(tmp_path: Path) -> None:
    auth = write_auth(tmp_path, json.dumps({}))
    with pytest.raises(ConfigError, match="no api key registered"):
        load_api_key(auth_path=auth)


def test_empty_api_key_errors(tmp_path: Path) -> None:
    auth = write_auth(tmp_path, json.dumps({"openrouter": {"api_key": ""}}))
    with pytest.raises(ConfigError, match="no api key registered"):
        load_api_key(auth_path=auth)


def test_load_runtime_settings_defaults(tmp_path: Path) -> None:
    cfg = write_config(tmp_path, "")
    auth = write_auth(
        tmp_path,
        json.dumps({"openrouter": {"api_key": "or-test"}}),
    )
    settings = load_runtime_settings(config_path=cfg, auth_path=auth)
    assert settings.api_key == "or-test"
    assert settings.model == DEFAULT_MODEL
    assert settings.prompt == DEFAULT_PROMPT
    assert settings.max_seconds == DEFAULT_MAX_SECONDS


def test_cli_overrides_take_precedence(tmp_path: Path) -> None:
    cfg = write_config(
        tmp_path,
        """
[transcription]
model = "a"
max_seconds = 10
""",
    )
    auth = write_auth(
        tmp_path,
        json.dumps({"openrouter": {"api_key": "or-test"}}),
    )
    settings = load_runtime_settings(
        config_path=cfg,
        auth_path=auth,
        model_override="b",
        max_seconds_override=45,
    )
    assert settings.model == "b"
    assert settings.max_seconds == 45


def test_non_positive_max_seconds_errors(tmp_path: Path) -> None:
    cfg = write_config(
        tmp_path,
        """
[transcription]
max_seconds = 0
""",
    )
    auth = write_auth(
        tmp_path,
        json.dumps({"openrouter": {"api_key": "or-test"}}),
    )
    with pytest.raises(ConfigError):
        load_runtime_settings(config_path=cfg, auth_path=auth)
