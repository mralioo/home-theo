# Autonomous Tenant & Vendor Ops — Orchestration Layer

The **foundation layer**: a transport-agnostic agent orchestrator for property
management (German WEG / SEV). Your colleague's voice/channel layer (ElevenLabs)
calls this over HTTP; this layer triages, retrieves property context, picks a
vendor, applies a human-escalation risk gate, drafts messages, and streams
status events to a live role-aware dashboard.

## Why it's built this way
- **Transport-agnostic**: orchestrator never knows if a request was a call, SMS,
  or chat. Merge seam with the voice layer = `app/core/schemas.py`.
- **Dual mode**: runs fully **offline** (deterministic, no API key) for a
  reliable demo, and upgrades to **ADK + Claude** with `USE_LLM=1`.
- **Modular**: each agent + tool is a small unit. Tools are mocked now and
  swapped for the colleague's real vendor/messaging APIs later.
- **Same image local & cloud**: one Dockerfile for Compose and Cloud Run.

## Build status (in-flight on `feat/dev3-implementation`)

The Dev 3 glue/realtime/dashboard lane is being built on top of commit-1
(orchestration core by Dev 2). Progress so far:

| Task | Branch | Status | What landed |
|------|--------|--------|-------------|
| **T0** ci-baseline   | `feat/dev3-implementation` | ✅ committed | ruff + pyproject, GitHub Actions CI, pre-commit hooks, PR template, BPMN-id validator, `tests/conftest.py` DB reset, FastAPI `lifespan` (replaces deprecated `on_event`), `PRAGMA journal_mode=WAL` |
| **T1** event-bus     | `feat/dev3-implementation` | ✅ committed | `app/core/event_bus.py` — sync-safe in-memory pub/sub with 200-event backlog. One-line hook in `repository.record_event` fans events to subscribers. |
| **T2** SSE endpoint  | `feat/dev3-implementation` | ✅ committed | `GET /events/stream/{request_id}` via `sse-starlette` (15s keepalive ping). Replays backlog + streams live. Verified end-to-end with `curl -N`. |
| **T3** dashboard v0  | `feat/dev3-implementation` | ⚠️ skeleton landed, full UI in flight | `static/dashboard.{html,js,css}` + `diagram.bpmn` placeholder. **Direction has pivoted away from raw BPMN** — see "Dashboard direction" below. |
| **T4** ElevenLabs webhook | `feat/dev3-implementation` | ✅ committed | `POST /webhooks/elevenlabs/tool` with `X-Webhook-Secret` auth, pydantic adapter to `InboundRequest`, orchestration kicked via `BackgroundTasks` so the agent gets its stock ack in <1.5s. `app/core/settings.py` via pydantic-settings. |
| **T5** outbound vendor call | `feat/dev3-implementation` | ⏳ next | Post-call webhook + `POST /actions/call-vendor` via ElevenLabs REST. |
| **T6** dashboard polish | `feat/dev3-implementation` | ⏳ pending | Role-specific views, ticket card, admin reset, list endpoint. |
| **T7** demo runbook  | `feat/dev3-implementation` | ⏳ pending | `scripts/demo.sh`, `DEMO.md`. |

Test status: 12 tests passing offline. Live smoke verified end-to-end:
`POST /api/requests` → 7 BPMN-node status events stream over SSE; ElevenLabs
webhook → stock ack returned + background orchestration completes.

### Dashboard direction
The original plan was a raw BPMN node-lights viewer for the judges. **That
diagram stays as an internal developer/observability view at
`/static/dashboard.html`**, but the production-facing dashboard is being built
as a clean, modern, role-aware single-page UI with views for:

- **Tenant** — see your reported issues, current status, ETA, vendor name.
- **Property owner** — portfolio-wide ticket roll-up + cost approvals.
- **Property manager** — escalation queue, override decisions, message drafts.
- **Facility manager** — work orders, vendor scheduling, on-site notes.

Same backend (`/api/requests`, `/events/stream/*`); the UI is one component
tree with role-gated panels. Smooth transitions, modular cards, no BPMN
chrome bleeding into end-user views.

## Endpoints (current)

| Method | Path | Owner | What |
|--------|------|-------|------|
| `GET`  | `/health` | Dev 2 | liveness for Cloud Run |
| `POST` | `/api/requests` | Dev 2 | run orchestration synchronously, return `OrchestratorResponse` |
| `GET`  | `/api/requests/{id}/status` | Dev 2 | polled list of `StatusEvent`s |
| `GET`  | `/events/stream/{id}` | Dev 3 (T2) | **SSE** push of `StatusEvent`s — backlog + live |
| `POST` | `/webhooks/elevenlabs/tool` | Dev 3 (T4) | ElevenLabs server-tool adapter; runs orchestration in background |
| `GET`  | `/static/*` | Dev 3 (T3) | dashboard assets (`dashboard.html`, `diagram.bpmn`, JS, CSS) |

## Run locally (offline demo — no keys)
```bash
cp .env.example .env          # USE_LLM stays 0
docker compose up --build
curl -X POST localhost:8080/api/requests -H 'Content-Type: application/json' \
  -d '{"request_id":"d1","channel":"phone","raw_text":"Heating is broken","property_hint":"Musterstrasse 12"}'
curl localhost:8080/api/requests/d1/status   # feed for the dashboard
```

## Run with real agents (ADK + Claude)
```bash
# in .env:  USE_LLM=1  and  ANTHROPIC_API_KEY=sk-ant-...
docker compose up --build
```

## Inspect agents visually (ADK dev UI)
```bash
pip install -r requirements.txt
adk web app/agents      # step through agent traces in the browser
```

## Tests (offline, no key)
```bash
pip install -r requirements.txt
PYTHONPATH=. pytest -q
```

## Deploy to GCP Cloud Run (low cost — scales to zero)
```bash
gcloud auth login && gcloud config set project YOUR_PROJECT
gcloud artifacts repositories create ops --repository-format=docker --location=europe-west1

# Build + push (Cloud Build, no local Docker needed)
gcloud builds submit --tag europe-west1-docker.pkg.dev/YOUR_PROJECT/ops/orchestrator

# Deploy. min-instances=0 => you pay ~nothing when idle.
gcloud run deploy orchestrator \
  --image europe-west1-docker.pkg.dev/YOUR_PROJECT/ops/orchestrator \
  --region europe-west1 --allow-unauthenticated \
  --min-instances 0 --max-instances 2 --memory 512Mi \
  --set-secrets ANTHROPIC_API_KEY=anthropic-key:latest \
  --set-env-vars USE_LLM=1
```
Cost notes: Cloud Run bills only while serving; idle = free. Keep SQLite on the
container for the hackathon (data resets on cold start — fine for a demo). Only
move to Cloud SQL if you need durable, concurrent state, since it bills hourly.

## Merge plan with the voice layer
1. Agree on `schemas.InboundRequest` / `OrchestratorResponse` ✅ (frozen in `app/core/schemas.py`).
2. ElevenLabs server-tool POSTs to `/webhooks/elevenlabs/tool` ✅ (T4).
3. Replace `tools.property_tools.send_message` with the real ElevenLabs/Twilio call (T5 in flight).
4. Dashboard subscribes to `/events/stream/{id}` over SSE ✅ (T2).

## Layout
```
app/
  main.py                 FastAPI surface (lifespan, router mounts, StaticFiles)
  core/
    schemas.py            SHARED CONTRACT — the merge seam (frozen)
    repository.py         SQLite state (WAL pragma; one-line event_bus hook)
    event_bus.py          in-memory pub/sub for StatusEvent (T1)
    settings.py           pydantic-settings env loader (T4)
  agents/
    coordinator.py        orchestration brain + risk gate
    triage.py             dispatcher persona (fallback + LLM)
    comms.py              message drafting (templates + LLM)
    llm_triage.py         ADK LlmAgent + Claude (USE_LLM=1)
    llm_comms.py          ADK LlmAgent + Claude (USE_LLM=1)
  routes/
    events.py             GET /events/stream/{id} (SSE, T2)
    elevenlabs.py         POST /webhooks/elevenlabs/tool (T4)
  tools/
    property_tools.py     property memory, vendor pick, messaging (mocked)
static/
  dashboard.{html,js,css} BPMN dev view (T3 — to be superseded by role UI in T6)
  diagram.bpmn            7-node placeholder, replaced by Biz 2's polished diagram
data/property_memory.json the "property memory" fixture
scripts/
  validate_bpmn.py        CI guard: diagram ids must match coordinator nodes
tests/
  conftest.py             autouse fixture: reset DB per test
  test_flow.py            offline end-to-end (Dev 2)
  test_event_bus.py       pub/sub backlog + live (Dev 3, T1)
  test_sse.py             route wiring + generator (Dev 3, T2)
  test_elevenlabs_webhook.py auth + adapter + bg orchestration (Dev 3, T4)
```
