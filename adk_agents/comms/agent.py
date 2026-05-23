"""
ADK web UI entry point for the comms agent.
Wraps the LlmAgent defined in app/agents/llm_comms so it is discoverable
by `adk web adk_agents` (each subdirectory = one agent, must export root_agent).
"""
import os
import sys

sys.path.insert(0, os.environ.get("PYTHONPATH", "/srv"))

from app.agents.llm_comms import _comms_agent  # noqa: E402

root_agent = _comms_agent
