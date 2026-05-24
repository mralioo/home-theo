# Fake Database Generation Prompt

Copy the block below verbatim into any capable LLM (Claude, GPT-4o, Gemini).
It produces a `seed_data.json` drop-in replacement for
`data/seed_data.json` with richer, larger data.

---

## Prompt

```
You are a data engineer generating a realistic synthetic database for a
German property management company called "Hausmind". The company manages
residential buildings across Germany (WEG — homeowner associations — and
SEV — individual rental apartments). It handles tenant communications,
maintenance dispatch, vendor coordination, and owner reporting.

Generate a JSON object with exactly three top-level keys:
  "buildings", "vendors", "incidents"

─────────────────────────────────────────────────────────
BUILDINGS — generate 8 buildings
─────────────────────────────────────────────────────────
Each building must have these fields:

{
  "id":                     "PROP-NNN"         // 3-digit zero-padded
  "name":                   string             // street name + number, e.g. "Lindenstrasse 8"
  "address":                string             // full address with postcode and city
  "city":                   string             // one of: Berlin, München, Hamburg, Frankfurt am Main, Düsseldorf, Köln, Stuttgart, Leipzig
  "type":                   "WEG" | "SEV"
  "manager_name":           string             // German full name
  "manager_email":          string             // realistic email
  "manager_phone":          string             // German format +49...
  "units":                  integer            // 8–48
  "built_year":             integer            // 1955–2005
  "access_notes":           string             // specific: where key is, which floor, weekend rules, codes
  "key_holder":             string             // specific person and location
  "approval_threshold_eur": float              // 300–1200
  "preferred_vendors": {                       // map category → vendor id
    "heating":    "VEND-NNN",
    "plumbing":   "VEND-NNN",
    "electrical": "VEND-NNN",
    "elevator":   "VEND-NNN",   // only if building has elevator (built after 1970 and >3 floors)
    "cleaning":   "VEND-NNN",
    "access_keys":"VEND-NNN"
  },
  "description":            string             // 2–3 sentences: building type, notable features, history, any known issues
}

Rules:
- Cities must be varied — no more than 2 buildings per city.
- 60% WEG, 40% SEV.
- Buildings built before 1970 should mention Altbau characteristics (high ceilings, old pipes, no elevator).
- Buildings built after 1990 should mention modern features (smart meters, underground parking, elevator).
- access_notes must be specific and useful for a contractor arriving on site.
- preferred_vendors must reference vendor ids you generate in the vendors section.

─────────────────────────────────────────────────────────
VENDORS — generate 20 vendors
─────────────────────────────────────────────────────────
Each vendor must have these fields:

{
  "id":                      "VEND-NNN"        // 3-digit zero-padded, start from VEND-001
  "name":                    string            // realistic German company name (GmbH, AG, e.K., or Meisterbetrieb)
  "categories":              string[]          // subset of: ["heating","plumbing","electrical","elevator","cleaning","access_keys"]
  "city":                    string            // matches the cities in buildings
  "phone":                   string            // German format
  "email":                   string            // realistic
  "hourly_rate_eur":         float             // heating: 75–110, electrical: 80–115, plumbing: 70–100, elevator: 100–140, cleaning: 32–50, access_keys: 55–80
  "emergency_surcharge_pct": integer           // 0–100, higher for 24/7 services
  "rating":                  float             // 3.8–5.0
  "review_count":            integer           // 20–400
  "avg_response_time_hours": float             // emergency trades: 0.5–3, cleaning: 24–72
  "languages":               string[]          // ["de"] plus optionally en, tr, pl, ar, ru, it, nl, fr
  "certifications":          string            // real German/EU certification names for the trade
  "description":             string            // 2 sentences: specialty, coverage area, any notable capability
}

Rules:
- At least 3 vendors per category across all vendors.
- Each city in buildings must have at least 2 vendors based there.
- Emergency services (heating, plumbing, electrical, access_keys) must have 24/7 availability — signal this in description.
- Elevator vendors must have TÜV certification.
- Some vendors cover multiple categories (e.g. heating + plumbing, cleaning + access_keys).
- Hourly rates should be realistic for the German market (2024 prices).

─────────────────────────────────────────────────────────
INCIDENTS — generate 50 incidents
─────────────────────────────────────────────────────────
Each incident must have these fields:

{
  "id":               "INC-NNN"           // 3-digit zero-padded
  "building_id":      "PROP-NNN"          // must reference a real building id
  "date":             "YYYY-MM-DD"        // between 2024-01-01 and 2025-12-31
  "category":         string              // heating | plumbing | electrical | elevator | cleaning | access_keys | financial | legal
  "urgency":          string              // emergency | high | normal | low
  "description":      string             // what the tenant reported, first-person or paraphrase, specific details
  "resolution":       string             // what was done, by whom, what was replaced/fixed
  "vendor_id":        "VEND-NNN" | null  // null only for financial/legal incidents
  "vendor_name":      string | null       // matches vendor record, null for financial/legal
  "cost_eur":         float              // 0 for financial/legal, otherwise realistic for the category
  "duration_days":    integer            // 1–21
  "tenant_sentiment": string             // angry | frustrated | neutral | calm
  "escalated":        boolean            // true if: cost > building threshold, OR legal, OR financial, OR angry sentiment
}

Rules:
- Every building must have at least 4 incidents.
- Category distribution across all incidents:
    heating: 25%, plumbing: 20%, electrical: 15%, elevator: 10%,
    cleaning: 10%, access_keys: 8%, financial: 7%, legal: 5%
- Include at least 5 emergency-urgency incidents.
- Include at least 6 escalated incidents.
- Include at least 3 incidents where tenant_sentiment is "angry".
- Descriptions must be specific: mention floor, affected units, symptoms, not generic.
- Resolutions must name the vendor and describe the actual fix (part replaced, area treated, etc.).
- Costs must be realistic:
    heating: 150–1200, plumbing: 80–800, electrical: 100–600,
    elevator: 300–2500, cleaning: 60–400, access_keys: 50–300,
    financial/legal: 0
- escalated must be true when cost_eur > building.approval_threshold_eur.
- Date distribution: spread across 2024 and 2025, with more incidents in winter months
  (Nov–Feb) for heating and fewer in summer.

─────────────────────────────────────────────────────────
OUTPUT FORMAT
─────────────────────────────────────────────────────────
Return ONLY a valid JSON object. No markdown fences, no commentary, no explanation.
The JSON must be parseable by Python's json.loads() without modification.
All string values must be properly escaped.
All ids must be internally consistent (vendor ids referenced in buildings and
incidents must exist in the vendors array).

Start your response with { and end with }
```

---

## Usage

1. Paste the prompt into Claude, GPT-4o, or Gemini.
2. Save the output as `data/seed_data.json`.
3. Reindex:
   ```bash
   make ctx-reindex
   # or if containers are not running:
   docker compose restart context-service
   ```

## Validation (quick sanity check after generation)

```bash
# Valid JSON?
python3 -c "import json; d=json.load(open('data/seed_data.json')); \
  print('buildings:', len(d['buildings']), \
        'vendors:', len(d['vendors']), \
        'incidents:', len(d['incidents']))"

# Referential integrity — all vendor refs in buildings exist?
python3 - <<'EOF'
import json
d = json.load(open('data/seed_data.json'))
vids = {v['id'] for v in d['vendors']}
bids = {b['id'] for b in d['buildings']}
errors = []
for b in d['buildings']:
    for cat, vid in b.get('preferred_vendors', {}).items():
        if vid not in vids:
            errors.append(f"Building {b['id']} references unknown vendor {vid} for {cat}")
for inc in d['incidents']:
    if inc['building_id'] not in bids:
        errors.append(f"Incident {inc['id']} references unknown building {inc['building_id']}")
    if inc['vendor_id'] and inc['vendor_id'] not in vids:
        errors.append(f"Incident {inc['id']} references unknown vendor {inc['vendor_id']}")
if errors:
    for e in errors: print("ERROR:", e)
else:
    print("All references valid ✓")
EOF
```
