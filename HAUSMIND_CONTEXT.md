# Hausmind — Project Context & Handoff

> Autonomous Tenant & Vendor Operations (ElevenLabs hackathon track).
> An always-on AI operations layer that triages tenant requests, coordinates
> vendors, and closes the loop — keeping humans only where it matters.

This file is the single source of truth for the team. Drop it into any chat or
tool as context.

---

## 1. The challenge

**Track:** ElevenLabs — Autonomous Tenant & Vendor Operations.
Tenant communication and service coordination are repetitive, manual, and
slow. Maintenance requests, vendor coordination, and status updates require
endless back-and-forth.

**Goal:** an AI-powered operations layer that automates communication,
coordination, and service workflows across tenants, landlords, and vendors —
"AI-powered operations teams that are always on."

**Guiding prompts:**
- What if 80% of tenant requests never needed a human?
- How do we coordinate vendors without back-and-forth chaos?
- What would a fully automated maintenance workflow look like?

**Bonus points:** real-time voice AI call handling, multi-channel orchestration
(email/SMS/phone), sentiment detection + escalation, end-to-end resolution
tracking.

---

## 2. Domain grounding (from the interview / personas doc)

The domain is **German property management** — WEG-Verwaltung (homeowner
association management) and SEV/Sondereigentumsverwaltung (managing an
individual rented apartment for its owner). Focus: maintenance/service ops and
internal property-manager productivity.

**Key personas → agent mapping:**
- **Overloaded property manager** (50–100 emails/day, knowledge in their head)
  → the coordinator's job is to give them "perfect memory + follow-through."
- **Servicer / dispatcher** (intake, classify urgency, route) → **triage agent**.
- **Individual owner** (wants asset protection, financial clarity) → kept in the
  loop via the **risk gate** for money decisions.
- **Tenant** (report issue, get updates, human escalation when serious) →
  served by the **comms agent** + escalation logic.
- **External contractor** (needs clear brief, access info, payment) → **vendor
  agent**.

**The two deepest insights from the doc (drive the whole design):**
1. Property management isn't broken because people don't know the process — it's
   broken because **context is fragmented and stuck in human memory**. So the
   product wedge is "property memory" + case memory (doc Priority 2).
2. With enough context, an agent doesn't need a rigidly deterministic process
   map; it can infer next steps from history. → Use a **process skeleton
   (BPMN) for predictability + LLM/context for judgment** (hybrid).

**Humans stay in the loop where it matters:** financial, emotional, legal,
high-value asset, complex exceptions. Everything else auto-resolves.

**Canonical demo scenario:** tenant reports "heating is broken" → triage →
property context (key with Frau Meyer, 2nd floor, weekends only) → preferred
heating contractor → cost below threshold → auto-dispatch + tenant SMS. If cost
is high / caller is angry / topic is financial-or-legal → escalate to human.

---

## 3. Architecture

Two halves with a clean seam between them:

- **Voice / channel layer (colleague's work):** ElevenLabs Agents handle
  inbound + outbound voice, SMS, chat. They normalize a request and POST it to
  the orchestrator; they render a live BPMN status dashboard.
- **Orchestration layer (this scaffold — the foundation):** transport-agnostic
  agent orchestrator. Triages, retrieves context, picks a vendor, applies the
  risk gate, drafts messages, streams status events.

**The merge seam** is the shared schema (`app/core/schemas.py`):
`InboundRequest` in, `OrchestratorResponse` out, plus a `/status` event feed.

**Agents (derived from personas, not invented top-down):**
1. **Coordinator (root / brain)** — plans, sequences specialists, applies the
   risk gate. The foundation layer.
2. **Triage agent** — classify category + urgency + sentiment (dispatcher).
3. **Context agent** — retrieve "property memory": access, keys, preferred
   vendors, history (RAG in prod; fixture for the demo).
4. **Vendor agent** — select contractor, propose window + cost (contractor coord).
5. **Comms agent** — draft tenant/vendor messages (warm, factual).
6. **Risk gate** — a policy in the coordinator: escalate on cost > threshold,
   negative sentiment, or financial/legal topic; else auto-resolve.

Every step writes a **status event** (the "digital trace" the doc wants),
which drives the dashboard and the case-memory store.

---

## 4. Tech stack (and why)

- **Voice — ElevenLabs Agents** (not raw TTS). Built-in STT, turn-taking, RAG
  knowledge base, tool-calling, and Twilio/WhatsApp telephony. Don't build the
  voice pipeline by hand.
- **Orchestration — Google ADK (Python).** `pip install google-adk` (Py 3.11+).
  Multi-agent composition, workflow runtime, built-in `adk web` trace UI for
  showing agents "thinking" to judges. Model-agnostic via LiteLLM.
  ⚠️ ADK ships breaking changes ~bi-weekly — **pin the version** and keep all
  ADK code isolated.
- **Reasoning LLM — Claude via ADK's LiteLLM adapter.**
  `LiteLlm(model="anthropic/claude-...")`, driven by `ANTHROPIC_API_KEY`.
  (Optionally Gemini Flash for cheap triage, Claude for nuanced reasoning.)
- **Glue API — FastAPI.** Thin HTTP surface the voice layer calls.
- **State + RAG — SQLite (local) + ElevenLabs native knowledge base** for
  lease/SOP RAG (zero retrieval code to write). Swap SQLite → Cloud SQL only if
  durable concurrent state is needed.
- **Dashboard — bpmn-js** (bpmn.io) rendering a real BPMN diagram, nodes lit by
  the status feed. React optional; static HTML + CDN is faster under pressure.
- **Containers — one Dockerfile** for both local Compose and GCP Cloud Run (no
  env drift).

---

## 5. The scaffold (already built & tested)

A working, tested orchestration layer. Runs **offline with zero keys**
(deterministic fallback = demo insurance) and upgrades to **ADK + Claude** with
`USE_LLM=1`. Tests pass; full HTTP flow verified including the escalation path.

**Layout:**
```
app/
  main.py                 FastAPI surface (the only HTTP layer)
  core/schemas.py         SHARED CONTRACT — the merge seam
  core/repository.py      SQLite state (swap URL for Cloud SQL)
  agents/coordinator.py   orchestration brain + risk gate
  agents/triage.py        dispatcher persona (fallback + LLM)
  agents/comms.py         message drafting (templates + LLM)
  agents/llm_triage.py    ADK LlmAgent + Claude (USE_LLM=1)
  agents/llm_comms.py     ADK LlmAgent + Claude (USE_LLM=1)
  tools/property_tools.py property memory, vendor pick, messaging (mocked)
data/property_memory.json  the "property memory" fixture
tests/test_flow.py         offline end-to-end tests
Dockerfile, docker-compose.yml, requirements.txt, .env.example, README.md
```

**Design principles:** transport-agnostic; each agent/tool is a small testable
unit; LLM lives behind a flag with try/except fallback; state isolated in one
repository module; everything containerized from day one.

**HTTP contract:**
- `POST /api/requests` → run orchestration, return `OrchestratorResponse`
- `GET /api/requests/{id}/status` → status events for the dashboard
- `GET /health` → Cloud Run liveness

**Risk-gate logic (in coordinator):** legal → escalate; financial → escalate;
angry sentiment → escalate; estimated cost > property approval threshold →
escalate; otherwise → auto-resolve.

---

## 6. Run & deploy

**Local (offline demo, no keys):**
```bash
cp .env.example .env          # USE_LLM stays 0
docker compose up --build
curl -X POST localhost:8080/api/requests -H 'Content-Type: application/json' \
  -d '{"request_id":"d1","channel":"phone","raw_text":"Heating is broken","property_hint":"Musterstrasse 12"}'
curl localhost:8080/api/requests/d1/status
```

**Real agents (ADK + Claude):** set `USE_LLM=1` + `ANTHROPIC_API_KEY` in `.env`.

**Agent trace UI:** `adk web app/agents`

**Tests:** `PYTHONPATH=. pytest -q`

**GCP Cloud Run (low cost — scales to zero, idle ≈ free):**
```bash
gcloud builds submit --tag europe-west1-docker.pkg.dev/PROJECT/ops/orchestrator
gcloud run deploy orchestrator \
  --image europe-west1-docker.pkg.dev/PROJECT/ops/orchestrator \
  --region europe-west1 --allow-unauthenticated \
  --min-instances 0 --max-instances 2 --memory 512Mi \
  --set-secrets ANTHROPIC_API_KEY=anthropic-key:latest \
  --set-env-vars USE_LLM=1
```
Keep SQLite on the container for the hackathon (resets on cold start — fine for
a demo). Cloud SQL bills hourly; avoid unless needed.

---

## 7. Team plan (5 people, 1 day)

**Split (3 devs, 2 business):**
- **Dev 1 — Voice edge.** ElevenLabs inbound + outbound agents, knowledge base,
  Twilio, the webhook into FastAPI. Most-visible artifact → most reliable dev.
- **Dev 2 — Orchestration brain.** ADK coordinator + sub-agents, Claude/Gemini
  wiring, workflow graph. (This scaffold is the starting point.)
- **Dev 3 — Glue + dashboard.** FastAPI webhooks, SQLite, status feed, bpmn-js
  dashboard. Floats to unblock 1 & 2.
- **Business 1 — Domain + content.** Lease/SOP/FAQ docs for RAG, maintenance
  taxonomy + urgency rules, agent prompts/guardrails.
- **Business 2 — Story, pitch, BPMN model.** The canonical BPMN process, the
  pitch, slides, demo script + dry runs, ROI framing.

**Phases:**
- **0 (30 min) Align:** lock ONE scenario, pin versions, distribute keys, repo.
- **1 (~2h) Vertical slice in isolation:** each piece alive returning fake data.
- **2 (~2h) First integration (make-or-break):** tenant call → webhook → ADK →
  fake vendor → SMS. One unbroken thread. *Now you have a demo.*
- **3 (~2h) Real coordination:** real outbound vendor call, RAG triage,
  sentiment escalation, live BPMN updates.
- **4 (~1.5h) Bonus points:** pick 2 of {multi-channel, human escalation,
  resolution tracking}.
- **5 (~2h) Freeze, polish, rehearse:** code-freeze, run live 3×, **record a
  backup video**, finalize pitch.

**Failure modes to pre-empt:** stage network/telephony flakiness (→ backup
video + a typed-input fallback for the tenant); ADK version drift (→ pin +
isolate ADK code).

**Winning demo (the money shot):** a real phone call → ElevenLabs answers,
diagnoses, classifies urgency + sentiment → ADK orchestrator → outbound
ElevenLabs call to a vendor proposing time/cost → SMS confirmation to tenant →
the whole thing lighting up a live BPMN dashboard node-by-node. The BPMN
diagram is the differentiator that makes it legible to judges.

---

## 8. Naming

- **Project / repo:** `hausmind` ("Haus" + "mind" — the AI brain; bilingual,
  short, demo-friendly). Alternatives: `hauskeeper`, `meister-ai`, `tenant-loop`,
  `building-brain`, `propmem`.
- **Team:** **Team Hausmind** (matches the repo). Personality alternatives:
  *Die Hausmeister*, *Loop Closers*, *The Always-On*, *Schicht-frei*.

**Tagline:** "Hausmind — perfect memory and operational follow-through for every
property manager." (Lifted from the interview's key strategic insight; judges
respond well when the pitch traces to real user research.)

**One-line repo description:**
> An always-on AI operations layer that triages tenant requests, coordinates
> vendors, and closes the loop — humans only where it matters.

---

## 9. Merge plan with the voice layer

1. Agree on `schemas.InboundRequest` / `OrchestratorResponse` (share that file).
2. Colleague's ElevenLabs webhook POSTs `InboundRequest` to `/api/requests`.
3. Replace `tools.property_tools.send_message` with the real ElevenLabs/Twilio
   call.
4. Replace the vendor agent's stubbed cost/window with a real outbound vendor
   call that negotiates them.
5. Dashboard polls (or websockets) `/api/requests/{id}/status`; its node ids
   match the emitted events: `intake`, `triage`, `context`, `vendor`,
   `risk_gate`, `comms`, `closed`.

---

## 10. Open next steps

- BPMN node mapping aligned exactly to the status-event node ids.
- Real property-memory RAG (replace the JSON fixture).
- Outbound vendor negotiation on a live ElevenLabs call.
- Resolution tracking / case-memory learning loop.
