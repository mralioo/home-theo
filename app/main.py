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

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from app.agents.coordinator import handle_request
from app.core.repository import events_for, init_db
from app.core.schemas import InboundRequest, OrchestratorResponse

app = FastAPI(title="Autonomous Ops Orchestrator", version="0.1.0")

_DASHBOARD = Path(__file__).parent / "static" / "dashboard.html"


@app.on_event("startup")
def _startup() -> None:
    init_db()


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
