"""
Comms agent — drafts the human-facing messages (tenant updates, vendor work
orders). Maps to the 'clear status updates' gain across every persona.

Fallback mode uses templates so the demo always produces sensible text.
"""
from __future__ import annotations

import os

from app.core.schemas import Diagnosis, PropertyContext, VendorPlan


def draft_tenant_message(diag: Diagnosis, plan: VendorPlan | None, escalated: bool) -> str:
    if escalated:
        return (
            f"Thanks for reporting the {diag.category.value} issue. Because this "
            f"needs a manager's review, a member of our team will call you "
            f"personally within the hour. We have logged everything you told us."
        )
    if plan is None:
        return (
            f"Thanks for reporting the {diag.category.value} issue. We need a "
            f"little more detail before we dispatch someone — we'll be in touch."
        )
    return (
        f"Thanks for reporting the {diag.category.value} issue. We've arranged "
        f"{plan.vendor_name} to come {plan.proposed_window}. You don't need to do "
        f"anything else — we'll confirm once the visit is scheduled."
    )


def draft_vendor_message(diag: Diagnosis, ctx: PropertyContext, plan: VendorPlan) -> str:
    return (
        f"Work order for {plan.vendor_name} at {ctx.property_name}. "
        f"Issue: {diag.category.value} ({diag.urgency.value}). {diag.summary}. "
        f"Access: {ctx.access_notes} Key: {ctx.key_holder}. "
        f"Proposed window: {plan.proposed_window}. "
        f"Please confirm availability and estimated cost."
    )


def polish(messages: dict[str, str]) -> dict[str, str]:
    """Optionally rewrite templates in a warmer, on-brand voice via LLM."""
    if os.environ.get("USE_LLM") == "1":
        try:
            from app.agents.llm_comms import polish_llm
            return polish_llm(messages)
        except Exception as exc:
            print(f"[comms] LLM polish failed, using templates: {exc}")
    return messages
