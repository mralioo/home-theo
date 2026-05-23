"""Tests for the SSE endpoint.

Two layers:
  1. `test_sse_route_registered` — route is mounted at the expected path with
     the right method. Cheap and avoids the long-lived stream that hangs
     TestClient.
  2. `test_sse_generator_streams_events` — exercises the generator wired into
     the endpoint by subscribing through `event_bus` and publishing live.
     This is what the browser EventSource sees, minus the HTTP transport.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.core import event_bus
from app.core.repository import record_event
from app.core.schemas import StatusEvent
from app.main import app


def test_sse_route_registered():
    """Smoke check: GET /events/stream/{request_id} is wired up."""
    routes = {(r.path, tuple(sorted(r.methods))) for r in app.routes if hasattr(r, "methods")}
    assert ("/events/stream/{request_id}", ("GET",)) in routes


@pytest.mark.asyncio
async def test_sse_generator_streams_events():
    """Drive record_event → event_bus → subscribe pipeline like the route does."""
    rid = "sse-gen-1"

    async def consume(n: int) -> list[dict]:
        out: list[dict] = []
        async for ev in event_bus.subscribe(rid):
            out.append(json.loads(ev.model_dump_json()))
            if len(out) >= n:
                return out
        return out

    task = asyncio.create_task(consume(3))
    await asyncio.sleep(0.05)

    for node in ("intake", "triage", "context"):
        record_event(StatusEvent(request_id=rid, node=node, status="done"))

    received = await asyncio.wait_for(task, timeout=1.0)
    assert [e["node"] for e in received] == ["intake", "triage", "context"]
