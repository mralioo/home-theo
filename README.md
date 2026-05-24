# Home Theo — Autonomous Property Operations Platform

**Home Theo** is an AI-native orchestration layer for German residential and commercial property management (WEG / SEV). A voice or channel layer (ElevenLabs, SMS, chat) POSTs a tenant complaint; Home Theo triages it, retrieves property memory from a vector database, selects and dispatches a vendor, applies a risk gate, drafts bilingual messages, and streams live status events to a role-aware dashboard — all within seconds.

---

## High-Level Architecture

```
Voice / Channel Layer (ElevenLabs ConvAI, SMS, email, chat)
         │
         │  POST /api/requests  or  POST /webhooks/elevenlabs/tool
         ▼
┌────────────────────────────────────────────────────────────────────┐
│  Home Theo Orchestrator  (FastAPI · port 8080)                     │
│                                                                    │
│  coordinator.handle_request()                                      │
│   │                                                                │
│   ├─ 1. Triage ──────────────────────────────────────────────────  │
│   │       keyword heuristics (USE_LLM=0, always-on demo)           │
│   │       LlmTriageAgent via Google ADK + Claude (USE_LLM=1)       │
│   │       → Diagnosis {category, urgency, sentiment, confidence}   │
│   │                                                                │
│   ├─ 2a. Retriever ──────────────────────────────────────────────  │
│   │       OpenSearch knn_vector (384-dim) + BM25 hybrid search     │
│   │       BAAI/bge-small-en-v1.5 embeddings (fastembed / ONNX)     │
│   │       → building doc + top-k category-filtered incidents       │
│   │                                                                │
│   ├─ 2b. Synthesizer ────────────────────────────────────────────  │
│   │       Derives probable causes via semantic RAG over incidents   │
│   │       Assembles PropertyContext {manager, vendors, threshold,  │
│   │         access_notes, recent_cases, probable_causes}           │
│   │                                                                │
│   ├─ 3. Vendor Selector ────────────────────────────────────────── │
│   │       preferred vendor map from PropertyContext                │
│   │       rate × estimated hours → VendorPlan + cost estimate      │
│   │                                                                │
│   ├─ 4. Risk Gate (deterministic policy, no LLM) ───────────────── │
│   │       escalate if: legal | financial | angry | cost > threshold │
│   │       → Decision {auto_resolve | escalate_human}               │
│   │                                                                │
│   ├─ 5. Comms Agent ────────────────────────────────────────────── │
│   │       template drafts (offline) or Claude polish (USE_LLM=1)   │
│   │       → tenant acknowledgement + vendor work order             │
│   │                                                                │
│   └─ 6. Persist ───────────────────────────────────────────────── │
│           SQLite ticket + StatusEvents → event_bus pub/sub          │
│                                                                    │
└─────────────────────────────┬──────────────────────────────────────┘
                              │  SSE  GET /events/stream/{id}
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Home Theo Dashboard  (Vanilla JS SPA · served at /dashboard)      │
│                                                                    │
│  Pipeline Inspector: 8-step BPMN trace, live SSE updates           │
│  Retriever panel:    OpenSearch source, embedding model, top-k hits │
│  Synthesizer panel:  RAG-derived probable causes ranked list        │
│  Comms panel:        tenant + vendor messages with ElevenLabs TTS   │
└────────────────────────────────────────────────────────────────────┘

┌──────────────────────────┐    ┌──────────────────────────────────┐
│  Context Service :8002   │    │  OpenSearch :9200                │
│  FastAPI + fastembed     │◄──►│  k-NN plugin, index.knn=true     │
│  /buildings/search       │    │  3 indices: buildings / vendors   │
│  /vendors/search         │    │  / incidents (384-dim vectors)    │
│  /incidents/semantic     │    └──────────────────────────────────┘
│  /probable-causes/search │
└──────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **API / orchestration** | Python 3.12, FastAPI, Uvicorn, Pydantic v2 |
| **LLM agents** | Google ADK (`LlmAgent`), Claude Sonnet via LiteLLM |
| **Voice / TTS / STT** | ElevenLabs ConvAI (inbound), TTS v2 (`eleven_multilingual_v2`), Whisper STT |
| **Vector search** | OpenSearch 2.11 (k-NN plugin), knn_vector 384-dim, BM25 hybrid |
| **Embeddings** | `BAAI/bge-small-en-v1.5` via fastembed / ONNX (CPU, no GPU needed) |
| **RAG** | Semantic incident search → probable cause derivation, `/probable-causes/search` |
| **Persistence** | SQLite (WAL mode) — drop-in swap for Cloud SQL |
| **Realtime** | Server-Sent Events (`sse-starlette`), in-memory event bus with 200-event backlog |
| **Dashboard** | Vanilla JS SPA, live BPMN pipeline trace, audio player (ElevenLabs TTS) |
| **Containerisation** | Docker Compose (local), single Dockerfile for Cloud Run |
| **CI** | GitHub Actions, ruff, pre-commit hooks |
| **Deployment** | GCP Cloud Run (scales to zero), Artifact Registry |

---

## Dual-Mode Operation

| Mode | How | When |
|---|---|---|
| **Offline / demo** | `USE_LLM=0` (default) — keyword heuristics + message templates | No API key needed; demo never dies |
| **LLM / production** | `USE_LLM=1` — ADK LlmAgent + Claude via LiteLLM | Set `ANTHROPIC_API_KEY` |

LLM agents are lazy-imported and isolated. Any exception falls back to deterministic mode silently.

---

## Key Design Decisions

- **Transport-agnostic**: orchestrator never knows if a request came from a phone call, SMS, or chat. The merge seam with the voice layer is `app/core/schemas.py` — never rename fields without coordinating.
- **Risk gate is 100% deterministic**: escalates to human for `legal`, `financial`, `angry` sentiment, or cost exceeding `approval_threshold_eur`. No LLM involved in this decision.
- **RAG is best-effort**: context service failure → fixture fallback. Demo never breaks on infrastructure issues.
- **Property context drives everything**: vendor selection, message drafting, and risk gate threshold all read from `PropertyContext` — the assembled output of the retriever + synthesizer steps.

---

## Endpoints

| Method | Path | What |
|--------|------|------|
| `POST` | `/api/requests` | Run full orchestration pipeline, return `OrchestratorResponse` |
| `GET`  | `/api/requests/{id}/status` | Polled list of `StatusEvent`s |
| `GET`  | `/events/stream/{id}` | **SSE** live push of `StatusEvent`s (backlog + live) |
| `POST` | `/api/tts` | ElevenLabs TTS synthesis → MP3 stream |
| `POST` | `/webhooks/elevenlabs/tool` | ElevenLabs server-tool adapter (async orchestration) |
| `POST` | `/webhooks/elevenlabs/post-call` | Attach post-call transcript summary to ticket |
| `POST` | `/actions/call-vendor` | Outbound vendor call via ElevenLabs (admin-secret gated) |
| `POST` | `/api/transcribe/file` | Transcribe uploaded audio via ElevenLabs STT |
| `GET`  | `/dashboard` | Pipeline Inspector dashboard |
| `GET`  | `/app` | Role-aware operations SPA |
| `GET`  | `/health` | Liveness probe |

Context Service (port 8002):

| Method | Path | What |
|--------|------|------|
| `GET` | `/buildings/search?q=` | Semantic building lookup (knn_vector + BM25) |
| `GET` | `/vendors/search?category=` | Vendor search with category filter + rating sort |
| `GET` | `/incidents/search?building_id=` | Incident history, optionally filtered by category |
| `GET` | `/incidents/semantic?q=&building_id=` | Free-text semantic search over incident history |
| `GET` | `/probable-causes/search?q=&building_id=` | RAG: semantic incidents → ranked probable causes |
| `POST` | `/admin/reindex` | Re-seed all OpenSearch indices from `data/seed_data.json` |

---

## Run Locally (offline — no keys needed)

```bash
cp .env.example .env          # USE_LLM stays 0
docker compose up --build

# Submit a request
curl -X POST localhost:8080/api/requests \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"d1","channel":"phone","raw_text":"Heating broken","property_hint":"The Delta Campus Berlin"}'

# Poll status events
curl localhost:8080/api/requests/d1/status

# Live SSE stream
curl -N localhost:8080/events/stream/d1

# Open dashboard
open http://localhost:8080/dashboard
```

## Run with LLM Agents (ADK + Claude)

```bash
# .env:
USE_LLM=1
ANTHROPIC_API_KEY=sk-ant-...
docker compose up --build
```

## Run with ElevenLabs TTS

```bash
# .env:
ELEVENLABS_API_KEY=sk_...
# Then click the ▶ play button on any message in the Comms step of the dashboard
```

## Regenerate Seed Data (OpenSearch)

```bash
# Edit data/seed_data.json or regenerate via the prompt in DATA_GENERATION_PROMPT.md
curl -X POST http://localhost:8002/admin/reindex
```

## Tests (offline, no keys)

```bash
PYTHONPATH=. pytest -q
```

---

## Project Layout

```
app/
  main.py                  FastAPI surface — routes, TTS endpoint, lifespan
  core/
    schemas.py             SHARED CONTRACT with voice layer — never rename fields
    repository.py          SQLite (WAL); one-line event_bus hook
    event_bus.py           in-memory pub/sub for StatusEvent (SSE backlog)
    settings.py            pydantic-settings env loader
  agents/
    coordinator.py         orchestration brain + risk gate
    triage.py              dispatcher persona (fallback + LLM dispatch)
    comms.py               message drafting (templates + LLM dispatch)
    llm_triage.py          ADK LlmAgent + Claude via LiteLLM (USE_LLM=1)
    llm_comms.py           ADK LlmAgent + Claude via LiteLLM (USE_LLM=1)
  tools/
    property_tools.py      PropertyContext lookup (context service → fixture fallback)
                           Vendor selection, probable cause derivation
  routes/
    events.py              GET /events/stream/{id} — SSE
    elevenlabs.py          POST /webhooks/elevenlabs/* — inbound + post-call
    actions.py             POST /actions/call-vendor — outbound
    transcribe.py          POST /api/transcribe/* — STT
    queries.py             GET /api/requests — ticket list
  static/
    dashboard.html         Pipeline Inspector SPA (BPMN trace, RAG panels, TTS player)
    app.html               Role-aware operations SPA

context_service/
  main.py                  FastAPI — semantic search endpoints
  searcher.py              knn_vector + BM25 hybrid search; probable cause derivation
  indexer.py               OpenSearch index creation + bulk seeding
  embedder.py              BAAI/bge-small-en-v1.5 via fastembed

data/
  seed_data.json           9 buildings, 20 vendors, 55 incidents (OpenSearch source)
  property_memory.json     Fixture fallback — property_memory + probable_causes_by_category

tests/
  test_flow.py             Offline end-to-end pipeline
  test_event_bus.py        pub/sub backlog + live streaming
```

---

## Deploy to GCP Cloud Run

```bash
gcloud auth login && gcloud config set project YOUR_PROJECT
gcloud artifacts repositories create ops \
  --repository-format=docker --location=europe-west1

gcloud builds submit --tag europe-west1-docker.pkg.dev/YOUR_PROJECT/ops/orchestrator

gcloud run deploy orchestrator \
  --image europe-west1-docker.pkg.dev/YOUR_PROJECT/ops/orchestrator \
  --region europe-west1 --allow-unauthenticated \
  --min-instances 0 --max-instances 2 --memory 512Mi \
  --set-secrets ANTHROPIC_API_KEY=anthropic-key:latest \
  --set-env-vars USE_LLM=1,CONTEXT_SERVICE_URL=https://context-service-url
```

Cloud Run bills only while serving — idle = free. SQLite resets on cold start (fine for demo). Move to Cloud SQL only if durable concurrent state is needed.
