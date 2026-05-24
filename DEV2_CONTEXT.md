# DEV2_CONTEXT.md
> **Role:** Dev 2 — Agents + orchestration brain
> **Project:** Hausmind — ElevenLabs × Google ADK hackathon
> **Repo:** `https://github.com/mralioo/home-theo.git`
> **Branch you'll work against:** `main` for new lane work, or a `feat/*` branch.
> **Author of this brief:** Dev 3 (for the agentic-coding handoff)

This file is your starting point for using **Claude Code** to finalize the
orchestration brain for the demo. It tells Claude what you own, what's
off-limits (Dev 3 lane), open polish items with file:line pointers, and
verification commands. Paste it into your Claude Code session.

---

## 0. Resume-anywhere boot prompt

When you open Claude Code:

```
I'm Dev 2 on the Hausmind hackathon — orchestration brain / agents lane.
Read DEV2_CONTEXT.md fully, then run
  USE_LLM=0 DB_PATH=/tmp/dev2.db python3 -m pytest tests/ -q
to confirm the suite is green. Then pick up from §3 (open items),
prioritised, and ask me which to do first.
```

That puts Claude on the same baseline I left things in.

---

## 1. Mission

You own the **decision-making core**: how the orchestrator triages an
inbound request, retrieves property context, picks a vendor, applies the
risk gate, and drafts tenant + vendor messages. Both the deterministic
fallback (no LLM) AND the LLM-augmented path (USE_LLM=1, Claude via
LiteLLM/ADK) live in your lane.

---

## 2. Lane boundaries

| You own (modify freely) | Read-only — Dev 3 lane |
|---|---|
| `app/agents/coordinator.py` | `app/routes/*` (events, elevenlabs, actions, queries) |
| `app/agents/triage.py`, `comms.py` | `app/core/event_bus.py`, `app/core/settings.py`, `app/core/repository_views.py` |
| `app/agents/llm_triage.py`, `llm_comms.py` | `app/static/app.html`, `components/`, `views/*.js` |
| `app/core/schemas.py` (with cross-lane sign-off — frozen seam) | `static/dashboard.{html,js,css}`, `diagram.bpmn` |
| `app/tools/property_tools.py` | `scripts/demo_*.{py,sh}`, `scripts/preflight.sh`, `DEMO.md` |
| `app/core/repository.py` (Dev 3 added 1 line: `event_bus.publish(ev)` in record_event — please don't drop it) | `tests/test_event_bus.py`, `test_sse.py`, `test_elevenlabs_webhook.py`, `test_outbound.py`, `test_requests_list.py`, `test_dev3_advanced.py`, `test_demo.py`, `test_preflight.py`, `test_work_orders.py` |
| `app/main.py` (router mounts — coordinate with Dev 3 if adding to `/api/*`) | `app/tools/elevenlabs_outbound.py` |
| `adk_agents/triage/`, `comms/` | `Makefile` demo-live/demo-reset/preflight targets (additive) |
| `Dockerfile`, `docker-compose.yml`, `Makefile` (your existing targets), `LOCAL_VERIFICATION.md` | `.github/workflows/`, `.pre-commit-config.yaml`, `pyproject.toml` |
| `data/property_memory.json` | `.gitignore`, `DEMO.md` |
| `tests/test_flow.py` | |

If a schema change is needed in `app/core/schemas.py`, ping Dev 3 — that
file is the merge seam with the voice layer and the dashboards both depend
on it. Field-name changes break tests in three places at once.

---

## 3. Open items (prioritised — file:line pointers)

### High priority (demo day risk)

1. **`triage_llm` JSON parse fallback writes to stdout** —
   `app/agents/llm_triage.py:65` (approx). When Claude returns malformed
   JSON, the fallback path swallows the exception with a `print()`. Use
   `logging.getLogger(__name__).warning(...)` so Cloud Run captures it.

2. **No `asyncio.wait_for` around LLM calls** — `app/agents/llm_triage.py`
   and `app/agents/llm_comms.py`. If Anthropic stalls, the entire
   coordinator stalls and the SSE stream goes silent. Wrap each
   `await _triage_agent.run_async(...)` in `asyncio.wait_for(..., timeout=10)`,
   catch `asyncio.TimeoutError`, fall through to the deterministic path.

3. **Dev 1's voice payload field names are unverified vs `schemas.py`** —
   coordinate one 5-min check with Dev 1 before demo. The risk is camelCase
   drift (`issueSummary` vs `issue_summary`) → 422 on stage.

### Medium priority (polish)

4. **Vendor cost table doesn't cover legal/financial/other** —
   `app/tools/property_tools.py:37-40`. Falls back to EUR 150 today.
   The escalation logic already catches legal/financial regardless of cost,
   but `cleaning` falls back to 70 and `access_keys` to 90 — both fine.
   Add explicit entries for `legal: 0`, `financial: 0`, `other: 150` so
   the manager view doesn't show a vendor cost for issues that shouldn't
   have one. Or skip the vendor block entirely for those categories in
   `coordinator.py::handle_request` (cleaner — the vendor card disappears
   on the dashboards too).

5. **Fixture data is thin** — `data/property_memory.json` has one named
   property (`musterstrasse 12`) + `_default`. For the demo, a second
   named property would let you tell a "portfolio" story on the owner
   view. Mirror the existing structure with a `friedrichstrasse 7`
   entry — different manager, different preferred vendors, different
   threshold.

### Low priority (post-demo)

6. **`Diagnosis.summary` unconstrained in LLM mode** — `app/agents/llm_triage.py`.
   Long summaries from Claude blow out the dashboard cards. Either add a
   `max_length=200` constraint in the pydantic Diagnosis (cross-lane —
   ping Dev 3) or trim at the agent: `diag.summary[:200]`.

7. **`repository._conn` per-call (no pooling)** — fine at hackathon scale,
   would matter at >10 RPS. Skip for the demo.

8. **`_risk_gate` no error on `IssueCategory.other`** — falls through cleanly
   today. Worth a defensive `default` branch with a log line.

---

## 4. Verification — local

### 4.1 Quick offline test
```bash
USE_LLM=0 DB_PATH=/tmp/dev2.db python3 -m pytest tests/ -q
# expected: 60 passed (as of latest commit)
```

### 4.2 LLM-mode test (smoke, needs ANTHROPIC_API_KEY)
```bash
ANTHROPIC_API_KEY=sk-ant-... USE_LLM=1 \
  python3 -m uvicorn app.main:app --port 8080 &
curl -X POST localhost:8080/api/requests \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"llm-1","channel":"phone",
       "raw_text":"Die Heizung in meiner Wohnung ist eiskalt seit gestern Abend.",
       "property_hint":"Musterstrasse 12"}'
# expect: decision=auto_resolve, German tenant_message
```

### 4.3 ADK web UI (visual agent debugger)
```bash
adk web app/agents      # browse the triage + comms agents in a browser
# or via Docker Compose:
docker compose up --build      # orchestrator :8080, ADK UI :8001
```

### 4.4 Coverage gate
The CI requires `--cov-fail-under=70`. Check coverage locally before
pushing:
```bash
USE_LLM=0 DB_PATH=/tmp/dev2.db python3 -m pytest --cov=app --cov-report=term-missing
```

### 4.5 BPMN integrity (catches the demo-killer)
```bash
python3 scripts/validate_bpmn.py static/diagram.bpmn
```
This asserts the diagram's node IDs match what `coordinator.py::_emit`
emits. If you add a new BPMN node to the coordinator, the dashboards
silently won't light it up — this script catches it in CI.

---

## 5. Things to coordinate with Dev 3 (me)

- **Any rename in `app/core/schemas.py`** (e.g. field name change, enum
  value change). The dashboards (`views/tenant.js`, `manager.js`, etc.)
  read these field names directly via `/api/requests/{id}`, and several
  tests assert specific keys. Ping me before pushing.
- **Adding new BPMN nodes to `coordinator.py::_emit`** — update
  `static/diagram.bpmn` in the same commit; CI validator will catch it
  otherwise. Existing nodes: `intake`, `triage`, `context`, `vendor`,
  `risk_gate`, `comms`, `closed`. Plus `work_order` (non-BPMN, emitted by
  the facility manager action — don't accidentally re-use that name).
- **Adding routes under `/api/*`** — Dev 3 owns `queries.py` and the
  routing. Better to put new endpoints under a new prefix you own
  (`/agents/*` or `/llm/*`).

---

## 6. Common things you'll ask Claude to do

Example prompts that work well in Claude Code with this context loaded:

- *"Read `app/agents/llm_triage.py` and wrap the LLM call in
   `asyncio.wait_for(..., timeout=10)`. On TimeoutError, fall through to
   the deterministic `triage.py::triage()` path. Don't change the
   function signature — the coordinator calls this in-place."*
- *"Add a second property `Friedrichstrasse 7` to
   `data/property_memory.json` with a different manager name, a different
   preferred_vendors map, and `approval_threshold_eur=300` (lower than
   Musterstrasse). Then run `pytest tests/test_flow.py -v` and confirm
   nothing breaks."*
- *"The LLM triage path prints to stdout on JSON parse error
   (`llm_triage.py` around line 65). Replace with
   `logging.getLogger(__name__).warning(...)` and configure the root
   logger in `app/main.py` to write to stderr with timestamps."*
- *"Run the full test suite and grep the output for any test that takes
   longer than 1 second. We want the suite under 15s for CI."*
- *"Diff `app/core/schemas.py` against the body shape in
   `tests/test_elevenlabs_webhook.py::_payload()`. Are there any fields
   in one that aren't in the other?"*

---

## 7. Demo-day hard rules

- **Don't break the deterministic path.** `USE_LLM=0` is the safety net.
  Every change you make should still pass `pytest tests/test_flow.py -v`
  with `USE_LLM=0`.
- **Don't refactor `coordinator.py`'s emit sequence.** Seven `_emit(...)`
  calls in a specific order (intake → triage → context → vendor → risk_gate
  → comms → closed) drive the dashboard pipeline animation. Changing
  the order changes what judges see.
- **Don't touch the SQLite WAL pragma.** `repository.py::init_db` sets
  `PRAGMA journal_mode=WAL` — removing it makes the event_bus + SSE flow
  race against the repository writer.
- **Don't drop the `event_bus.publish(ev)` line in `record_event`.** It
  looks like a stray import in repository.py, but it's the seam that fans
  status events to the live dashboards.

---

## 8. If everything breaks during the demo

`DEMO.md` Act 5 has the full fallback playbook. Three things you can flip:

1. `gcloud run services update orchestrator --update-env-vars USE_LLM=0 ...`
   → drops LLM path entirely, deterministic everywhere.
2. Open the Hausmind dashboard at `$BASE_URL/dashboard` and submit
   manually — same coordinator runs, same dashboards animate.
3. `pkill -f uvicorn && bash scripts/demo.sh --reset` locally → clean DB,
   re-seeded background. Re-deploy if Cloud Run got into a weird state.

---

## 9. Where Dev 3's pieces live (for reference, not modification)

- **Realtime:** `app/core/event_bus.py`, `app/routes/events.py` (SSE)
- **Webhooks:** `app/routes/elevenlabs.py`
- **Outbound vendor calls:** `app/routes/actions.py`, `app/tools/elevenlabs_outbound.py`
- **Read queries for SPA:** `app/core/repository_views.py`, `app/routes/queries.py`
- **Role-aware SPA:** `app/static/app.html`, `components/`, `views/{tenant,manager,owner,facility}.js`
- **Demo runbook:** `DEMO.md`, `scripts/demo_seed.py`, `scripts/demo.sh`, `scripts/preflight.sh`
- **BPMN dev view:** `static/dashboard.{html,js,css}`, `static/diagram.bpmn`
- **CI / hooks:** `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `pyproject.toml`
- **Tests:** `tests/test_event_bus.py`, `test_sse.py`, `test_elevenlabs_webhook.py`,
  `test_outbound.py`, `test_requests_list.py`, `test_dev3_advanced.py`,
  `test_demo.py`, `test_preflight.py`, `test_work_orders.py`
