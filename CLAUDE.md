# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Transport-agnostic orchestration layer for German property management (WEG/SEV). A voice/channel layer (ElevenLabs, colleague's system) POSTs to this service; this layer triages, fetches property context, selects a vendor, applies a risk gate, drafts messages, and emits BPMN status events.

Runs in two modes controlled by `USE_LLM` env var:
- `USE_LLM=0` (default): deterministic keyword heuristics + templates, zero external calls — always demo-safe
- `USE_LLM=1`: ADK `LlmAgent` + Claude via LiteLLM for triage and comms polish

## Commands

```bash
# Run tests (offline, no key needed)
PYTHONPATH=. pytest -q

# Run single test
PYTHONPATH=. pytest -q tests/test_flow.py::test_low_cost_heating_auto_resolves

# Start local server (offline demo)
cp .env.example .env
docker compose up --build

# Step through agent traces visually (ADK dev UI)
pip install -r requirements.txt
adk web app/agents

# Hit the API
curl -X POST localhost:8080/api/requests -H 'Content-Type: application/json' \
  -d '{"request_id":"d1","channel":"phone","raw_text":"Heating broken","property_hint":"Musterstrasse 12"}'
curl localhost:8080/api/requests/d1/status
```

## Architecture

```
InboundRequest (POST /api/requests)
        │
        ▼
coordinator.handle_request()          ← deterministic orchestration skeleton
  ├── triage()                         → Diagnosis (category, urgency, sentiment)
  │     └── triage_llm() if USE_LLM=1  (ADK LlmAgent, returns structured JSON)
  ├── lookup_property_context()        → PropertyContext from data/property_memory.json fixture
  ├── select_vendor()                  → VendorPlan (mocked cost + window)
  ├── _risk_gate()                     → Decision (auto_resolve | escalate_human)
  ├── comms.draft_*() + polish()       → tenant/vendor messages
  │     └── polish_llm() if USE_LLM=1
  └── upsert_ticket() + record_event() → SQLite (repository.py)
        │
        ▼
OrchestratorResponse + StatusEvents (GET /api/requests/{id}/status for dashboard)
```

**Risk gate policy** (`coordinator._risk_gate`): always escalate for `legal`, `financial`, `angry` sentiment, or cost exceeding `approval_threshold_eur` from the property fixture. This is the most important business rule.

**`app/core/schemas.py` is the merge seam** — the shared contract with the voice layer. Never rename fields without coordinating with the colleague's ElevenLabs integration.

**LLM agents are isolated** in `app/agents/llm_triage.py` and `app/agents/llm_comms.py`, imported lazily. Any exception there falls back to deterministic mode silently — the demo never dies on a model error.

**`google-adk` is pinned** (bi-weekly breaking releases). Bump it only deliberately and test `USE_LLM=1` paths after.

## Key files

| File | Role |
|---|---|
| `app/core/schemas.py` | Shared types — merge seam with voice layer |
| `app/agents/coordinator.py` | Orchestration brain + risk gate |
| `app/agents/triage.py` / `llm_triage.py` | Dispatcher persona, dual mode |
| `app/agents/comms.py` / `llm_comms.py` | Message drafting, dual mode |
| `app/tools/property_tools.py` | Property memory lookup + vendor selection (mocked) |
| `app/core/repository.py` | All DB access (SQLite; swap URL for Cloud SQL) |
| `data/property_memory.json` | Property fixture — source of `PropertyContext` |

## Env vars

| Var | Default | Purpose |
|---|---|---|
| `USE_LLM` | `0` | `1` enables ADK + Claude path |
| `ANTHROPIC_API_KEY` | — | Required only when `USE_LLM=1` |
| `LITELLM_MODEL` | `anthropic/claude-sonnet-4-5-20250929` | Model for both LLM agents |
| `DB_PATH` | `/data/ops.db` | SQLite path; override in tests |
