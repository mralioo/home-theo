"""
LLM-backed message polishing using ADK + Claude. Optional (USE_LLM=1).
Rewrites the template messages into a warm, on-brand German-property-manager
voice without changing any facts.
"""

from __future__ import annotations

import json
import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

_MODEL = os.environ.get("LITELLM_MODEL", "anthropic/claude-sonnet-4-5-20250929")

_INSTRUCTION = """You rewrite property-management messages to be warm, concise,
and reassuring, keeping every fact identical. Tenants want clarity and to feel
heard; do not invent details. You receive a JSON object mapping recipient ->
draft. Return ONLY a JSON object with the same keys and improved values.
"""

_comms_agent = LlmAgent(
    name="comms_agent",
    model=LiteLlm(model=_MODEL),
    instruction=_INSTRUCTION,
)


def polish_llm(messages: dict[str, str]) -> dict[str, str]:
    runner = InMemoryRunner(agent=_comms_agent, app_name="ops")
    session = runner.session_service.create_session_sync(app_name="ops", user_id="system")
    content = types.Content(role="user", parts=[types.Part(text=json.dumps(messages))])
    final = ""
    for event in runner.run(user_id="system", session_id=session.id, new_message=content):
        if event.is_final_response() and event.content and event.content.parts:
            final = event.content.parts[0].text or ""
    final = final.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        polished = json.loads(final)
        # Only keep keys we sent; never let the model add recipients
        return {k: polished.get(k, v) for k, v in messages.items()}
    except Exception:
        return messages
