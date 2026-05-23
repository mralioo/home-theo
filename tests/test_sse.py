"""Integration test for the SSE endpoint.

Drives a fake trace through record_event (which fans to event_bus subscribers)
and asserts the SSE stream yields the expected JSON-encoded StatusEvents.
"""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.core import event_bus
from app.core.repository import record_event
from app.core.schemas import StatusEvent
from app.main import app


@pytest.mark.asyncio
async def test_sse_streams_status_events():
    rid = "sse-1"
    event_bus.attach_loop(asyncio.get_running_loop())

    transport = httpx.ASGITransport(app=app)
    received: list[dict] = []

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:

        async def consume():
            async with client.stream("GET", f"/events/stream/{rid}") as resp:
                assert resp.status_code == 200
                async for line in resp.aiter_lines():
                    if line.startswith("data:"):
                        received.append(json.loads(line.removeprefix("data:").strip()))
                        if len(received) >= 3:
                            return

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.1)  # let SSE subscriber register

        for node in ("intake", "triage", "context"):
            record_event(StatusEvent(request_id=rid, node=node, status="done"))

        await asyncio.wait_for(task, timeout=2.0)

    assert [e["node"] for e in received] == ["intake", "triage", "context"]
