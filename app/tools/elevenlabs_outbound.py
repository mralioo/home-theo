"""ElevenLabs outbound-call wrapper.

Thin async client that hits the ElevenLabs Conversational AI REST endpoint
to place an outbound voice call to a vendor. Kept as a separate module so
the route handlers stay focused on adapter logic and can be unit-tested
with `httpx.MockTransport`.
"""

from __future__ import annotations

import httpx

from app.core.settings import settings

_OUTBOUND_URL = "https://api.elevenlabs.io/v1/convai/twilio/outbound-call"


class OutboundCallError(RuntimeError):
    """ElevenLabs returned a non-2xx for the outbound-call request."""


async def start_outbound_call(
    *,
    to_number: str,
    agent_id: str | None = None,
    metadata: dict | None = None,
    timeout: float = 10.0,
) -> dict:
    """Place a one-shot outbound call. Returns the ElevenLabs response body.

    `metadata` is sent in the call's initial context so the outbound agent
    knows the ticket_id, property, vendor, etc.
    """
    if not settings.elevenlabs_api_key:
        raise OutboundCallError("ELEVENLABS_API_KEY is not set")

    payload: dict = {
        "agent_id": agent_id or settings.elevenlabs_agent_id_outbound,
        "to_number": to_number,
    }
    if metadata:
        payload["conversation_initiation_client_data"] = {"dynamic_variables": metadata}

    headers = {
        "xi-api-key": settings.elevenlabs_api_key,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(_OUTBOUND_URL, json=payload, headers=headers)

    if resp.status_code >= 400:
        raise OutboundCallError(f"ElevenLabs {resp.status_code}: {resp.text}")
    return resp.json()
