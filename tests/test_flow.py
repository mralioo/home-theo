"""
Tests for the deterministic (offline) orchestration path. No API key needed.
Run: pytest -q
"""

import os
import tempfile

# Use a throwaway DB per test run.
os.environ["DB_PATH"] = os.path.join(tempfile.gettempdir(), "ops_test.db")
os.environ["USE_LLM"] = "0"

from app.agents.coordinator import handle_request  # noqa: E402
from app.core.repository import init_db  # noqa: E402
from app.core.schemas import Channel, Decision, InboundRequest  # noqa: E402

init_db()


def _req(text, **kw):
    return InboundRequest(
        request_id=kw.pop("rid", "t1"), channel=Channel.phone, raw_text=text, **kw
    )


def test_low_cost_heating_auto_resolves():
    r = handle_request(
        _req(
            "The heating is not working, please help.",
            property_hint="Musterstrasse 12",
            rid="r-heat",
        )
    )
    assert r.decision == Decision.auto_resolve
    assert r.diagnosis.category.value == "heating"
    assert r.vendor_plan is not None
    assert r.tenant_message is not None
    assert "Thermo" in r.vendor_message
    assert r.vendor_plan.estimated_cost_eur < ctx_threshold()


def ctx_threshold():
    from app.tools.property_tools import lookup_property_context

    return lookup_property_context("Musterstrasse 12").approval_threshold_eur


def test_financial_escalates_to_human():
    r = handle_request(
        _req("Why was this invoice charged to me?", property_hint="Musterstrasse 12", rid="r-fin")
    )
    assert r.decision == Decision.escalate_human
    assert r.vendor_plan is None


def test_angry_sentiment_escalates():
    r = handle_request(
        _req(
            "This is the third time! Unacceptable!!!",
            property_hint="Musterstrasse 12",
            rid="r-angry",
        )
    )
    assert r.decision == Decision.escalate_human


def test_emergency_detected():
    r = handle_request(
        _req("There is flooding in the basement!", property_hint="Musterstrasse 12", rid="r-flood")
    )
    assert r.diagnosis.urgency.value == "emergency"
