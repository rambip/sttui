"""OpenRouter transcription client."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Protocol

import requests

from sttui.errors import RetryableTranscriptionError, TranscriptionError

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
INVALID_API_KEY_MSG = "invalid api key. Run `sttui auth` to update it"


class _ResponseLike(Protocol):
    status_code: int

    def json(self) -> Any: ...


def encode_audio_base64(audio_path: Path) -> str:
    try:
        raw = audio_path.read_bytes()
    except OSError as exc:
        raise TranscriptionError(f"failed to read audio file: {audio_path}") from exc
    return base64.b64encode(raw).decode("ascii")


def build_payload(*, model: str, prompt: str, audio_b64: str) -> dict:
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": prompt,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": audio_b64, "format": "wav"},
                    },
                ],
            },
        ],
    }


def _parse_transcript_with_meta(data: dict) -> tuple[str, bool, str]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise TranscriptionError("malformed API response")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise TranscriptionError("malformed API response")

    content = message.get("content")
    raw_text = ""

    if isinstance(content, str):
        raw_text = content
    elif isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        raw_text = "".join(chunks)
    else:
        raise TranscriptionError("malformed API response")

    json_text = _extract_json_text(raw_text)
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError:
        return "", True, raw_text
    if not isinstance(parsed, dict):
        return "", False, raw_text
    transcription = parsed.get("transcription")
    if transcription is None:
        return "", False, raw_text
    if not isinstance(transcription, str):
        return "", False, raw_text
    return transcription, False, raw_text


def _extract_json_text(raw_text: str) -> str:
    stripped = raw_text.strip()
    if not (stripped.startswith("```") and stripped.endswith("```")):
        return raw_text

    lines = stripped.splitlines()
    if len(lines) < 2:
        return raw_text

    first = lines[0].strip()
    last = lines[-1].strip()
    if last != "```":
        return raw_text

    if first == "```" or first.startswith("```"):
        return "\n".join(lines[1:-1])
    return raw_text


def parse_transcript(data: dict) -> str:
    transcript, _, _ = _parse_transcript_with_meta(data)
    return transcript


def _extract_api_error_detail(resp: _ResponseLike) -> str:
    try:
        body = resp.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    err = body.get("error")
    if not isinstance(err, dict):
        return ""
    msg = err.get("message")
    if not isinstance(msg, str):
        return ""
    return msg


def _raise_api_error(resp: _ResponseLike) -> None:
    status_code = int(getattr(resp, "status_code", 0))
    detail = _extract_api_error_detail(resp)
    detail_lc = detail.lower()

    # Non-retryable: invalid API key
    if status_code in {401, 403}:
        raise TranscriptionError(INVALID_API_KEY_MSG)
    if "invalid api key" in detail_lc or "unauthorized" in detail_lc:
        raise TranscriptionError(INVALID_API_KEY_MSG)

    # Retryable: balance issues, rate limits, server errors
    if "balance" in detail_lc or status_code in {429} or status_code >= 500:
        if detail:
            raise RetryableTranscriptionError(f"api error: {detail}")
        raise RetryableTranscriptionError(f"api error: HTTP {status_code}")

    # Other API errors - non-retryable
    if detail:
        raise TranscriptionError(f"api error: {detail}")
    raise TranscriptionError(f"api error: HTTP {status_code}")


def list_audio_models(api_key: str, timeout_seconds: int = 20) -> list[str]:
    """Return OpenRouter model ids that accept audio input."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.get(
            OPENROUTER_MODELS_URL, headers=headers, timeout=timeout_seconds
        )
    except requests.RequestException as exc:
        raise RetryableTranscriptionError("network error") from exc

    if resp.status_code < 200 or resp.status_code >= 300:
        _raise_api_error(resp)

    try:
        payload = resp.json()
    except ValueError as exc:
        raise TranscriptionError("malformed API response") from exc
    if not isinstance(payload, dict):
        raise TranscriptionError("malformed API response")

    data = payload.get("data")
    if not isinstance(data, list):
        raise TranscriptionError("malformed API response")

    model_ids: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if not isinstance(model_id, str) or not model_id.strip():
            continue

        architecture = item.get("architecture")
        if not isinstance(architecture, dict):
            continue
        input_modalities = architecture.get("input_modalities")
        if not isinstance(input_modalities, list):
            continue
        if "audio" not in [str(modality).lower() for modality in input_modalities]:
            continue
        model_ids.append(model_id.strip())

    return sorted(set(model_ids))


def transcribe_audio(
    *,
    api_key: str,
    model: str,
    prompt: str,
    audio_path: Path,
    timeout_seconds: int = 120,
) -> tuple[str, bool, str]:
    payload = build_payload(
        model=model,
        prompt=prompt,
        audio_b64=encode_audio_base64(audio_path),
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            OPENROUTER_URL,
            json=payload,
            headers=headers,
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        raise RetryableTranscriptionError("network error") from exc

    if resp.status_code < 200 or resp.status_code >= 300:
        _raise_api_error(resp)

    try:
        data = resp.json()
    except ValueError as exc:
        raise RetryableTranscriptionError("malformed API response") from exc
    if not isinstance(data, dict):
        raise RetryableTranscriptionError("malformed API response")
    return _parse_transcript_with_meta(data)
