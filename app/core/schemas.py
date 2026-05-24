"""
Shared contract between the VOICE/CHANNEL layer (colleague) and the
ORCHESTRATION layer (you).

This is the merge seam. Agree on this file first; do not change field names
without telling your colleague. Everything is transport-agnostic: the
orchestrator never knows if the request came from a phone call, SMS, or chat.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(UTC)


class Channel(StrEnum):
    phone = "phone"
    sms = "sms"
    email = "email"
    chat = "chat"
    walk_in = "walk_in"


class IssueCategory(StrEnum):
    """Grounded in the personas doc: heating, plumbing, electrical, access,
    cleaning, financial, legal, other. Triage maps free text onto these."""

    heating = "heating"
    plumbing = "plumbing"
    electrical = "electrical"
    elevator = "elevator"
    access_keys = "access_keys"
    cleaning = "cleaning"
    financial = "financial"
    legal = "legal"
    other = "other"


class Urgency(StrEnum):
    emergency = "emergency"  # fire, flooding, no heat in winter
    high = "high"
    normal = "normal"
    low = "low"


class Sentiment(StrEnum):
    angry = "angry"
    frustrated = "frustrated"
    neutral = "neutral"
    calm = "calm"


# ---- INBOUND: what the voice layer sends us -------------------------------


class InboundRequest(BaseModel):
    """Normalized request the voice/channel layer POSTs to /api/requests."""

    request_id: str = Field(..., description="Idempotency key from the caller")
    channel: Channel
    raw_text: str = Field(..., description="Transcript or message body")
    # Optional hints the voice layer may already have resolved:
    reporter_name: str | None = None
    reporter_phone: str | None = None
    property_hint: str | None = None
    detected_sentiment: Sentiment | None = None
    received_at: datetime = Field(default_factory=_now)


# ---- INTERNAL: enriched understanding produced by the agents --------------


class Diagnosis(BaseModel):
    category: IssueCategory
    urgency: Urgency
    sentiment: Sentiment
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)


class PropertyContext(BaseModel):
    """The 'property memory' from the doc (Priority 2)."""

    property_id: str
    property_name: str
    manager_name: str
    access_notes: str
    key_holder: str
    preferred_vendors: dict[str, str]  # category -> vendor_id
    approval_threshold_eur: float
    recent_cases: list[str] = Field(default_factory=list)


class VendorPlan(BaseModel):
    vendor_id: str
    vendor_name: str
    proposed_window: str
    estimated_cost_eur: float


# ---- OUTBOUND: what we hand back to the voice layer -----------------------


class Decision(StrEnum):
    auto_resolve = "auto_resolve"
    escalate_human = "escalate_human"
    need_more_info = "need_more_info"


class OrchestratorResponse(BaseModel):
    request_id: str
    decision: Decision
    diagnosis: Diagnosis | None = None
    vendor_plan: VendorPlan | None = None
    tenant_message: str | None = None  # drafted by comms agent
    vendor_message: str | None = None
    escalation_reason: str | None = None
    trace: list[str] = Field(default_factory=list)  # human-readable steps


# ---- STATUS EVENTS: drive the live BPMN dashboard -------------------------


class StatusEvent(BaseModel):
    request_id: str
    node: str  # BPMN node id, e.g. "triage"
    status: str  # "started" | "done" | "skipped"
    detail: str = ""
    at: datetime = Field(default_factory=_now)
