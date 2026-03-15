import base64

import pytest
import requests

from sttui.errors import TranscriptionError
from sttui.transcribe import (
    INVALID_API_KEY_MSG,
    build_payload,
    list_audio_models,
    parse_transcript,
)


def test_build_payload_structure() -> None:
    audio_b64 = base64.b64encode(b"wav").decode("ascii")
    payload = build_payload(model="m", prompt="p", audio_b64=audio_b64)
    assert payload["model"] == "m"
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][0]["content"] == "p"
    msg = payload["messages"][1]
    assert msg["role"] == "user"
    content = msg["content"]
    assert content[0]["type"] == "input_audio"
    assert content[0]["input_audio"]["format"] == "wav"
    assert content[0]["input_audio"]["data"] == audio_b64


def test_parse_transcript_string_content() -> None:
    data = {"choices": [{"message": {"content": '{"transcription":"hello"}'}}]}
    assert parse_transcript(data) == "hello"


def test_parse_transcript_chunk_content() -> None:
    data = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "output_text", "text": '{"transcription":"hello'},
                        {"type": "output_text", "text": ' world"}'},
                    ]
                }
            }
        ]
    }
    assert parse_transcript(data) == "hello world"


def test_parse_transcript_invalid_json_returns_empty() -> None:
    data = {"choices": [{"message": {"content": "not json"}}]}
    assert parse_transcript(data) == ""


def test_parse_transcript_json_without_transcription_returns_empty() -> None:
    data = {"choices": [{"message": {"content": '{"foo":"bar"}'}}]}
    assert parse_transcript(data) == ""


def test_parse_transcript_json_non_string_transcription_returns_empty() -> None:
    data = {"choices": [{"message": {"content": '{"transcription":123}'}}]}
    assert parse_transcript(data) == ""


def test_parse_transcript_json_null_transcription_returns_empty() -> None:
    data = {"choices": [{"message": {"content": '{"transcription":null}'}}]}
    assert parse_transcript(data) == ""


def test_parse_transcript_invalid_shape() -> None:
    with pytest.raises(TranscriptionError):
        parse_transcript({"choices": []})


def test_list_audio_models_filters_and_sorts(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {
                "data": [
                    {
                        "id": "b/model",
                        "architecture": {"input_modalities": ["text", "audio"]},
                    },
                    {
                        "id": "a/model",
                        "architecture": {"input_modalities": ["Audio"]},
                    },
                    {
                        "id": "c/model",
                        "architecture": {"input_modalities": ["text"]},
                    },
                    {
                        "id": "a/model",
                        "architecture": {"input_modalities": ["audio"]},
                    },
                ]
            }

    def fake_get(*args: object, **kwargs: object) -> Response:
        return Response()

    monkeypatch.setattr(requests, "get", fake_get)

    assert list_audio_models("or-test") == ["a/model", "b/model"]


def test_list_audio_models_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 503

        @staticmethod
        def json() -> dict:
            return {}

    def fake_get(*args: object, **kwargs: object) -> Response:
        return Response()

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(TranscriptionError, match="api error: HTTP 503"):
        list_audio_models("or-test")


def test_list_audio_models_invalid_api_key_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status_code = 401

        @staticmethod
        def json() -> dict:
            return {"error": {"message": "Unauthorized"}}

    def fake_get(*args: object, **kwargs: object) -> Response:
        return Response()

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(TranscriptionError, match="invalid api key"):
        list_audio_models("or-test")


def test_list_audio_models_invalid_api_key_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status_code = 400

        @staticmethod
        def json() -> dict:
            return {"error": {"message": "Invalid API key"}}

    def fake_get(*args: object, **kwargs: object) -> Response:
        return Response()

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(TranscriptionError, match=INVALID_API_KEY_MSG):
        list_audio_models("or-test")


def test_list_audio_models_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(*args: object, **kwargs: object) -> object:
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(TranscriptionError, match="network error"):
        list_audio_models("or-test")
