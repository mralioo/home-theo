"""
Tools the agents call. Each is a plain function with a typed signature so it
can be (a) unit-tested, (b) mocked, (c) swapped for the real thing later
without touching agent logic.

For the hackathon these read from a small in-repo fixture (the "property
memory"). On GCP you point them at Firestore / Cloud SQL / your colleague's
real vendor + messaging APIs.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.schemas import IssueCategory, PropertyContext, VendorPlan

_FIXTURES = Path(__file__).resolve().parent.parent.parent / "data" / "property_memory.json"


def lookup_property_context(property_hint: str | None) -> PropertyContext:
    """Retrieve the 'property memory' (doc Priority 2). In prod this is RAG
    over the property DB; here it reads a fixture and falls back to a default.
    """
    data = json.loads(_FIXTURES.read_text())
    key = (property_hint or "").strip().lower()
    record = data.get(key) or data["_default"]
    return PropertyContext(**record)


def select_vendor(category: IssueCategory, ctx: PropertyContext) -> VendorPlan:
    """Pick the preferred contractor for this category from property memory.
    Mirrors persona 5 (contractor) + the doc's 'preferred provider' field.
    """
    vendor_id = ctx.preferred_vendors.get(category.value, "generic-handyman")
    # Cost + window are stubbed; the real vendor agent (colleague) negotiates
    # these on a live ElevenLabs outbound call.
    cost_table = {
        "heating": 280.0,
        "plumbing": 180.0,
        "electrical": 220.0,
        "elevator": 650.0,
        "access_keys": 90.0,
        "cleaning": 70.0,
    }
    return VendorPlan(
        vendor_id=vendor_id,
        vendor_name=vendor_id.replace("-", " ").title(),
        proposed_window="tomorrow 09:00-12:00",
        estimated_cost_eur=cost_table.get(category.value, 150.0),
    )


def send_message(to: str, channel: str, body: str) -> dict:
    """Stub messaging. Locally this just logs; your colleague swaps this for
    ElevenLabs outbound voice / Twilio SMS. Returns a fake message id.
    """
    print(f"[send_message] -> {to} via {channel}: {body[:80]}...")
    return {"status": "sent", "to": to, "channel": channel}
