"""OpenRouter transcription client."""

from __future__ import annotations

import base64
from pathlib import Path

import requests

from sttui.errors import TranscriptionError

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
INVALID_API_KEY_MSG = "invalid api key. Run `sttui auth` to update it"


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
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "input_audio",
                        "input_audio": {"data": audio_b64, "format": "wav"},
                    },
                ],
            }
        ],
    }


def parse_transcript(data: dict) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise TranscriptionError("malformed API response")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise TranscriptionError("malformed API response")

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content

    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        joined = "".join(chunks)
        if joined.strip():
            return joined

    raise TranscriptionError("malformed API response")


def _extract_api_error_detail(resp: object) -> str:
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


def _raise_api_error(resp: object) -> None:
    status_code = int(getattr(resp, "status_code", 0))
    detail = _extract_api_error_detail(resp)
    detail_lc = detail.lower()

    if status_code in {401, 403}:
        raise TranscriptionError(INVALID_API_KEY_MSG)
    if "invalid api key" in detail_lc or "unauthorized" in detail_lc:
        raise TranscriptionError(INVALID_API_KEY_MSG)
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
        raise TranscriptionError("network error") from exc

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
) -> str:
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
        raise TranscriptionError("network error") from exc

    if resp.status_code < 200 or resp.status_code >= 300:
        _raise_api_error(resp)

    try:
        data = resp.json()
    except ValueError as exc:
        raise TranscriptionError("malformed API response") from exc
    if not isinstance(data, dict):
        raise TranscriptionError("malformed API response")
    return parse_transcript(data)
