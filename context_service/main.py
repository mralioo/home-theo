"""
Hausmind Context Service
Provides semantic search over buildings, vendors and incidents.

Endpoints:
  GET /health
  GET /buildings/search?q=<text>
  GET /vendors/search?category=<cat>[&building_id=<id>]
  GET /incidents/search?building_id=<id>[&category=<cat>]
  GET /incidents/semantic?q=<text>&building_id=<id>
  POST /admin/reindex   — re-seeds all indices from the data file
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

import embedder
import indexer
import searcher

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    embedder.load_model()
    indexer.seed_all()
    yield


app = FastAPI(title="Hausmind Context Service", version="0.1.0", lifespan=lifespan)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ── Buildings ─────────────────────────────────────────────────────────────────

@app.get("/buildings/search")
def buildings_search(
    q: str = Query(..., description="Free-text property hint (address, name, city…)"),
    top_k: int = Query(3, ge=1, le=10),
) -> dict:
    try:
        results = searcher.search_buildings(q, top_k=top_k)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"query": q, "results": results}


# ── Vendors ───────────────────────────────────────────────────────────────────

@app.get("/vendors/search")
def vendors_search(
    category: str = Query(..., description="Issue category: heating, plumbing, electrical…"),
    building_id: str | None = Query(None, description="Prefer vendors used by this building"),
    top_k: int = Query(5, ge=1, le=20),
) -> dict:
    try:
        results = searcher.search_vendors(category, building_id=building_id, top_k=top_k)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"category": category, "results": results}


# ── Incidents ─────────────────────────────────────────────────────────────────

@app.get("/incidents/search")
def incidents_search(
    building_id: str = Query(...),
    category: str | None = Query(None),
    top_k: int = Query(10, ge=1, le=50),
) -> dict:
    try:
        results = searcher.search_incidents(building_id, category=category, top_k=top_k)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"building_id": building_id, "results": results}


@app.get("/incidents/semantic")
def incidents_semantic(
    q: str = Query(..., description="Natural language description of the issue"),
    building_id: str = Query(...),
    top_k: int = Query(5, ge=1, le=20),
) -> dict:
    try:
        results = searcher.search_incidents_semantic(q, building_id, top_k=top_k)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"query": q, "building_id": building_id, "results": results}


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.post("/admin/reindex")
def reindex() -> dict:
    try:
        indexer.seed_all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "reindexed"}
