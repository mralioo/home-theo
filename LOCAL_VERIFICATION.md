# Local Verification & Architecture — Hausmind

> Verify the full agentic stack locally before deploying to GCP.
> Reference: `HAUSMIND_CONTEXT.md`, `app/core/schemas.py`, `app/agents/`

---

## Prerequisites

`.env` must have:

```env
USE_LLM=1
ANTHROPIC_API_KEY=sk-ant-...   # from console.anthropic.com
LITELLM_MODEL=anthropic/claude-sonnet-4-5-20250929
DB_PATH=/data/ops.db
```

> **Security:** rotate the key after the hackathon — it lives on disk in `.env`.

---

## Start the stack

```bash
docker compose up --build -d
```

| Container | URL | Role |
|---|---|---|
| `orchestrator` | http://localhost:8080 | FastAPI + ADK orchestration |
| `adk-ui` | http://localhost:8001 | ADK visual trace UI |

---

## Trigger the agentic workflow

```bash
# 1. Health check
make health

# 2. Auto-resolve path — triage + Claude + vendor dispatch
make req-heating

# 3. Escalation paths — risk gate must fire
make req-financial      # → decision=escalate_human  (financial rule)
make req-angry          # → decision=escalate_human  (sentiment rule)
make req-legal          # → decision=escalate_human  (legal rule)
make req-emergency      # → urgency=emergency

# 4. Read the BPMN status event trace
make status ID=demo-heat-01

# 5. Live container logs (watch ADK + Claude calls)
make logs-orchestrator
```

---

## Pre-GCP checklist

| Command | Expected result |
|---|---|
| `make req-heating` | `decision=auto_resolve`, `vendor_plan` present, `tenant_message` + `vendor_message` drafted |
| `make req-financial` | `decision=escalate_human`, `vendor_plan=null` |
| `make req-angry` | `decision=escalate_human` |
| `make req-emergency` | `diagnosis.urgency=emergency` |
| `make test` | All offline tests green (no key needed) |
| http://localhost:8001 | ADK UI loads `triage` + `comms` agents |

All six must pass before deploying.

---

## ADK visual trace (http://localhost:8001)

1. Open http://localhost:8001
2. Select **triage** agent from the left panel
3. Paste: `"The heating is broken and it is freezing outside"`
4. Click **Run**
5. Trace panel shows Claude reasoning → JSON output `{category, urgency, sentiment, confidence}`

Repeat with **comms** agent — paste the JSON Diagnosis and a vendor plan, see the polished tenant message.

---

## Detailed architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  VOICE / CHANNEL LAYER  (colleague — ElevenLabs)                    │
│                                                                      │
│  ElevenLabs Agent ──STT──► normalize ──POST InboundRequest──►       │
│  (inbound call)             channel, raw_text, sentiment hint        │
│                                                                      │
│  ElevenLabs Agent ◄── TTS ◄── OrchestratorResponse.tenant_message  │
│  (outbound vendor)  └─────── vendor_message (negotiates cost/window)│
└──────────────────────────────────┬──────────────────────────────────┘
                                   │  HTTP  POST /api/requests
                    ┌──────────────▼──────────────────────────────┐
                    │  FastAPI  (app/main.py)  :8080               │
                    │                                              │
                    │  POST /api/requests   → orchestrate          │
                    │  GET  /api/requests/{id}/status → dashboard  │
                    │  GET  /health         → Cloud Run liveness   │
                    └──────────────┬──────────────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────────────┐
                    │  coordinator.handle_request()                │
                    │  app/agents/coordinator.py                   │
                    │                                              │
                    │  Deterministic skeleton — sequences agents,  │
                    │  applies risk gate, emits status events       │
                    └──┬──────────┬──────────┬────────────────────┘
                       │          │          │
          ┌────────────▼──┐  ┌───▼───────┐  ┌▼──────────────┐
          │  TRIAGE        │  │  CONTEXT  │  │  VENDOR        │
          │                │  │  lookup   │  │  select        │
          │  USE_LLM=0:    │  │           │  │                │
          │  keyword rules │  │  reads    │  │  picks from    │
          │                │  │  data/    │  │  preferred_    │
          │  USE_LLM=1:    │  │  property_│  │  vendors in    │
          │  LlmAgent +    │  │  memory   │  │  PropertyCtx   │
          │  Claude        │  │  .json    │  │                │
          │  via LiteLLM   │  │           │  │  → VendorPlan  │
          │                │  │  prod:    │  │  (cost+window  │
          │  → Diagnosis   │  │  Firestore│  │   stubbed now) │
          │  category      │  │  / RAG    │  │                │
          │  urgency       │  │           │  └──────┬─────────┘
          │  sentiment     │  │  → Prop.  │         │
          │  confidence    │  │  Context  │         │
          └────────┬───────┘  └───┬───────┘         │
                   │              │                  │
                   └──────────────┴─────────┬────────┘
                                            │
                    ┌───────────────────────▼─────────────────────┐
                    │  RISK GATE  (coordinator._risk_gate)         │
                    │                                              │
                    │  escalate_human if ANY of:                   │
                    │    category == legal                         │
                    │    category == financial                     │
                    │    sentiment == angry                        │
                    │    estimated_cost > approval_threshold_eur   │
                    │                                              │
                    │  → Decision: auto_resolve | escalate_human  │
                    └──────────────┬──────────────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────────────┐
                    │  COMMS agent  (app/agents/comms.py)          │
                    │                                              │
                    │  draft_tenant_message()   template           │
                    │  draft_vendor_message()   template           │
                    │  polish()                                    │
                    │    USE_LLM=0 → templates as-is              │
                    │    USE_LLM=1 → LlmAgent rewrites via Claude │
                    │               warm, on-brand voice           │
                    └──────────────┬──────────────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────────────┐
                    │  REPOSITORY  (app/core/repository.py)        │
                    │                                              │
                    │  upsert_ticket()   → tickets table           │
                    │  record_event()    → status_events table     │
                    │                                              │
                    │  SQLite /data/ops.db                         │
                    │  → swap connection URL for Cloud SQL in prod │
                    └──────────────┬──────────────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────────────┐
                    │  STATUS EVENTS  (dashboard feed)             │
                    │                                              │
                    │  GET /api/requests/{id}/status               │
                    │  ordered event stream:                       │
                    │    intake → triage → context → vendor →     │
                    │    risk_gate → comms → closed                │
                    │                                              │
                    │  bpmn-js lights BPMN nodes by these ids      │
                    └─────────────────────────────────────────────┘
```

---

## LLM call path (USE_LLM=1)

```
coordinator
  │
  ├─► triage()                         app/agents/triage.py
  │     └─► triage_llm()               app/agents/llm_triage.py
  │           └─► ADK LlmAgent         "triage_agent"
  │                 └─► LiteLlm        anthropic/claude-sonnet-4-5-20250929
  │                       └─► Anthropic API  ← ANTHROPIC_API_KEY
  │                             └─► {category, urgency, sentiment, summary, confidence}
  │
  └─► comms.polish()                   app/agents/comms.py
        └─► polish_llm()               app/agents/llm_comms.py
              └─► ADK LlmAgent         "comms_agent"
                    └─► LiteLlm  ──►  Anthropic API
                          └─► rewrites templates → warm on-brand tenant/vendor messages
```

Both LLM calls have a **try/except fallback** — any model error silently drops back to the deterministic path so the demo never dies.

---

## Dual-mode summary

| | USE_LLM=0 (demo safe) | USE_LLM=1 (live agents) |
|---|---|---|
| Triage | keyword heuristics | ADK LlmAgent + Claude |
| Comms | fixed templates | Claude rewrites to on-brand voice |
| Keys needed | none | `ANTHROPIC_API_KEY` |
| Demo risk | zero | model latency / API errors |
| Confidence | 0.6 (fixed) | 0.0–1.0 from model |

---

## GCP Cloud Run deploy (after local verification passes)

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT

# Build + push (no local Docker needed)
gcloud builds submit \
  --tag europe-west1-docker.pkg.dev/YOUR_PROJECT/ops/orchestrator

# Deploy — scales to zero, idle ≈ free
gcloud run deploy orchestrator \
  --image europe-west1-docker.pkg.dev/YOUR_PROJECT/ops/orchestrator \
  --region europe-west1 \
  --allow-unauthenticated \
  --min-instances 0 --max-instances 2 --memory 512Mi \
  --set-secrets ANTHROPIC_API_KEY=anthropic-key:latest \
  --set-env-vars USE_LLM=1
```

Keep SQLite on the container for the hackathon (resets on cold start — fine for a demo).
Only move to Cloud SQL if you need state to survive restarts.

---

## Open next steps (from HAUSMIND_CONTEXT §10)

- [ ] BPMN diagram node ids aligned exactly to status-event node ids (`intake`, `triage`, `context`, `vendor`, `risk_gate`, `comms`, `closed`)
- [ ] Replace `tools.property_tools.send_message` with real ElevenLabs / Twilio call
- [ ] Replace stubbed vendor cost/window with real outbound ElevenLabs vendor call
- [ ] Property-memory RAG (replace JSON fixture with Firestore / ElevenLabs knowledge base)
- [ ] Resolution tracking / case-memory learning loop
