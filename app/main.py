"""
HTTP surface of the orchestration layer. This is what the voice/channel layer
(colleague) calls. Kept deliberately thin — all logic lives in the agents.

Endpoints:
  POST /api/requests             -> run the orchestration, return OrchestratorResponse
  GET  /api/requests/{id}/status -> status events (for the BPMN dashboard)
  GET  /health                   -> liveness for Cloud Run
  GET  /dashboard                -> pipeline visualizer UI
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from app.agents.coordinator import handle_request
from app.core import event_bus
from app.core.repository import events_for, init_db
from app.core.schemas import InboundRequest, OrchestratorResponse
from app.core.settings import settings
from app.routes import actions as actions_route
from app.routes import elevenlabs as elevenlabs_route
from app.routes import events as events_route
from app.routes import queries as queries_route
from app.routes import transcribe as transcribe_route

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

_DASHBOARD = Path(__file__).parent / "static" / "dashboard.html"
_APP_HTML = Path(__file__).parent / "static" / "app.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    event_bus.attach_loop(asyncio.get_running_loop())
    yield


app = FastAPI(
    title="Autonomous Ops Orchestrator",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(queries_route.router)
app.include_router(events_route.router)
app.include_router(elevenlabs_route.router)
app.include_router(actions_route.router)
app.include_router(transcribe_route.router)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(content=_DASHBOARD.read_text())


@app.get("/app", response_class=HTMLResponse)
def spa() -> HTMLResponse:
    return HTMLResponse(content=_APP_HTML.read_text())


@app.post("/api/tts")
async def text_to_speech(payload: dict) -> Response:
    """Call ElevenLabs TTS and stream back MP3 bytes to the dashboard player."""
    text = payload.get("text", "").strip()
    voice_id = payload.get("voice_id") or settings.elevenlabs_tts_voice_id
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    if not settings.elevenlabs_api_key:
        raise HTTPException(status_code=503, detail="ELEVENLABS_API_KEY not configured")
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": settings.elevenlabs_api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text[:5000],
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.45,
                    "similarity_boost": 0.80,
                    "style": 0.15,
                    "use_speaker_boost": True,
                },
            },
            timeout=30.0,
        )
    if not r.is_success:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return Response(
        content=r.content,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/requests", response_model=OrchestratorResponse)
def create_request(req: InboundRequest) -> OrchestratorResponse:
    try:
        return handle_request(req)
    except Exception as exc:  # surface a clean error to the caller
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/requests/{request_id}/status")
def get_status(request_id: str) -> dict:
    events = events_for(request_id)
    if not events:
        raise HTTPException(status_code=404, detail="unknown request_id")
    return {"request_id": request_id, "events": events}
