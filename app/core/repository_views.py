"""Read-only query layer for the role-aware dashboard SPA.

Separate from repository.py (which owns writes) so the SPA routes
can import just what they need without pulling in the write path.
"""

from __future__ import annotations

import json

from app.core.repository import _conn


def list_tickets(limit: int = 50, decision: str | None = None) -> list[dict]:
    """Return tickets newest-first, optionally filtered by decision value."""
    if decision:
        rows_q = (
            "SELECT request_id, channel, raw_text, category, urgency, sentiment, "
            "decision, payload_json, created_at FROM tickets "
            "WHERE decision=? ORDER BY created_at DESC LIMIT ?"
        )
        params: tuple = (decision, limit)
    else:
        rows_q = (
            "SELECT request_id, channel, raw_text, category, urgency, sentiment, "
            "decision, payload_json, created_at FROM tickets "
            "ORDER BY created_at DESC LIMIT ?"
        )
        params = (limit,)

    with _conn() as c:
        rows = c.execute(rows_q, params).fetchall()

    result = []
    for r in rows:
        t = dict(r)
        try:
            t["payload"] = json.loads(t.pop("payload_json") or "{}")
        except Exception:
            t["payload"] = {}
        result.append(t)
    return result
