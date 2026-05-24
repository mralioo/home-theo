"""Tests for the outbound vendor-call action and the post-call webhook.

All real HTTP traffic to ElevenLabs is intercepted with httpx.MockTransport
so the tests run offline and assert the exact URL + body shape sent to the
ElevenLabs Conversational AI endpoint.
"""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from app.core.repository import record_event
from app.core.schemas import StatusEvent
from app.core.settings import settings
from app.main import app
from app.tools import elevenlabs_outbound

client = TestClient(app)


def _seed_ticket(rid: str) -> None:
    """Plant a status_event so events_for(rid) returns truthy."""
    record_event(StatusEvent(request_id=rid, node="intake", status="done"))


def test_call_vendor_requires_admin_secret():
    resp = client.post(
        "/actions/call-vendor",
        json={"ticket_id": "x", "to_number": "+49"},
    )
    assert resp.status_code == 401


def test_call_vendor_unknown_ticket_returns_404(monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_api_key", "fake-key")
    resp = client.post(
        "/actions/call-vendor",
        json={"ticket_id": "ghost", "to_number": "+4915123456789"},
        headers={"X-Admin-Secret": settings.admin_secret},
    )
    assert resp.status_code == 404


def test_call_vendor_happy_path_posts_to_elevenlabs(monkeypatch):
    rid = "ticket-1"
    _seed_ticket(rid)
    monkeypatch.setattr(settings, "elevenlabs_api_key", "fake-key")
    monkeypatch.setattr(settings, "elevenlabs_agent_id_outbound", "agent_default")

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"conversation_id": "el_outbound_1", "ok": True})

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(elevenlabs_outbound.httpx, "AsyncClient", patched_client)

    resp = client.post(
        "/actions/call-vendor",
        json={"ticket_id": rid, "to_number": "+4915123456789"},
        headers={"X-Admin-Secret": settings.admin_secret},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticket_id"] == rid
    assert body["elevenlabs_response"]["ok"] is True

    # Wire-shape assertions
    assert captured["url"] == "https://api.elevenlabs.io/v1/convai/twilio/outbound-call"
    assert captured["method"] == "POST"
    assert captured["headers"]["xi-api-key"] == "fake-key"
    assert captured["body"]["to_number"] == "+4915123456789"
    assert captured["body"]["agent_id"] == "agent_default"
    assert (
        captured["body"]["conversation_initiation_client_data"]["dynamic_variables"]["ticket_id"]
        == rid
    )


def test_call_vendor_no_api_key_returns_502(monkeypatch):
    rid = "ticket-no-key"
    _seed_ticket(rid)
    monkeypatch.setattr(settings, "elevenlabs_api_key", "")

    resp = client.post(
        "/actions/call-vendor",
        json={"ticket_id": rid, "to_number": "+49"},
        headers={"X-Admin-Secret": settings.admin_secret},
    )
    assert resp.status_code == 502
    assert "ELEVENLABS_API_KEY" in resp.json()["detail"]


def test_post_call_webhook_rejects_bad_secret():
    resp = client.post(
        "/webhooks/elevenlabs/post-call",
        json={"conversation_id": "x"},
        headers={"X-Webhook-Secret": "wrong"},
    )
    assert resp.status_code == 401


def test_post_call_webhook_attaches_summary_to_ticket():
    rid = "ticket-postcall"
    _seed_ticket(rid)

    resp = client.post(
        "/webhooks/elevenlabs/post-call",
        json={
            "conversation_id": rid,
            "transcript_summary": "Vendor confirmed slot tomorrow 09:00.",
            "duration_seconds": 42.5,
            "success": True,
        },
        headers={"X-Webhook-Secret": settings.webhook_secret},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticket_id"] == rid
    assert body["matched_existing"] is True
