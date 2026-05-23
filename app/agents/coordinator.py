"""
Coordinator — the orchestration brain (the foundation layer).

Sequences the specialist agents and applies the RISK GATE, which is the most
important policy in the whole system per the personas doc: humans stay in
emotional / financial / legal / high-cost moments (lines 676, 753, 788).

This is deliberately a deterministic workflow (predictable for a live demo)
that *calls* LLM-backed agents for the fuzzy sub-tasks. That hybrid is exactly
the doc's insight: a process map for the skeleton, context+LLM for the judgment.
"""
from __future__ import annotations

from app.agents import comms
from app.agents.triage import triage
from app.core.repository import record_event, upsert_ticket
from app.core.schemas import (
    Decision,
    Diagnosis,
    InboundRequest,
    IssueCategory,
    OrchestratorResponse,
    Sentiment,
    StatusEvent,
    Urgency,
)
from app.tools.property_tools import lookup_property_context, select_vendor


def _emit(request_id: str, node: str, status: str, detail: str = "") -> None:
    """Write a status event (drives the live BPMN dashboard)."""
    record_event(StatusEvent(request_id=request_id, node=node, status=status, detail=detail))


def _risk_gate(diag: Diagnosis, estimated_cost: float, threshold: float) -> tuple[Decision, str]:
    """Return (decision, reason). Escalate on cost, sentiment, or legal."""
    if diag.category == IssueCategory.legal:
        return Decision.escalate_human, "Legal matters require a human."
    if diag.category == IssueCategory.financial:
        return Decision.escalate_human, "Financial questions are human-reviewed."
    if diag.sentiment == Sentiment.angry:
        return Decision.escalate_human, "Caller is upset; a person should respond."
    if estimated_cost > threshold:
        return (
            Decision.escalate_human,
            f"Estimated EUR {estimated_cost:.0f} exceeds approval threshold "
            f"of EUR {threshold:.0f}.",
        )
    return Decision.auto_resolve, ""


def handle_request(req: InboundRequest) -> OrchestratorResponse:
    trace: list[str] = []
    rid = req.request_id

    _emit(rid, "intake", "done", f"{req.channel.value}: {req.raw_text[:60]}")
    trace.append(f"Intake via {req.channel.value}")

    # 1. Triage (dispatcher persona)
    _emit(rid, "triage", "started")
    diag = triage(req.raw_text, req.detected_sentiment)
    _emit(rid, "triage", "done", f"{diag.category.value}/{diag.urgency.value}/{diag.sentiment.value}")
    trace.append(f"Triaged: {diag.category.value}, urgency {diag.urgency.value}, "
                 f"sentiment {diag.sentiment.value}")

    # 2. Retrieve property context (property memory)
    _emit(rid, "context", "started")
    ctx = lookup_property_context(req.property_hint)
    _emit(rid, "context", "done", f"{ctx.property_name}, mgr {ctx.manager_name}")
    trace.append(f"Context: {ctx.property_name} (manager {ctx.manager_name})")

    # 3. Vendor selection (contractor coordination)
    vendor_plan = None
    if diag.category not in (IssueCategory.financial, IssueCategory.legal):
        _emit(rid, "vendor", "started")
        vendor_plan = select_vendor(diag.category, ctx)
        _emit(rid, "vendor", "done",
              f"{vendor_plan.vendor_name} @ EUR {vendor_plan.estimated_cost_eur:.0f}")
        trace.append(f"Vendor: {vendor_plan.vendor_name}, "
                     f"est EUR {vendor_plan.estimated_cost_eur:.0f}")

    # 4. Risk gate
    _emit(rid, "risk_gate", "started")
    est_cost = vendor_plan.estimated_cost_eur if vendor_plan else 0.0
    decision, reason = _risk_gate(diag, est_cost, ctx.approval_threshold_eur)
    _emit(rid, "risk_gate", "done", decision.value + (f": {reason}" if reason else ""))
    trace.append(f"Decision: {decision.value}" + (f" ({reason})" if reason else ""))

    # 5. Draft communications (comms agent)
    _emit(rid, "comms", "started")
    escalated = decision == Decision.escalate_human
    msgs = {
        "tenant": comms.draft_tenant_message(diag, vendor_plan, escalated),
    }
    if vendor_plan and not escalated:
        msgs["vendor"] = comms.draft_vendor_message(diag, ctx, vendor_plan)
    msgs = comms.polish(msgs)
    _emit(rid, "comms", "done", "messages drafted")
    trace.append("Drafted tenant" + (" + vendor" if "vendor" in msgs else "") + " messages")

    # 6. Persist (case memory — every resolution improves the next)
    upsert_ticket(
        rid,
        channel=req.channel.value,
        raw_text=req.raw_text,
        category=diag.category.value,
        urgency=diag.urgency.value,
        sentiment=diag.sentiment.value,
        decision=decision.value,
        payload={"vendor": vendor_plan.model_dump() if vendor_plan else None},
    )
    _emit(rid, "closed", "done", "ticket stored")

    return OrchestratorResponse(
        request_id=rid,
        decision=decision,
        diagnosis=diag,
        vendor_plan=vendor_plan if not escalated else None,
        tenant_message=msgs.get("tenant"),
        vendor_message=msgs.get("vendor"),
        escalation_reason=reason or None,
        trace=trace,
    )
