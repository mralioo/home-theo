# DEV1_CONTEXT.md
> **Role:** Dev 1 — Voice / ElevenLabs lane (external, no code in repo)
> **Project:** Hausmind — ElevenLabs × Google ADK hackathon
> **Repo:** `https://github.com/mralioo/home-theo.git`
> **Branch you'll work against:** whatever is current; you usually don't push code.
> **Author of this brief:** Dev 3 (for the agentic-coding handoff)

This file is your starting point for using **Claude Code** to finalize the
voice layer for the demo. It tells Claude what you own, what the
orchestrator expects, and what verification commands to run. Paste it into
your Claude Code session when you start working.

---

## 0. Resume-anywhere boot prompt

When you open Claude Code in a fresh terminal:

```
I'm Dev 1 on the Hausmind hackathon — voice/ElevenLabs lane. Read
DEV1_CONTEXT.md, then check the live orchestrator at $BASE_URL/health
and skim its OpenAPI at $BASE_URL/docs. Confirm the webhook contract in
DEV1_CONTEXT.md §3 still matches the deployed app, then ask me what
needs fixing.
```

That gets Claude into the right mental model in under a minute.

---

## 1. Mission

The tenant calls a number → ElevenLabs Conversational Agent triages in
German/English → mid-call, the agent calls our `dispatch_maintenance`
server-tool → the orchestrator (Dev 2's brain + Dev 3's glue) decides what
to do → the agent reads back a confirmation. After the call, ElevenLabs
fires a post-call webhook with the transcript summary.

You own everything *outside* the Python repo:
- The Twilio phone number (or whatever PSTN provider).
- The ElevenLabs inbound agent (system prompt, voice ID, language).
- The ElevenLabs outbound agent used for vendor calls.
- The server-tool definition + the post-call webhook URL.

---

## 2. Lane boundaries

| You own | You read-but-don't-modify | Off-limits |
|---|---|---|
| ElevenLabs dashboard (agents, tools) | `app/core/schemas.py` (the contract) | `app/routes/*`, `app/static/*`, `app/agents/*`, `app/core/*` (other devs' lanes) |
| Twilio config / phone numbers | `DEMO.md` | Anything inside `app/` |
| Voice prompts, language, persona | `DEV3_CONTEXT.md` §5.4 / §14 (full payload + sample tool YAML) | |

If a code change is needed in `app/`, ping Dev 2 (agents) or Dev 3 (routes,
webhooks, dashboards).

---

## 3. The contract (DO NOT DRIFT — verified by repo tests)

### 3.1 Inbound server-tool (mid-call) — `POST /webhooks/elevenlabs/tool`

```yaml
url:    $BASE_URL/webhooks/elevenlabs/tool
method: POST
headers:
  X-Webhook-Secret: ${env.WEBHOOK_SECRET}   # MUST match what Cloud Run has
  Content-Type: application/json
```

Body the orchestrator expects (every field name matters; the pydantic
adapter is strict):

```json
{
  "tool_name": "dispatch_maintenance",
  "conversation_id": "{{conversation.id}}",
  "caller_id": "{{conversation.caller_id}}",
  "parameters": {
    "issue_summary": "{{parameters.issue_summary}}",
    "category_hint": "heating|plumbing|electrical|elevator|access_keys|cleaning|financial|legal|other",
    "urgency_hint":  "emergency|high|normal|low",
    "property_hint": "Musterstrasse 12",
    "reporter_name": "Frau Schmidt"
  }
}
```

Response the orchestrator gives back (your agent reads this aloud):

```json
{
  "ticket_id": "<conversation_id>",
  "agent_message": "Got it — I'm dispatching maintenance now. We'll text you once a vendor is scheduled."
}
```

**Auth failures:** wrong / missing `X-Webhook-Secret` → 401. Body shape
mismatch → 422. Both verified by `tests/test_elevenlabs_webhook.py` in
the repo.

### 3.2 Post-call webhook — `POST /webhooks/elevenlabs/post-call`

Same `X-Webhook-Secret` header. Body:

```json
{
  "conversation_id": "<same as inbound>",
  "transcript_summary": "Vendor confirmed slot tomorrow 09:00.",
  "transcript": "(full transcript, optional)",
  "duration_seconds": 42.5,
  "success": true
}
```

Response: `{ "ticket_id": "...", "matched_existing": true }`. The summary
is attached to the ticket's payload for the dashboards.

### 3.3 Outbound vendor calls (orchestrator → ElevenLabs)

Already wired. Your outbound agent receives:

```json
{
  "agent_id": "<your outbound agent id>",
  "to_number": "+49...",
  "conversation_initiation_client_data": {
    "dynamic_variables": { "ticket_id": "..." }
  }
}
```

You configure the agent prompt to use `{{dynamic_variables.ticket_id}}` if
you want to reference it during the call.

---

## 4. Required env vars on the orchestrator (Cloud Run)

```
WEBHOOK_SECRET=<random string — must match the X-Webhook-Secret header you configure>
ELEVENLABS_API_KEY=<your key>
ELEVENLABS_AGENT_ID_OUTBOUND=<your outbound agent's id>
USE_LLM=1                      # if you want Claude in the loop; 0 for deterministic fallback
ANTHROPIC_API_KEY=<sk-ant-...>  # only needed when USE_LLM=1
```

Set them via:
```bash
gcloud run services update orchestrator --update-env-vars \
  "WEBHOOK_SECRET=...,ELEVENLABS_API_KEY=...,..." \
  --region europe-west1
```

---

## 5. Verification — before judges arrive

### 5.1 Make sure the orchestrator side is up
```bash
curl $BASE_URL/health                 # → {"status":"ok"}
make preflight BASE=$BASE_URL         # runs scripts/preflight.sh, 16 checks
```

### 5.2 Simulate the inbound webhook (no real call needed)
```bash
curl -X POST "$BASE_URL/webhooks/elevenlabs/tool" \
  -H "X-Webhook-Secret: $WEBHOOK_SECRET" \
  -H 'Content-Type: application/json' \
  -d '{
        "tool_name":"dispatch_maintenance",
        "conversation_id":"sim-001",
        "caller_id":"+4915123456789",
        "parameters":{
          "issue_summary":"Heizung ist seit gestern kalt",
          "property_hint":"Musterstrasse 12"
        }
      }'
# → 200 + {"ticket_id":"sim-001","agent_message":"..."}

# Wait ~1s for the background orchestration, then check:
curl "$BASE_URL/api/requests/sim-001" | jq '.decision, .payload.vendor'
```

### 5.3 Live call rehearsal
1. Dial the number.
2. Open `$BASE_URL/app?role=manager` in a browser.
3. Speak in German or English about a maintenance issue.
4. Within ~8 seconds, the ticket should appear at the top of the queue.
5. Click it — the pipeline strip animates as the coordinator runs.

If the ticket doesn't appear: check Cloud Run logs for the
`/webhooks/elevenlabs/tool` request. Almost always either (a) wrong secret
or (b) body shape drift in the ElevenLabs tool config.

---

## 6. Common things you'll ask Claude to do

Examples of good prompts for Claude Code:

- *"Read the ElevenLabs tool config in DEV1_CONTEXT.md §3.1 and write me a
   filled-in YAML for the production agent, using `$BASE_URL=...`."*
- *"Open Cloud Run logs for the orchestrator and grep for the last 10
   `/webhooks/elevenlabs/tool` calls. Tell me which failed and why."*
- *"The simulator curl in §5.2 returns 422. What field shape did I get
   wrong? Diff my payload against `app/routes/elevenlabs.py::ElevenLabsToolCall`."*
- *"Draft a system prompt for the inbound agent in German, persona: warm,
   professional Hausverwaltung receptionist. The agent's only job is to
   collect issue_summary + property_hint and then call the
   dispatch_maintenance tool."*
- *"Generate a sanity test in pytest that I can run locally to verify my
   inbound webhook body matches the pydantic model."*

---

## 7. Things to flag for me (Dev 3) before the demo

- Final Cloud Run URL once we deploy → I'll bake it into DEMO.md.
- The exact vendor phone number you want pre-configured for outbound — I'll
  add it to a demo-only env var so the manager's "call vendor" button works
  during the demo.
- Any field-name drift in your tool config that doesn't match §3.1 — I'd
  rather adjust on my side than have the demo 422 on stage.

---

## 8. If everything breaks during the demo

Fallback path is documented in `DEMO.md` Act 5:
- `USE_LLM=0` → orchestrator runs deterministic keyword triage, no API key.
- Skip the live call: open `$BASE_URL/dashboard`, type a tenant message,
  click "Run Pipeline". Same coordinator runs, same dashboards animate.

You don't need to do anything for these fallbacks — they're already wired.
Just know they exist if the call doesn't connect.
