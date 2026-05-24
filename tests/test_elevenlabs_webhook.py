"""Tests for the ElevenLabs server-tool webhook adapter."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.repository import events_for
from app.core.settings import settings
from app.main import app

client = TestClient(app)


def _payload(conv_id: str = "el_conv_test") -> dict:
    return {
        "tool_name": "dispatch_maintenance",
        "conversation_id": conv_id,
        "caller_id": "+4915123456789",
        "parameters": {
            "issue_summary": "Heating not working since yesterday",
            "category_hint": "heating",
            "urgency_hint": "high",
            "property_hint": "Musterstrasse 12",
            "reporter_name": "Frau Schmidt",
        },
    }


def test_webhook_rejects_missing_secret():
    resp = client.post("/webhooks/elevenlabs/tool", json=_payload())
    assert resp.status_code == 401


def test_webhook_rejects_bad_secret():
    resp = client.post(
        "/webhooks/elevenlabs/tool",
        json=_payload(),
        headers={"X-Webhook-Secret": "wrong"},
    )
    assert resp.status_code == 401


def test_webhook_accepts_and_kicks_orchestration():
    conv_id = "el_conv_ok"
    resp = client.post(
        "/webhooks/elevenlabs/tool",
        json=_payload(conv_id),
        headers={"X-Webhook-Secret": settings.webhook_secret},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticket_id"] == conv_id
    assert "dispatching" in body["agent_message"].lower()

    # BackgroundTask runs after the response is sent. TestClient blocks until
    # background tasks complete, so by the time we read events they should
    # be in the DB.
    events = events_for(conv_id)
    nodes = {e["node"] for e in events}
    assert {"intake", "triage", "context", "closed"}.issubset(nodes)


def test_webhook_invalid_body_returns_422():
    resp = client.post(
        "/webhooks/elevenlabs/tool",
        json={"tool_name": "x"},  # missing conversation_id, parameters
        headers={"X-Webhook-Secret": settings.webhook_secret},
    )
    assert resp.status_code == 422
