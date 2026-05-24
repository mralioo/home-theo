"""
ADK web UI entry point for the triage agent.
Wraps the LlmAgent defined in app/agents/llm_triage so it is discoverable
by `adk web adk_agents` (each subdirectory = one agent, must export root_agent).
"""

import os
import sys

# Ensure app.* imports resolve when adk web is run from /srv
sys.path.insert(0, os.environ.get("PYTHONPATH", "/srv"))

from app.agents.llm_triage import _triage_agent  # noqa: E402

root_agent = _triage_agent
