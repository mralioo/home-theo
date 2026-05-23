"""Unit tests for in-memory event bus."""
import asyncio

import pytest

from app.core import event_bus
from app.core.schemas import StatusEvent


async def _drain(request_id: str, n: int) -> list[StatusEvent]:
    received: list[StatusEvent] = []
    async for ev in event_bus.subscribe(request_id):
        received.append(ev)
        if len(received) >= n:
            break
    return received


@pytest.mark.asyncio
async def test_subscribe_receives_live_events():
    rid = "live-1"

    task = asyncio.create_task(_drain(rid, 2))
    await asyncio.sleep(0.05)  # let subscriber register

    event_bus.publish(StatusEvent(request_id=rid, node="intake", status="started"))
    event_bus.publish(StatusEvent(request_id=rid, node="intake", status="done"))

    received = await asyncio.wait_for(task, timeout=1.0)
    assert [(e.node, e.status) for e in received] == [
        ("intake", "started"),
        ("intake", "done"),
    ]


@pytest.mark.asyncio
async def test_backlog_replayed_to_late_subscriber():
    rid = "backlog-1"

    event_bus.publish(StatusEvent(request_id=rid, node="triage", status="started"))
    event_bus.publish(StatusEvent(request_id=rid, node="triage", status="done"))

    received = await asyncio.wait_for(_drain(rid, 2), timeout=1.0)
    assert [(e.node, e.status) for e in received] == [
        ("triage", "started"),
        ("triage", "done"),
    ]
