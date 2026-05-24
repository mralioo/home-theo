"""Transcription endpoints: submit audio → ElevenLabs STT → orchestration pipeline.

Three modes:
  POST /api/transcribe/file          — multipart audio/video file upload
  POST /api/transcribe/url           — public HTTPS URL to audio/video
  POST /api/transcribe/conversation  — pull transcript from ElevenLabs ConvAI

All three run the full orchestration pipeline on the resulting transcript and
return an OrchestratorResponse (identical to POST /api/requests).

Additional:
  GET  /api/transcribe/conversation/{id}/preview  — inspect raw transcript
                                                    without running the pipeline
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.agents.coordinator import handle_request
from app.core.schemas import Channel, InboundRequest, OrchestratorResponse
from app.services import stt as stt_svc

router = APIRouter(prefix="/api/transcribe", tags=["transcribe"])


# ── shared helper ──────────────────────────────────────────────────────────────


def _orchestrate(
    transcript: str,
    channel: str,
    property_hint: str | None,
    request_id: str | None,
) -> OrchestratorResponse:
    req = InboundRequest(
        request_id=request_id or f"stt-{uuid.uuid4().hex[:8]}",
        channel=Channel(channel),
        raw_text=transcript,
        property_hint=property_hint,
    )
    try:
        return handle_request(req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _stt_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, httpx_error := type(exc)) and "httpx" in httpx_error.__module__:
        return HTTPException(status_code=502, detail=f"ElevenLabs API error: {exc}")
    return HTTPException(status_code=502, detail=f"STT failed: {exc}")


# ── POST /api/transcribe/file ──────────────────────────────────────────────────


@router.post("/file", response_model=OrchestratorResponse, summary="Upload audio → pipeline")
async def transcribe_file(
    file: UploadFile = File(
        ..., description="Audio/video file (mp3, wav, m4a, ogg, webm, mp4, flac)"
    ),
    channel: str = Form("phone", description="Inbound channel: phone|chat|sms|email|walk_in"),
    property_hint: str | None = Form(None, description="Property name or address hint"),
    language_code: str = Form("de", description="ISO-639-1 language code; empty = auto-detect"),
    diarize: bool = Form(False, description="Separate speaker turns in transcript"),
    request_id: str | None = Form(
        None, description="Custom idempotency key; auto-generated if omitted"
    ),
) -> OrchestratorResponse:
    """Upload an audio/video file, transcribe with ElevenLabs Scribe, then run the pipeline."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Empty file")
    try:
        transcript = stt_svc.transcribe_file(
            data,
            file.filename or "audio.mp3",
            language_code=language_code,
            diarize=diarize,
        )
    except Exception as exc:
        raise _stt_error(exc) from exc

    return _orchestrate(transcript, channel, property_hint, request_id)


# ── POST /api/transcribe/url ───────────────────────────────────────────────────


class TranscribeUrlBody(BaseModel):
    url: str
    channel: str = "phone"
    property_hint: str | None = None
    language_code: str = "de"
    request_id: str | None = None


@router.post("/url", response_model=OrchestratorResponse, summary="Audio URL → pipeline")
def transcribe_url(body: TranscribeUrlBody) -> OrchestratorResponse:
    """Pass a public HTTPS audio/video URL, transcribe with ElevenLabs, then run the pipeline."""
    try:
        transcript = stt_svc.transcribe_url(body.url, language_code=body.language_code)
    except Exception as exc:
        raise _stt_error(exc) from exc

    return _orchestrate(transcript, body.channel, body.property_hint, body.request_id)


# ── POST /api/transcribe/conversation ─────────────────────────────────────────


class TranscribeConvBody(BaseModel):
    conversation_id: str
    channel: str = "phone"
    property_hint: str | None = None
    request_id: str | None = None


@router.post(
    "/conversation", response_model=OrchestratorResponse, summary="ConvAI transcript → pipeline"
)
def transcribe_conversation(body: TranscribeConvBody) -> OrchestratorResponse:
    """Pull the tenant's turns from an ElevenLabs ConvAI conversation and run the pipeline."""
    try:
        transcript = stt_svc.fetch_conversation_transcript(body.conversation_id)
    except Exception as exc:
        raise _stt_error(exc) from exc

    if not transcript.strip():
        raise HTTPException(status_code=422, detail="No user turns found in conversation")

    return _orchestrate(
        transcript,
        body.channel,
        body.property_hint,
        body.request_id or body.conversation_id,
    )


# ── GET /api/transcribe/conversation/{id}/preview ─────────────────────────────


@router.get(
    "/conversation/{conversation_id}/preview",
    summary="Preview ConvAI transcript (no pipeline)",
)
def preview_conversation(conversation_id: str) -> dict:
    """Fetch raw ElevenLabs conversation metadata and extract transcript — does NOT run the pipeline."""
    try:
        meta = stt_svc.fetch_conversation_metadata(conversation_id)
    except Exception as exc:
        raise _stt_error(exc) from exc

    turns = meta.get("transcript") or []
    user_text = " ".join(t["message"] for t in turns if t.get("role") == "user")
    return {
        "conversation_id": conversation_id,
        "duration_seconds": meta.get("metadata", {}).get("duration", None),
        "user_transcript": user_text,
        "turn_count": len(turns),
        "turns": [{"role": t.get("role"), "message": t.get("message", "")} for t in turns],
    }
