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

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.agents.coordinator import handle_request
from app.core import event_bus
from app.core.repository import events_for, init_db
from app.core.schemas import InboundRequest, OrchestratorResponse
from app.routes import actions as actions_route
from app.routes import elevenlabs as elevenlabs_route
from app.routes import events as events_route

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

_DASHBOARD = Path(__file__).parent / "static" / "dashboard.html"


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

app.include_router(events_route.router)
app.include_router(elevenlabs_route.router)
app.include_router(actions_route.router)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(content=_DASHBOARD.read_text())


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
