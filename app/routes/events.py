"""SSE endpoint for realtime status event streaming."""

from __future__ import annotations

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.core import event_bus

router = APIRouter()

# Keepalive cadence (seconds). sse-starlette sends `: ping` comments on this
# interval so Cloud Run / proxies don't drop idle connections.
_PING_SECONDS = 15


@router.get("/events/stream/{request_id}")
async def stream_events(request_id: str):
    """Stream StatusEvent JSON as SSE. Replays backlog, then streams live."""

    async def event_generator():
        async for ev in event_bus.subscribe(request_id):
            # sse-starlette wraps {"data": ...} into a `data:` SSE frame
            yield {"data": ev.model_dump_json()}

    return EventSourceResponse(event_generator(), ping=_PING_SECONDS)
