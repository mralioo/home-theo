HOST     ?= localhost
PORT     ?= 8080
BASE_URL  = http://$(HOST):$(PORT)
ADK_URL   = http://$(HOST):8001

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

# ── GET /api/requests/{id}/status ────────────────────────────────────────────
# Usage:  make status ID=demo-heat-01

.PHONY: status

status:
	@test -n "$(ID)" || (echo "Usage: make status ID=<request_id>"; exit 1)
	curl -s $(BASE_URL)/api/requests/$(ID)/status | python3 -m json.tool

# ── Run all demo requests sequentially ───────────────────────────────────────

.PHONY: demo

demo: health req-heating req-plumbing req-electrical req-elevator \
      req-access req-cleaning req-financial req-legal req-emergency req-angry

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
