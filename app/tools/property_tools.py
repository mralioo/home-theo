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

# Static fallback causes — used when no property-specific incident history exists
_PROBABLE_CAUSES: dict[str, list[str]] = {
    "heating": [
        "Pressure drop in circuit — expansion vessel membrane or relief valve fault",
        "Air lock after recent top-up or maintenance — bleed radiators",
        "Thermostat or zone valve stuck — no flow despite correct system pressure",
        "Boiler ignition or burner fault — check error code on display",
        "Circulation pump failure — listen for pump noise in plant room",
    ],
    "plumbing": [
        "Lime scale build-up in hot-water lines (common in hard-water areas)",
        "Blockage in waste pipe — hair, grease, or debris accumulation",
        "Dripping tap or toilet fill valve worn — replace washers or cartridge",
        "Pipe joint seeping — check under sinks and at radiator connections",
    ],
    "electrical": [
        "RCD/RCCB trip from appliance fault or moisture ingress",
        "Overloaded circuit — too many high-draw devices on same MCB",
        "Faulty light fitting or starter — flickering or no-light fault",
        "Aging MCB — contact fatigue or spring failure in older fuseboxes",
    ],
    "elevator": [
        "Door sensor dirty or misaligned — most common cause of door faults",
        "Worn brake pads or brake lining — annual service item",
        "Buffer lubrication overdue — causes jerky movement in shaft",
        "Door cam or door clutch worn — doors not opening or closing cleanly",
    ],
    "access_keys": [
        "Cylinder barrel wear from frequent use — replacement likely",
        "Door closer tension misadjusted — door not latching fully",
        "Magnetic lock power supply fault — check 12V PSU in controller cabinet",
        "Access card reader head dirty or worn",
    ],
    "cleaning": [
        "Deep-clean schedule overdue — check last service date",
        "Waste separation not being followed — resident information required",
        "Bulk waste deposited — waste collection appointment needed",
        "Bin room drain blocked or odour from organic waste",
    ],
    "financial": [],
    "legal": [],
    "other": [],
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


def _probable_causes_from_incidents(incidents: list[dict], category: str) -> list[str]:
    """Derive cause hints from past incidents matching this category.

    Falls back to static knowledge base when no matching history exists.
    """
    causes = []
    for inc in incidents:
        if inc.get("category") != category:
            continue
        desc = inc.get("description", "")
        date = inc.get("date", "")[:7]
        if desc:
            causes.append(f"Recurring ({date}): {desc[:110]}")
    return causes or _PROBABLE_CAUSES.get(category, [])


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


def _building_doc_to_context(
    doc: dict, incidents: list[dict], category: str | None = None
) -> PropertyContext:
    return PropertyContext(
        property_id=doc["id"],
        property_name=doc.get("name", doc["id"]),
        manager_name=doc.get("manager_name", "Unassigned"),
        access_notes=doc.get("access_notes", "No access notes on file."),
        key_holder=doc.get("key_holder", "Unknown"),
        preferred_vendors=doc.get("preferred_vendors", {}),
        approval_threshold_eur=float(doc.get("approval_threshold_eur", 500.0)),
        recent_cases=_recent_cases_from_incidents(incidents),
        probable_causes=(
            _probable_causes_from_incidents(incidents, category) if category else []
        ),
    )


# ── Context service client ────────────────────────────────────────────────────


def _ctx_lookup_building(
    hint: str,
    category: str | None = None,
    raw_text: str | None = None,
) -> PropertyContext | None:
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

        # Pull category-filtered incidents for probable cause derivation
        incident_params: dict = {"building_id": doc["id"], "top_k": 5}
        if category:
            incident_params["category"] = category
        ri = httpx.get(f"{_CTX_URL}/incidents/search", params=incident_params, timeout=5.0)
        incidents = ri.json().get("results", []) if ri.is_success else []

        ctx = _building_doc_to_context(doc, incidents, category)
        rag_enriched = False

        # RAG enrichment: semantic search over all incidents using raw complaint text
        if raw_text and category:
            try:
                pc = httpx.get(
                    f"{_CTX_URL}/probable-causes/search",
                    params={
                        "q": raw_text,
                        "building_id": doc["id"],
                        "category": category,
                        "top_k": 5,
                    },
                    timeout=5.0,
                )
                if pc.is_success:
                    rag_causes = pc.json().get("probable_causes", [])
                    if rag_causes:
                        ctx.probable_causes = rag_causes
                        rag_enriched = True
            except Exception:
                pass  # RAG enrichment is best-effort; base causes already set

        ctx.retrieval_meta = {
            "source": "context_service",
            "building_id": doc["id"],
            "incidents_fetched": len(incidents),
            "category_filter": category or "all",
            "rag_enriched": rag_enriched,
            "embedding_model": "BAAI/bge-small-en-v1.5",
        }
        return ctx
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


def lookup_property_context(
    property_hint: str | None,
    category: IssueCategory | None = None,
    raw_text: str | None = None,
) -> PropertyContext:
    hint = (property_hint or "").strip()
    cat_str = category.value if category else None

    if _CTX_URL and hint:
        ctx = _ctx_lookup_building(hint, category=cat_str, raw_text=raw_text)
        if ctx:
            return ctx

    # Fixture fallback
    data = json.loads(_FIXTURES.read_text())
    key = hint.lower()
    matched_key = key if key in data else "_default"
    record = data.get(key) or data["_default"]
    ctx = PropertyContext(**record)
    if cat_str:
        by_cat = record.get("probable_causes_by_category", {})
        ctx.probable_causes = by_cat.get(cat_str) or _PROBABLE_CAUSES.get(cat_str, [])
    ctx.retrieval_meta = {
        "source": "fixture",
        "file": "data/property_memory.json",
        "key_matched": matched_key,
        "incidents_fetched": len(record.get("incidents", [])),
        "category_filter": cat_str or "all",
        "rag_enriched": False,
        "embedding_model": None,
    }
    return ctx


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
