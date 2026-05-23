"""In-memory pub/sub for StatusEvent.

Bridges sync `record_event` (called from the deterministic coordinator) to
async SSE subscribers. The coordinator runs in FastAPI's threadpool (sync def
routes) but SSE subscribers are async — `publish` uses run_coroutine_threadsafe
to cross that boundary safely.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from typing import AsyncIterator

from app.core.schemas import StatusEvent

_BACKLOG_SIZE = 200
_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
_backlog: dict[str, deque[StatusEvent]] = defaultdict(lambda: deque(maxlen=_BACKLOG_SIZE))
_loop: asyncio.AbstractEventLoop | None = None


def attach_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Called once on FastAPI startup so sync code can publish."""
    global _loop
    _loop = loop


def publish(event: StatusEvent) -> None:
    """Safe to call from sync OR async code."""
    _backlog[event.request_id].append(event)
    queues = list(_subscribers[event.request_id])
    if not queues:
        return

    async def _fanout() -> None:
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow consumer — drop

    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    if running is not None:
        # Caller is already on an asyncio loop — dispatch directly.
        asyncio.create_task(_fanout())
    elif _loop is not None and not _loop.is_closed():
        # Sync caller (coordinator threadpool) — bridge into the stored loop.
        asyncio.run_coroutine_threadsafe(_fanout(), _loop)
    # else: no way to deliver — drop. Backlog still preserves the event.


async def subscribe(request_id: str) -> AsyncIterator[StatusEvent]:
    """Subscribe to events for a request. Replays backlog, then streams live."""
    q: asyncio.Queue[StatusEvent] = asyncio.Queue(maxsize=100)
    _subscribers[request_id].add(q)
    try:
        for ev in list(_backlog[request_id]):
            yield ev
        while True:
            yield await q.get()
    finally:
        _subscribers[request_id].discard(q)
