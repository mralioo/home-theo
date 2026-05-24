# Hausmind — API Reference & Integration Guide

## Services

| Service | Local URL | Purpose |
|---|---|---|
| **Orchestrator** | `http://localhost:8080` | Main FastAPI app — triage, risk gate, comms, events |
| **ADK UI** | `http://localhost:8001` | Google ADK visual agent trace debugger |
| **Context Service** | `http://localhost:8002` | RAG/semantic search over buildings, vendors, incidents |
| **OpenSearch** | `http://localhost:9200` | Vector DB powering the context service |

---

## Start everything

```bash
# 1. Copy and fill in secrets
cp .env.example .env
# set ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_AGENT_ID_OUTBOUND

# 2. Build and start all four containers
make up

# 3. Tail logs
make logs                    # all services
make logs-orchestrator       # orchestrator only
make logs-context            # context service + opensearch
```

---

## Orchestrator — `http://localhost:8080`

### `GET /health`
Liveness probe. Returns `{"status": "ok"}`.

```bash
make health
# or
curl http://localhost:8080/health
```

---

### `GET /dashboard`
Hausmind Pipeline Visualizer — role-aware SPA showing ticket state and vendor assignment.

```bash
open http://localhost:8080/dashboard
```

---

### `GET /static/dashboard.html`
BPMN developer/observability view. Shows live node-by-node pipeline state for a given request.

```bash
open http://localhost:8080/static/dashboard.html
```

---

### `POST /api/requests`
Submit an issue. Runs triage → property context → vendor selection → risk gate → comms drafting synchronously. Returns the full `OrchestratorResponse`.

**Request body**
```json
{
  "request_id": "dc-heat-01",
  "channel": "chat",
  "raw_text": "The heating on the 3rd floor is broken",
  "property_hint": "The Delta Campus Berlin",
  "reporter_name": "Max Mustermann",
  "reporter_phone": "+4930000001",
  "detected_sentiment": "neutral"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `request_id` | string | ✓ | Idempotency key — reusing the same ID overwrites the ticket |
| `channel` | enum | ✓ | `phone` `sms` `email` `chat` `walk_in` |
| `raw_text` | string | ✓ | Transcript or message body |
| `property_hint` | string | | Address, name, or alias — matched case-insensitively against `data/property_memory.json` |
| `reporter_name` | string | | |
| `reporter_phone` | string | | E.164 format |
| `detected_sentiment` | enum | | `angry` `frustrated` `neutral` `calm` — overrides LLM sentiment when set |

**Response** — `OrchestratorResponse`
```json
{
  "request_id": "dc-heat-01",
  "decision": "auto_resolve",
  "diagnosis": {
    "category": "heating",
    "urgency": "high",
    "sentiment": "neutral",
    "summary": "Heating system not functioning in 3rd floor coworking space.",
    "confidence": 0.95
  },
  "vendor_plan": {
    "vendor_id": "klimatec-berlin",
    "vendor_name": "Klimatec Berlin",
    "proposed_window": "tomorrow 09:00-12:00",
    "estimated_cost_eur": 280.0
  },
  "tenant_message": "...",
  "vendor_message": "...",
  "escalation_reason": null,
  "trace": ["intake done", "triage done: heating/high/neutral", "..."]
}
```

| `decision` | When |
|---|---|
| `auto_resolve` | Cost ≤ threshold, category not legal/financial, sentiment not angry |
| `escalate_human` | Any of: legal, financial, angry sentiment, cost > approval threshold |
| `need_more_info` | Insufficient signal to triage |

**Make targets**
```bash
make req-heating             # Musterstrasse 12 — heating
make req-plumbing            # Musterstrasse 12 — plumbing
make req-electrical          # Musterstrasse 12 — electrical
make req-elevator            # Musterstrasse 12 — elevator
make req-access              # Musterstrasse 12 — locked out
make req-cleaning            # Musterstrasse 12 — cleaning
make req-financial           # → escalate_human (financial dispute)
make req-legal               # → escalate_human (legal question)
make req-emergency           # → urgency=emergency (flooding)
make req-angry               # → escalate_human (angry, third repeat)

# Delta Campus Berlin showcase
make req-delta-heating       # 3rd-floor coworking, no heat
make req-delta-plumbing      # 4th-floor kitchen sink leak
make req-delta-elevator      # atrium lift — person trapped (emergency)
make req-delta-access        # transponder card dead
make req-delta-angry         # gym overheating, 3rd complaint → escalate
make req-delta-legal         # management contract question → escalate

make demo                    # fire all standard + Delta requests sequentially
make demo-delta              # Delta Campus scenarios only
```

---

### `GET /api/requests/{id}/status`
Polled status event list for the dashboard. Returns an ordered array of `StatusEvent` objects covering every BPMN node that was executed.

```bash
make status ID=dc-heat-01
# or
curl http://localhost:8080/api/requests/dc-heat-01/status
```

**Response**
```json
{
  "request_id": "dc-heat-01",
  "events": [
    {"node": "intake",   "status": "done",    "detail": "chat: Heating broken...", "at": "..."},
    {"node": "triage",   "status": "started", "detail": "",                         "at": "..."},
    {"node": "triage",   "status": "done",    "detail": "heating/high/neutral",     "at": "..."},
    {"node": "context",  "status": "done",    "detail": "PROP-DCB loaded",          "at": "..."},
    {"node": "vendor",   "status": "done",    "detail": "klimatec-berlin @ EUR 280","at": "..."},
    {"node": "risk_gate","status": "done",    "detail": "auto_resolve",             "at": "..."},
    {"node": "comms",    "status": "done",    "detail": "messages drafted",         "at": "..."},
    {"node": "closed",   "status": "done",    "detail": "",                         "at": "..."}
  ]
}
```

---

### `GET /events/stream/{id}`
**Server-Sent Events** — replays the backlog then pushes live events as they arrive. Use this to drive the dashboard in real time.

```bash
make stream ID=dc-heat-01
# or
curl -N http://localhost:8080/events/stream/dc-heat-01
```

Each SSE frame:
```
data: {"node":"triage","status":"done","detail":"heating/high/neutral","at":"..."}
```

The stream sends `: ping` keepalive comments every 15 s so the connection survives Cloud Run / reverse-proxy idle timeouts.

---

### `POST /webhooks/elevenlabs/tool`
ElevenLabs server-tool adapter. ElevenLabs calls this mid-conversation when the voice agent decides to dispatch maintenance. Responds in < 1.5 s with a stock acknowledgement; orchestration runs in a background task so the full pipeline result reaches the dashboard via SSE.

**Auth** — `X-Webhook-Secret` header must match `WEBHOOK_SECRET` env var (default dev: `dev-only-not-secret`).

**Request body**
```json
{
  "tool_name": "dispatch_maintenance",
  "conversation_id": "el-conv-abc123",
  "caller_id": "+4930123456",
  "parameters": {
    "issue_summary": "The heating in the 3rd floor coworking area is broken",
    "property_hint": "The Delta Campus Berlin",
    "reporter_name": "Demo Caller",
    "category_hint": "heating",
    "urgency_hint": "high"
  }
}
```

**Response**
```json
{
  "ticket_id": "el-conv-abc123",
  "agent_message": "Got it — I'm dispatching maintenance now. We'll text you once a vendor is scheduled."
}
```

```bash
make elevenlabs-tool
# or with a custom secret:
WEBHOOK_SECRET=mysecret make elevenlabs-tool
```

---

### `POST /webhooks/elevenlabs/post-call`
Post-call hook. ElevenLabs fires this after a conversation ends. Attaches the transcript summary and call metadata to the ticket so the dashboard shows the final outcome.

**Auth** — same `X-Webhook-Secret` header.

**Request body**
```json
{
  "conversation_id": "el-conv-abc123",
  "transcript_summary": "Caller reported broken heating on 3rd floor. Dispatch confirmed.",
  "transcript": "...",
  "duration_seconds": 47.3,
  "success": true
}
```

**Response**
```json
{"ticket_id": "el-conv-abc123", "matched_existing": true}
```

```bash
make elevenlabs-post-call
```

---

### `POST /actions/call-vendor`
Trigger an outbound call to a vendor via ElevenLabs REST. Requires the ticket to exist (404 otherwise). Needs `ELEVENLABS_API_KEY` and `ELEVENLABS_AGENT_ID_OUTBOUND` set in `.env`.

**Auth** — `X-Admin-Secret` header must match `ADMIN_SECRET` env var.

**Request body**
```json
{
  "ticket_id": "dc-heat-01",
  "to_number": "+4930999888",
  "agent_id": null
}
```

**Response**
```json
{
  "ticket_id": "dc-heat-01",
  "elevenlabs_response": {"conversation_id": "...", "status": "queued"}
}
```

```bash
make call-vendor ID=dc-heat-01 PHONE=+4930999888
# or with a custom secret:
ADMIN_SECRET=mysecret make call-vendor ID=dc-heat-01 PHONE=+4930999888
```

---

## Context Service — `http://localhost:8002`

Semantic + keyword search over buildings, vendors, and historical incidents. The orchestrator uses it automatically when `CONTEXT_SERVICE_URL` is set.

### `GET /health`
```bash
make ctx-health
```

### `GET /buildings/search?q=<text>`
Free-text building lookup. Returns ranked matches with property metadata.
```bash
make ctx-search-building Q="Delta Campus Berlin"
make ctx-search-building Q="Musterstrasse 12"
```

### `GET /vendors/search?category=<cat>[&building_id=<id>]`
Find vendors for a service category, optionally scoped to a building.
```bash
make ctx-search-vendor CAT=heating
make ctx-search-vendor CAT=elevator BID=PROP-DCB
```

### `GET /incidents/search?building_id=<id>[&category=<cat>]`
Retrieve historical incidents for a building (keyword match).
```bash
make ctx-incidents BID=PROP-DCB
make ctx-incidents BID=PROP-DCB CAT=heating
```

### `GET /incidents/semantic?q=<text>&building_id=<id>`
Semantic vector search over incident history.
```bash
make ctx-semantic Q="heating pressure loss" BID=PROP-DCB
make ctx-semantic Q="lift door sensor" BID=PROP-DCB
```

### `POST /admin/reindex`
Re-seed all OpenSearch indices from `data/seed_data.json`. Run this after updating seed data.
```bash
make ctx-reindex
```

---

## OpenSearch — `http://localhost:9200`

```bash
make os-health          # cluster health
make os-indices         # list indices (buildings, vendors, incidents)
```

---

## Interactive docs

| URL | What |
|---|---|
| `http://localhost:8080/docs` | Swagger UI — try all endpoints in browser |
| `http://localhost:8080/redoc` | ReDoc — clean API reference |
| `http://localhost:8002/docs` | Context service Swagger UI |

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `USE_LLM` | `0` | `1` enables ADK + Claude triage/comms; `0` uses deterministic heuristics |
| `ANTHROPIC_API_KEY` | — | Required when `USE_LLM=1` |
| `LITELLM_MODEL` | `anthropic/claude-sonnet-4-5-20250929` | Model for both LLM agents |
| `DB_PATH` | `/data/ops.db` | SQLite path inside the orchestrator container |
| `WEBHOOK_SECRET` | `dev-only-not-secret` | Verified on `X-Webhook-Secret` header for ElevenLabs webhooks |
| `ADMIN_SECRET` | `dev-only-not-secret` | Verified on `X-Admin-Secret` header for admin actions |
| `ELEVENLABS_API_KEY` | — | Required for `POST /actions/call-vendor` |
| `ELEVENLABS_AGENT_ID_OUTBOUND` | — | Default agent used for outbound vendor calls |
| `FAKE_ORCHESTRATOR` | `0` | `1` emits canned status events without calling Claude — useful for frontend dev |
| `CONTEXT_SERVICE_URL` | — | Set in compose; orchestrator queries context service if set |

---

## Risk gate rules

The risk gate in `app/agents/coordinator.py` always escalates when **any** of these are true:

- `category` is `legal` or `financial`
- `detected_sentiment` or inferred sentiment is `angry`
- `estimated_cost_eur` exceeds the property's `approval_threshold_eur`
  - Musterstrasse 12: **€500**
  - The Delta Campus Berlin: **€800**

Everything else resolves automatically.

---

## Properties in fixture

Edit `data/property_memory.json` to add or update properties. Keys are matched case-insensitively against `property_hint`.

| Key | Property | Threshold |
|---|---|---|
| `musterstrasse 12` | Musterstrasse 12, Berlin | €500 |
| `the delta campus berlin` | The Delta Campus Berlin | €800 |
| `delta campus` | The Delta Campus Berlin (alias) | €800 |
| `_default` | Fallback for unknown properties | €500 |
