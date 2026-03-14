import base64

import pytest

from sttui.errors import TranscriptionError
from sttui.transcribe import build_payload, list_audio_models, parse_transcript


def test_build_payload_structure() -> None:
    audio_b64 = base64.b64encode(b"wav").decode("ascii")
    payload = build_payload(model="m", prompt="p", audio_b64=audio_b64)
    assert payload["model"] == "m"
    msg = payload["messages"][0]
    assert msg["role"] == "user"
    content = msg["content"]
    assert content[0]["type"] == "text"
    assert content[0]["text"] == "p"
    assert content[1]["type"] == "input_audio"
    assert content[1]["input_audio"]["format"] == "wav"
    assert content[1]["input_audio"]["data"] == audio_b64


def test_parse_transcript_string_content() -> None:
    data = {"choices": [{"message": {"content": "hello"}}]}
    assert parse_transcript(data) == "hello"


def test_parse_transcript_chunk_content() -> None:
    data = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "output_text", "text": "hello"},
                        {"type": "output_text", "text": " world"},
                    ]
                }
            }
        ]
    }
    assert parse_transcript(data) == "hello world"


def test_parse_transcript_invalid_shape() -> None:
    with pytest.raises(TranscriptionError):
        parse_transcript({"choices": []})


def test_list_audio_models_filters_input_modality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status_code = 200

        def json(self) -> dict:
            return {
                "data": [
                    {
                        "id": "openai/gpt-4",
                        "architecture": {"input_modalities": ["text"]},
                    },
                    {
                        "id": "openai/gpt-4o-mini-transcribe",
                        "architecture": {"input_modalities": ["text", "audio"]},
                    },
                    {
                        "id": "openai/gpt-4o-transcribe",
                        "architecture": {"input_modalities": ["audio"]},
                    },
                ]
            }

    def fake_get(*args, **kwargs) -> FakeResponse:  # noqa: ANN002, ANN003
        return FakeResponse()

    monkeypatch.setattr("sttui.transcribe.requests.get", fake_get)

    models = list_audio_models("or-test")
    assert models == ["openai/gpt-4o-mini-transcribe", "openai/gpt-4o-transcribe"]
