"""Operator-triggered actions on existing tickets.

These are NOT mid-call webhooks (ElevenLabs → us) but the reverse direction:
we tell ElevenLabs to place an outbound call to a vendor for an existing
ticket. Currently exposed as a JSON-API; the dashboard hooks a button to it
in T6.
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.repository import events_for
from app.core.settings import settings
from app.tools.elevenlabs_outbound import OutboundCallError, start_outbound_call

router = APIRouter()


class CallVendorRequest(BaseModel):
    ticket_id: str = Field(..., description="Existing request_id in the orchestrator DB.")
    to_number: str = Field(..., description="E.164 vendor phone, e.g. +4915123456789.")
    agent_id: str | None = Field(
        default=None,
        description="Optional override of ELEVENLABS_AGENT_ID_OUTBOUND.",
    )


class CallVendorResponse(BaseModel):
    ticket_id: str
    elevenlabs_response: dict


@router.post("/actions/call-vendor", response_model=CallVendorResponse)
async def call_vendor(
    body: CallVendorRequest,
    x_admin_secret: str | None = Header(default=None, alias="X-Admin-Secret"),
) -> CallVendorResponse:
    if x_admin_secret != settings.admin_secret:
        raise HTTPException(status_code=401, detail="bad admin secret")

    # 404 if the ticket doesn't exist. `events_for` is the existing read path
    # that returns [] for unknown ids — same convention as /api/requests/{id}/status.
    if not events_for(body.ticket_id):
        raise HTTPException(status_code=404, detail="unknown ticket_id")

    try:
        resp = await start_outbound_call(
            to_number=body.to_number,
            agent_id=body.agent_id,
            metadata={"ticket_id": body.ticket_id},
        )
    except OutboundCallError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return CallVendorResponse(ticket_id=body.ticket_id, elevenlabs_response=resp)
