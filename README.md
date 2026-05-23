# Autonomous Tenant & Vendor Ops — Orchestration Layer

The **foundation layer**: a transport-agnostic agent orchestrator for property
management (German WEG / SEV). Your colleague's voice/channel layer (ElevenLabs)
calls this over HTTP; this layer triages, retrieves property context, picks a
vendor, applies a human-escalation risk gate, drafts messages, and streams
status events for the live BPMN dashboard.

## Why it's built this way
- **Transport-agnostic**: orchestrator never knows if a request was a call, SMS,
  or chat. Merge seam with the voice layer = `app/core/schemas.py`.
- **Dual mode**: runs fully **offline** (deterministic, no API key) for a
  reliable demo, and upgrades to **ADK + Claude** with `USE_LLM=1`.
- **Modular**: each agent + tool is a small unit. Tools are mocked now and
  swapped for the colleague's real vendor/messaging APIs later.
- **Same image local & cloud**: one Dockerfile for Compose and Cloud Run.

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
1. Agree on `schemas.InboundRequest` / `OrchestratorResponse` (done — share this file).
2. Colleague's ElevenLabs agent webhook POSTs `InboundRequest` to `/api/requests`.
3. Replace `tools.property_tools.send_message` with their ElevenLabs/Twilio call.
4. Dashboard polls (or websockets) `/api/requests/{id}/status`.

## Layout
```
app/
  main.py            FastAPI surface (the only HTTP layer)
  core/schemas.py    SHARED CONTRACT — the merge seam
  core/repository.py SQLite state (swap URL for Cloud SQL)
  agents/coordinator.py   orchestration brain + risk gate
  agents/triage.py        dispatcher persona (fallback + LLM)
  agents/comms.py         message drafting (templates + LLM)
  agents/llm_triage.py    ADK LlmAgent + Claude (USE_LLM=1)
  agents/llm_comms.py     ADK LlmAgent + Claude (USE_LLM=1)
  tools/property_tools.py property memory, vendor pick, messaging (mocked)
data/property_memory.json  the "property memory" fixture
tests/test_flow.py         offline end-to-end tests
```
