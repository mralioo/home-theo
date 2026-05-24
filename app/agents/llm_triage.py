"""
LLM-backed triage using Google ADK + Claude (via LiteLLM).
Only imported when USE_LLM=1, so the base system has zero ADK dependency at
import time and the demo still runs offline.

ADK is on a fast (≈bi-weekly) release cadence with occasional breaking
changes — pin google-adk in requirements.txt and keep this module isolated so
an ADK bump can't break the deterministic core.
"""

from __future__ import annotations

import json
import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.core.schemas import Diagnosis, IssueCategory, Sentiment, Urgency

_MODEL = os.environ.get("LITELLM_MODEL", "anthropic/claude-sonnet-4-5-20250929")

_INSTRUCTION = """You are the triage dispatcher for a German property
management company (WEG / SEV). Classify the incoming tenant or owner message.

Return ONLY a JSON object, no prose, with exactly these keys:
  category: one of [heating, plumbing, electrical, elevator, access_keys,
            cleaning, financial, legal, other]
  urgency: one of [emergency, high, normal, low]
  sentiment: one of [angry, frustrated, neutral, calm]
  summary: a one-sentence neutral summary (max 20 words)
  confidence: a float 0-1

Rules: fire, flooding, gas, or no heating in winter => emergency. Money or
invoice questions => financial. Anything about contracts/rights => legal.
"""

_triage_agent = LlmAgent(
    name="triage_agent",
    model=LiteLlm(model=_MODEL),
    instruction=_INSTRUCTION,
)


def _run_once(text: str) -> str:
    """Run the agent for a single message and return its final text."""
    runner = InMemoryRunner(agent=_triage_agent, app_name="ops")
    session = runner.session_service.create_session_sync(app_name="ops", user_id="system")
    content = types.Content(role="user", parts=[types.Part(text=text)])
    final = ""
    for event in runner.run(user_id="system", session_id=session.id, new_message=content):
        if event.is_final_response() and event.content and event.content.parts:
            final = event.content.parts[0].text or ""
    return final


def triage_llm(raw_text: str, hint_sentiment: Sentiment | None) -> Diagnosis:
    out = _run_once(raw_text).strip()
    # Strip accidental code fences
    out = out.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(out)
    return Diagnosis(
        category=IssueCategory(data["category"]),
        urgency=Urgency(data["urgency"]),
        sentiment=hint_sentiment or Sentiment(data["sentiment"]),
        summary=data["summary"],
        confidence=float(data["confidence"]),
    )
