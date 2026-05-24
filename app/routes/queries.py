"""Read-only query endpoints that power the role-aware dashboard SPA."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.repository_views import list_tickets

router = APIRouter()


@router.get("/api/requests")
def list_requests(limit: int = 50, decision: str | None = None) -> dict:
    """Return all tickets, newest first. Optionally filter by decision value.

    decision: "auto_resolve" | "escalate_human" | "need_more_info"
    """
    tickets = list_tickets(limit=limit, decision=decision)
    return {"tickets": tickets, "total": len(tickets)}
