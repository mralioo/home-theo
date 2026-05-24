"""
Tools the agents call. Each is a plain function with a typed signature so it
can be (a) unit-tested, (b) mocked, (c) swapped for the real thing later
without touching agent logic.

Priority order for lookup:
  1. Context service (OpenSearch vector DB) when CONTEXT_SERVICE_URL is set
  2. JSON fixture fallback — always works offline / in tests
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import httpx

from app.core.schemas import IssueCategory, PropertyContext, VendorPlan

logger = logging.getLogger(__name__)

_FIXTURES = Path(__file__).resolve().parent.parent.parent / "data" / "property_memory.json"
_CTX_URL = os.environ.get("CONTEXT_SERVICE_URL", "").rstrip("/")

_CATEGORY_HOURS: dict[str, float] = {
    "heating": 3.0,
    "plumbing": 2.5,
    "electrical": 2.5,
    "elevator": 6.0,
    "access_keys": 1.0,
    "cleaning": 2.0,
}

# ── Helpers ───────────────────────────────────────────────────────────────────


def _recent_cases_from_incidents(incidents: list[dict]) -> list[str]:
    lines = []
    for inc in incidents[:5]:
        date = inc.get("date", "")[:7]
        cat = inc.get("category", "")
        res = inc.get("resolution", "")[:60]
        cost = inc.get("cost_eur")
        cost_str = f", EUR {cost:.0f}" if cost else ""
        lines.append(f"{date}: {cat} — {res}{cost_str}")
    return lines


def _vendor_doc_to_plan(vendor: dict, category: str) -> VendorPlan:
    rate = vendor.get("hourly_rate_eur", 80.0)
    hours = _CATEGORY_HOURS.get(category, 2.0)
    surcharge = 1 + vendor.get("emergency_surcharge_pct", 0) / 100
    return VendorPlan(
        vendor_id=vendor["id"],
        vendor_name=vendor["name"],
        proposed_window="tomorrow 09:00-12:00",
        estimated_cost_eur=round(rate * hours * surcharge, 0),
    )


def _building_doc_to_context(doc: dict, incidents: list[dict]) -> PropertyContext:
    return PropertyContext(
        property_id=doc["id"],
        property_name=doc.get("name", doc["id"]),
        manager_name=doc.get("manager_name", "Unassigned"),
        access_notes=doc.get("access_notes", "No access notes on file."),
        key_holder=doc.get("key_holder", "Unknown"),
        preferred_vendors=doc.get("preferred_vendors", {}),
        approval_threshold_eur=float(doc.get("approval_threshold_eur", 500.0)),
        recent_cases=_recent_cases_from_incidents(incidents),
    )


# ── Context service client ────────────────────────────────────────────────────


def _ctx_lookup_building(hint: str) -> PropertyContext | None:
    try:
        r = httpx.get(
            f"{_CTX_URL}/buildings/search",
            params={"q": hint, "top_k": 1},
            timeout=5.0,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return None
        doc = results[0]
        # Also pull recent incidents for this building
        ri = httpx.get(
            f"{_CTX_URL}/incidents/search",
            params={"building_id": doc["id"], "top_k": 5},
            timeout=5.0,
        )
        incidents = ri.json().get("results", []) if ri.is_success else []
        return _building_doc_to_context(doc, incidents)
    except Exception as exc:
        logger.warning("Context service unavailable (%s) — using fixture", exc)
        return None


def _ctx_select_vendor(category: str, preferred_ids: dict) -> VendorPlan | None:
    try:
        r = httpx.get(
            f"{_CTX_URL}/vendors/search",
            params={"category": category, "top_k": 5},
            timeout=5.0,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return None
        # Prefer a vendor listed in the building's preferred_vendors
        preferred_id = preferred_ids.get(category)
        vendor = next((v for v in results if v["id"] == preferred_id), results[0])
        return _vendor_doc_to_plan(vendor, category)
    except Exception as exc:
        logger.warning("Vendor search failed (%s) — using fallback", exc)
        return None


# ── Public API ────────────────────────────────────────────────────────────────


def lookup_property_context(property_hint: str | None) -> PropertyContext:
    hint = (property_hint or "").strip()

    if _CTX_URL and hint:
        ctx = _ctx_lookup_building(hint)
        if ctx:
            return ctx

    # Fixture fallback
    data = json.loads(_FIXTURES.read_text())
    key = hint.lower()
    record = data.get(key) or data["_default"]
    return PropertyContext(**record)


def select_vendor(category: IssueCategory, ctx: PropertyContext) -> VendorPlan:
    cat = category.value

    if _CTX_URL:
        plan = _ctx_select_vendor(cat, ctx.preferred_vendors)
        if plan:
            return plan

    # Fixture fallback
    vendor_id = ctx.preferred_vendors.get(cat, "generic-handyman")
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
        estimated_cost_eur=cost_table.get(cat, 150.0),
    )


def send_message(to: str, channel: str, body: str) -> dict:
    """Stub — colleague replaces with ElevenLabs / Twilio."""
    print(f"[send_message] -> {to} via {channel}: {body[:80]}...")
    return {"status": "sent", "to": to, "channel": channel}
