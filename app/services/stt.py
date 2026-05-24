"""ElevenLabs Speech-to-Text service.

Three entry points:
  transcribe_file(data, filename, *, language_code)  — binary upload
  transcribe_url(url, *, language_code)              — cloud / direct URL
  fetch_conversation_transcript(conversation_id)     — pull from ConvAI history

Uses httpx (already in requirements) — no extra SDK needed.
"""

from __future__ import annotations

import httpx

from app.core.settings import settings

_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
_CONVAI_URL = "https://api.elevenlabs.io/v1/convai/conversations/{}"

_MIME: dict[str, str] = {
    "mp3": "audio/mpeg",
    "mp4": "video/mp4",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "ogg": "audio/ogg",
    "webm": "audio/webm",
    "flac": "audio/flac",
    "aac": "audio/aac",
}


def _auth() -> dict[str, str]:
    return {"xi-api-key": settings.elevenlabs_api_key}


def _require_key() -> None:
    if not settings.elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set. Add it to .env to enable STT.")


def _mime(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _MIME.get(ext, "audio/mpeg")


def transcribe_file(
    data: bytes,
    filename: str,
    *,
    language_code: str = "de",
    model_id: str = "scribe_v2",
    diarize: bool = False,
) -> str:
    """POST audio bytes to ElevenLabs STT. Returns full transcript text.

    Args:
        data: Raw audio/video bytes.
        filename: Used to infer MIME type (e.g. "call.mp3").
        language_code: ISO-639-1 code; defaults to German ("de"). Pass empty
            string to let ElevenLabs auto-detect the language.
        model_id: "scribe_v2" (recommended) or "scribe_v1".
        diarize: If True, separate speaker turns in the transcript.
    """
    _require_key()
    payload: dict[str, str] = {"model_id": model_id}
    if language_code:
        payload["language_code"] = language_code
    if diarize:
        payload["diarize"] = "true"

    with httpx.Client(timeout=180) as client:
        resp = client.post(
            _STT_URL,
            headers=_auth(),
            data=payload,
            files={"file": (filename, data, _mime(filename))},
        )
    resp.raise_for_status()
    return resp.json()["text"]


def transcribe_url(
    url: str,
    *,
    language_code: str = "de",
    model_id: str = "scribe_v2",
) -> str:
    """POST a cloud_storage_url to ElevenLabs STT. Returns full transcript text.

    Accepts HTTPS URLs pointing to audio/video files (max 2 GB).
    """
    _require_key()
    payload: dict[str, str] = {"model_id": model_id, "cloud_storage_url": url}
    if language_code:
        payload["language_code"] = language_code

    with httpx.Client(timeout=180) as client:
        resp = client.post(_STT_URL, headers=_auth(), data=payload)
    resp.raise_for_status()
    return resp.json()["text"]


def fetch_conversation_transcript(conversation_id: str) -> str:
    """Pull transcript from the ElevenLabs ConvAI conversation history API.

    Joins all user-role turns into a single string suitable for triage.
    Falls back to including agent turns (labeled) when no user turns exist.
    """
    _require_key()
    with httpx.Client(timeout=30) as client:
        resp = client.get(_CONVAI_URL.format(conversation_id), headers=_auth())
    resp.raise_for_status()
    data = resp.json()

    # Conversation API returns transcript as a list of {role, message} dicts
    turns: list[dict] = data.get("transcript") or []

    user_turns = [t["message"] for t in turns if t.get("role") == "user"]
    if user_turns:
        return " ".join(user_turns)

    # Fallback: no user turns — include all turns with role labels
    labeled = [f"{t.get('role', '?')}: {t.get('message', '')}" for t in turns]
    return "\n".join(labeled)


def fetch_conversation_metadata(conversation_id: str) -> dict:
    """Return the raw conversation object from ElevenLabs ConvAI."""
    _require_key()
    with httpx.Client(timeout=30) as client:
        resp = client.get(_CONVAI_URL.format(conversation_id), headers=_auth())
    resp.raise_for_status()
    return resp.json()
