"""ElevenLabs server-tool webhook adapter.

ElevenLabs Agents call this endpoint mid-conversation when the voice agent
decides to dispatch maintenance. We must respond within ~1.5s (the agent's
hard timeout is ~5s) so the orchestration runs in a BackgroundTask and the
full result is delivered to the dashboard via SSE.

Contract (DEV3_CONTEXT.md §5.4):
  POST /webhooks/elevenlabs/tool
  Header: X-Webhook-Secret: <env>
  Body : { tool_name, conversation_id, caller_id, parameters: {...} }
  Resp : { ticket_id, agent_message }
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel, Field

from app.agents.coordinator import handle_request
from app.core.repository import events_for, upsert_ticket
from app.core.schemas import Channel, InboundRequest
from app.core.settings import settings

router = APIRouter()

_STOCK_ACK = "Got it — I'm dispatching maintenance now. We'll text you once a vendor is scheduled."


class ElevenLabsToolParams(BaseModel):
    issue_summary: str
    category_hint: str | None = None
    urgency_hint: str | None = None
    property_hint: str | None = None
    reporter_name: str | None = None


class ElevenLabsToolCall(BaseModel):
    tool_name: str
    conversation_id: str = Field(..., description="Used as InboundRequest.request_id")
    caller_id: str | None = None
    parameters: ElevenLabsToolParams


class ElevenLabsToolResponse(BaseModel):
    ticket_id: str
    agent_message: str


def _to_inbound(call: ElevenLabsToolCall) -> InboundRequest:
    return InboundRequest(
        request_id=call.conversation_id,
        channel=Channel.phone,
        raw_text=call.parameters.issue_summary,
        reporter_name=call.parameters.reporter_name,
        reporter_phone=call.caller_id,
        property_hint=call.parameters.property_hint,
    )


def _run_orchestration(req: InboundRequest) -> None:
    """Background task. Failures are logged via stderr — the agent already
    heard the stock acknowledgement, so a 500 here doesn't surface to the
    caller. The dashboard will simply lack a `closed` event."""
    try:
        handle_request(req)
    except Exception as exc:  # noqa: BLE001 — defensive, last line of defense
        import sys

        print(f"orchestration failed for {req.request_id}: {exc}", file=sys.stderr)


@router.post("/webhooks/elevenlabs/tool", response_model=ElevenLabsToolResponse)
def elevenlabs_tool(
    call: ElevenLabsToolCall,
    background: BackgroundTasks,
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
) -> ElevenLabsToolResponse:
    if x_webhook_secret != settings.webhook_secret:
        raise HTTPException(status_code=401, detail="bad webhook secret")

    req = _to_inbound(call)
    background.add_task(_run_orchestration, req)

    return ElevenLabsToolResponse(
        ticket_id=req.request_id,
        agent_message=_STOCK_ACK,
    )


class ElevenLabsPostCall(BaseModel):
    """Post-call webhook payload.

    ElevenLabs fires this after a conversation ends with a transcript summary
    and metadata. We attach it to the ticket so the dashboard can show the
    final call outcome without re-running orchestration.
    """

    conversation_id: str
    transcript_summary: str | None = None
    transcript: str | None = None
    duration_seconds: float | None = None
    success: bool | None = None


@router.post("/webhooks/elevenlabs/post-call")
def elevenlabs_post_call(
    body: ElevenLabsPostCall,
    background: BackgroundTasks,
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
) -> dict:
    if x_webhook_secret != settings.webhook_secret:
        raise HTTPException(status_code=401, detail="bad webhook secret")

    existing = events_for(body.conversation_id)

    # Enrich/create ticket with post-call metadata
    upsert_ticket(
        body.conversation_id,
        payload={
            "post_call": {
                "transcript_summary": body.transcript_summary,
                "transcript": body.transcript,
                "duration_seconds": body.duration_seconds,
                "success": body.success,
            }
        },
    )

    # If no tool-call ticket was created mid-conversation but we have a
    # transcript, run the pipeline now so the dashboard gets a full result.
    triggered = False
    if not existing and body.transcript and body.transcript.strip():
        req = InboundRequest(
            request_id=body.conversation_id,
            channel=Channel.phone,
            raw_text=body.transcript.strip(),
        )
        background.add_task(_run_orchestration, req)
        triggered = True

    return {
        "ticket_id": body.conversation_id,
        "matched_existing": bool(existing),
        "pipeline_triggered": triggered,
    }
