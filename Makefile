HOST              ?= localhost
PORT              ?= 8080
BASE_URL           = http://$(HOST):$(PORT)
ADK_URL            = http://$(HOST):8001
CTX_URL            = http://$(HOST):8002
OS_URL             = http://$(HOST):9200
WEBHOOK_SECRET    ?= dev-only-not-secret
ADMIN_SECRET      ?= dev-only-not-secret

# ── Docker ───────────────────────────────────────────────────────────────────

.PHONY: up down build logs

up:
	docker compose up --build -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

logs-orchestrator:
	docker compose logs -f orchestrator

logs-adk:
	docker compose logs -f adk-ui

logs-context:
	docker compose logs -f context-service

logs-opensearch:
	docker compose logs -f opensearch

# ── Context service ───────────────────────────────────────────────────────────
# Usage: make ctx-search-building Q="Musterstrasse 12"
#        make ctx-search-vendor   CAT=heating
#        make ctx-incidents       BID=PROP-001

.PHONY: ctx-health ctx-search-building ctx-search-vendor ctx-incidents ctx-reindex

ctx-health:
	curl -s $(CTX_URL)/health | python3 -m json.tool

ctx-search-building:
	@test -n "$(Q)" || (echo "Usage: make ctx-search-building Q='<text>'"; exit 1)
	curl -s -G "$(CTX_URL)/buildings/search" --data-urlencode "q=$(Q)" | python3 -m json.tool

ctx-search-vendor:
	@test -n "$(CAT)" || (echo "Usage: make ctx-search-vendor CAT=heating"; exit 1)
	curl -s "$(CTX_URL)/vendors/search?category=$(CAT)" | python3 -m json.tool

ctx-incidents:
	@test -n "$(BID)" || (echo "Usage: make ctx-incidents BID=PROP-001"; exit 1)
	curl -s "$(CTX_URL)/incidents/search?building_id=$(BID)" | python3 -m json.tool

ctx-semantic:
	@test -n "$(Q)" || (echo "Usage: make ctx-semantic Q='heating broken' BID=PROP-001"; exit 1)
	@test -n "$(BID)" || (echo "BID required"; exit 1)
	curl -s -G "$(CTX_URL)/incidents/semantic" --data-urlencode "q=$(Q)" --data-urlencode "building_id=$(BID)" | python3 -m json.tool

ctx-reindex:
	curl -s -X POST $(CTX_URL)/admin/reindex | python3 -m json.tool

os-health:
	curl -s $(OS_URL)/_cluster/health | python3 -m json.tool

os-indices:
	curl -s "$(OS_URL)/_cat/indices?v"

# ── Health ───────────────────────────────────────────────────────────────────

.PHONY: health

health:
	curl -s $(BASE_URL)/health | python3 -m json.tool

# ── POST /api/requests ───────────────────────────────────────────────────────
# Usage:  make req-heating              (offline demo, auto-resolved)
#         USE_LLM=1 make req-heating    (live ADK + Claude)

.PHONY: req-heating req-plumbing req-electrical req-elevator \
        req-access req-cleaning req-financial req-legal \
        req-emergency req-angry req-unknown-property

req-heating:
	curl -s -X POST $(BASE_URL)/api/requests \
	  -H 'Content-Type: application/json' \
	  -d '{"request_id":"demo-heat-01","channel":"phone","raw_text":"The radiator in my flat is cold since this morning. No heat at all.","property_hint":"Musterstrasse 12","reporter_name":"Max Mustermann","reporter_phone":"+4930000001"}' \
	  | python3 -m json.tool

req-plumbing:
	curl -s -X POST $(BASE_URL)/api/requests \
	  -H 'Content-Type: application/json' \
	  -d '{"request_id":"demo-plumb-01","channel":"sms","raw_text":"There is a water leak under the kitchen sink, it is getting worse.","property_hint":"Musterstrasse 12"}' \
	  | python3 -m json.tool

req-electrical:
	curl -s -X POST $(BASE_URL)/api/requests \
	  -H 'Content-Type: application/json' \
	  -d '{"request_id":"demo-elec-01","channel":"email","raw_text":"The power outlet in the bathroom stopped working and the fuse keeps tripping.","property_hint":"Musterstrasse 12"}' \
	  | python3 -m json.tool

req-elevator:
	curl -s -X POST $(BASE_URL)/api/requests \
	  -H 'Content-Type: application/json' \
	  -d '{"request_id":"demo-lift-01","channel":"chat","raw_text":"The lift is stuck between floors 2 and 3. Nobody is inside but it has been like this for hours.","property_hint":"Musterstrasse 12"}' \
	  | python3 -m json.tool

req-access:
	curl -s -X POST $(BASE_URL)/api/requests \
	  -H 'Content-Type: application/json' \
	  -d '{"request_id":"demo-key-01","channel":"phone","raw_text":"I lost my key and I am locked out of the building.","property_hint":"Musterstrasse 12"}' \
	  | python3 -m json.tool

req-cleaning:
	curl -s -X POST $(BASE_URL)/api/requests \
	  -H 'Content-Type: application/json' \
	  -d '{"request_id":"demo-clean-01","channel":"walk_in","raw_text":"The staircase has not been cleaned in weeks, it is very dirty.","property_hint":"Musterstrasse 12"}' \
	  | python3 -m json.tool

req-financial:
	@echo "→ Financial: expect decision=escalate_human"
	curl -s -X POST $(BASE_URL)/api/requests \
	  -H 'Content-Type: application/json' \
	  -d '{"request_id":"demo-fin-01","channel":"email","raw_text":"I received an invoice for EUR 820 for a repair I did not authorise. Please explain this charge.","property_hint":"Musterstrasse 12"}' \
	  | python3 -m json.tool

req-legal:
	@echo "→ Legal: expect decision=escalate_human"
	curl -s -X POST $(BASE_URL)/api/requests \
	  -H 'Content-Type: application/json' \
	  -d '{"request_id":"demo-legal-01","channel":"email","raw_text":"I want to know my rights regarding the management contract. I may need to consult a lawyer.","property_hint":"Musterstrasse 12"}' \
	  | python3 -m json.tool

req-emergency:
	@echo "→ Emergency: expect urgency=emergency"
	curl -s -X POST $(BASE_URL)/api/requests \
	  -H 'Content-Type: application/json' \
	  -d '{"request_id":"demo-emerg-01","channel":"phone","raw_text":"There is flooding in the basement, water is coming through the ceiling!","property_hint":"Musterstrasse 12"}' \
	  | python3 -m json.tool

req-angry:
	@echo "→ Angry sentiment: expect decision=escalate_human"
	curl -s -X POST $(BASE_URL)/api/requests \
	  -H 'Content-Type: application/json' \
	  -d '{"request_id":"demo-angry-01","channel":"phone","raw_text":"This is the third time I report this! Unacceptable!!! Nobody ever calls back!!!","property_hint":"Musterstrasse 12","detected_sentiment":"angry"}' \
	  | python3 -m json.tool

req-unknown-property:
	@echo "→ Unknown property: falls back to _default context"
	curl -s -X POST $(BASE_URL)/api/requests \
	  -H 'Content-Type: application/json' \
	  -d '{"request_id":"demo-unk-01","channel":"chat","raw_text":"The heating is broken."}' \
	  | python3 -m json.tool

# ── Delta Campus showcase requests ───────────────────────────────────────────

.PHONY: req-delta-heating req-delta-plumbing req-delta-elevator \
        req-delta-access req-delta-angry req-delta-legal

req-delta-heating:
	curl -s -X POST $(BASE_URL)/api/requests \
	  -H 'Content-Type: application/json' \
	  -d '{"request_id":"dc-heat-01","channel":"chat","raw_text":"The open-plan coworking area on the 3rd floor has no heating since this morning. People are wearing coats.","property_hint":"The Delta Campus Berlin"}' \
	  | python3 -m json.tool

req-delta-plumbing:
	curl -s -X POST $(BASE_URL)/api/requests \
	  -H 'Content-Type: application/json' \
	  -d '{"request_id":"dc-plumb-01","channel":"sms","raw_text":"The shared kitchen sink on the 4th floor is dripping badly and the cabinet below is soaked.","property_hint":"The Delta Campus Berlin"}' \
	  | python3 -m json.tool

req-delta-elevator:
	@echo "→ Emergency: trapped person in atrium lift"
	curl -s -X POST $(BASE_URL)/api/requests \
	  -H 'Content-Type: application/json' \
	  -d '{"request_id":"dc-lift-01","channel":"phone","raw_text":"The middle lift in the atrium stopped between floors 2 and 3, someone is inside and pressing the alarm button!","property_hint":"The Delta Campus Berlin"}' \
	  | python3 -m json.tool

req-delta-access:
	curl -s -X POST $(BASE_URL)/api/requests \
	  -H 'Content-Type: application/json' \
	  -d '{"request_id":"dc-key-01","channel":"chat","raw_text":"My transponder card stopped working this morning. I cannot enter the building or reach my office.","property_hint":"The Delta Campus Berlin"}' \
	  | python3 -m json.tool

req-delta-angry:
	@echo "→ Angry: expect decision=escalate_human"
	curl -s -X POST $(BASE_URL)/api/requests \
	  -H 'Content-Type: application/json' \
	  -d '{"request_id":"dc-angry-01","channel":"phone","raw_text":"The gym on floor 1 is overheating and nobody is fixing it! This is the third complaint this month. Unacceptable!!!","property_hint":"The Delta Campus Berlin","detected_sentiment":"angry"}' \
	  | python3 -m json.tool

req-delta-legal:
	@echo "→ Legal: expect decision=escalate_human"
	curl -s -X POST $(BASE_URL)/api/requests \
	  -H 'Content-Type: application/json' \
	  -d '{"request_id":"dc-legal-01","channel":"email","raw_text":"I want to understand my rights regarding the management contract and noise regulations in the event space.","property_hint":"The Delta Campus Berlin"}' \
	  | python3 -m json.tool

# ── GET /api/requests/{id}/status ────────────────────────────────────────────
# Usage:  make status ID=demo-heat-01

.PHONY: status

status:
	@test -n "$(ID)" || (echo "Usage: make status ID=<request_id>"; exit 1)
	curl -s $(BASE_URL)/api/requests/$(ID)/status | python3 -m json.tool

# ── GET /events/stream/{id}  (SSE — pipe through curl -N) ────────────────────
# Usage:  make stream ID=demo-heat-01

.PHONY: stream

stream:
	@test -n "$(ID)" || (echo "Usage: make stream ID=<request_id>"; exit 1)
	curl -N $(BASE_URL)/events/stream/$(ID)

# ── ElevenLabs webhooks ───────────────────────────────────────────────────────
# Simulate what ElevenLabs posts mid-call (tool dispatch).
# Usage:  make elevenlabs-tool
#         WEBHOOK_SECRET=mysecret make elevenlabs-tool

.PHONY: elevenlabs-tool elevenlabs-post-call

elevenlabs-tool:
	curl -s -X POST $(BASE_URL)/webhooks/elevenlabs/tool \
	  -H 'Content-Type: application/json' \
	  -H 'X-Webhook-Secret: $(WEBHOOK_SECRET)' \
	  -d '{"tool_name":"dispatch_maintenance","conversation_id":"el-demo-01","caller_id":"+4930123456","parameters":{"issue_summary":"The heating in the 3rd floor coworking area is broken","property_hint":"The Delta Campus Berlin","reporter_name":"Demo Caller"}}' \
	  | python3 -m json.tool

elevenlabs-post-call:
	curl -s -X POST $(BASE_URL)/webhooks/elevenlabs/post-call \
	  -H 'Content-Type: application/json' \
	  -H 'X-Webhook-Secret: $(WEBHOOK_SECRET)' \
	  -d '{"conversation_id":"el-demo-01","transcript_summary":"Caller reported broken heating on 3rd floor. Dispatch confirmed.","duration_seconds":47.3,"success":true}' \
	  | python3 -m json.tool

# ── Admin actions ─────────────────────────────────────────────────────────────
# Usage:  make call-vendor ID=demo-heat-01 PHONE=+4930999888

.PHONY: call-vendor

call-vendor:
	@test -n "$(ID)" || (echo "Usage: make call-vendor ID=<ticket_id> PHONE=<e164>"; exit 1)
	@test -n "$(PHONE)" || (echo "PHONE required, e.g. PHONE=+4930999888"; exit 1)
	curl -s -X POST $(BASE_URL)/actions/call-vendor \
	  -H 'Content-Type: application/json' \
	  -H 'X-Admin-Secret: $(ADMIN_SECRET)' \
	  -d '{"ticket_id":"$(ID)","to_number":"$(PHONE)"}' \
	  | python3 -m json.tool

# ── Run all demo requests sequentially ───────────────────────────────────────

.PHONY: demo demo-delta

demo: health req-heating req-plumbing req-electrical req-elevator \
      req-access req-cleaning req-financial req-legal req-emergency req-angry \
      req-delta-heating req-delta-elevator req-delta-angry

demo-delta: health req-delta-heating req-delta-plumbing req-delta-elevator \
            req-delta-access req-delta-angry req-delta-legal

# ── Tests ─────────────────────────────────────────────────────────────────────

.PHONY: test test-verbose

test:
	PYTHONPATH=. pytest -q

test-verbose:
	PYTHONPATH=. pytest -v

# ── Local dev (no Docker) ─────────────────────────────────────────────────────

.PHONY: serve adk-ui

serve:
	PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

adk-ui:
	PYTHONPATH=. adk web adk_agents --host 0.0.0.0 --port 8000
