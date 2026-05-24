# Context Service — Vector RAG for Property Management

Semantic search layer that replaces the static JSON fixture with a live
OpenSearch vector database. Buildings, vendors, and historical incidents are
indexed as dense vectors (384-dim, `BAAI/bge-small-en-v1.5` via fastembed /
ONNX). Queries are hybrid: **knn_vector** when embeddings are available,
**BM25 multi-field** fallback otherwise.

---

## Architecture

```
orchestrator
  └─► property_tools.lookup_property_context("Musterstrasse 12")
        │
        ├─ CONTEXT_SERVICE_URL set?
        │     └─► GET /buildings/search?q=Musterstrasse+12
        │           └─► OpenSearch knn_vector query (384-dim)
        │                 returns: building doc
        │         GET /incidents/search?building_id=PROP-001
        │               returns: last 5 incidents → recent_cases
        │         → PropertyContext
        │
        └─ fallback → data/property_memory.json fixture

  └─► property_tools.select_vendor(heating, ctx)
        │
        ├─ CONTEXT_SERVICE_URL set?
        │     └─► GET /vendors/search?category=heating
        │           └─► knn_vector + filter(categories=heating) + sort(rating desc)
        │                 prefers building's preferred_vendor if in results
        │         cost = vendor.hourly_rate_eur × category_hours
        │         → VendorPlan (real rates, not hardcoded table)
        │
        └─ fallback → hardcoded cost table
```

```
┌──────────────────────────────────────────────────────────────┐
│  context-service  :8002   (Python / FastAPI)                 │
│                                                              │
│  startup:                                                    │
│    fastembed loads BAAI/bge-small-en-v1.5 (ONNX, 384-dim)  │
│    seed_all() reads data/seed_data.json                      │
│    creates 3 indices in OpenSearch, bulk-indexes docs        │
│                                                              │
│  indices:                                                    │
│    buildings  — property profiles + knn_vector               │
│    vendors    — contractor profiles + knn_vector             │
│    incidents  — historical cases + knn_vector                │
└───────────────────────┬──────────────────────────────────────┘
                        │  opensearch-py client
┌───────────────────────▼──────────────────────────────────────┐
│  opensearch  :9200   (OpenSearch 2.11, single-node, no TLS)  │
│                                                              │
│  k-NN plugin enabled, index.knn=true per index               │
│  heap: 512 MB (dev), volume: opensearch_data (persistent)    │
└──────────────────────────────────────────────────────────────┘
```

---

## Data schema

### buildings

| Field | Type | Description |
|---|---|---|
| `id` | keyword | `PROP-001` |
| `name` | text | human-readable address |
| `address` | text | full street address |
| `city` | keyword | for filtering |
| `type` | keyword | `WEG` or `SEV` |
| `manager_name` | text | responsible property manager |
| `units` | integer | number of apartments |
| `built_year` | integer | construction year |
| `access_notes` | text | how to enter / where keys are |
| `key_holder` | text | person holding the backup key |
| `approval_threshold_eur` | float | cost above which owner approval required |
| `preferred_vendors` | object | `{category: vendor_id}` |
| `description` | text | free-text context for semantic search |
| `embedding` | knn_vector (384) | dense vector for similarity search |

### vendors

| Field | Type | Description |
|---|---|---|
| `id` | keyword | `VEND-001` |
| `name` | text | company name |
| `categories` | keyword[] | e.g. `["heating","plumbing"]` |
| `city` | keyword | service area |
| `hourly_rate_eur` | float | base rate; cost = rate × estimated hours |
| `emergency_surcharge_pct` | integer | % added for emergency callouts |
| `rating` | float | 0–5 aggregate review score |
| `review_count` | integer | number of reviews |
| `avg_response_time_hours` | float | typical arrival time |
| `certifications` | text | professional certifications |
| `description` | text | free-text for semantic search |
| `embedding` | knn_vector (384) | dense vector |

### incidents

| Field | Type | Description |
|---|---|---|
| `id` | keyword | `INC-001` |
| `building_id` | keyword | FK → buildings |
| `date` | date | `YYYY-MM-DD` |
| `category` | keyword | heating / plumbing / electrical / … |
| `urgency` | keyword | emergency / high / normal / low |
| `description` | text | what was reported |
| `resolution` | text | what was done |
| `vendor_id` | keyword | who did the work |
| `cost_eur` | float | final invoice |
| `duration_days` | integer | time to resolve |
| `tenant_sentiment` | keyword | angry / frustrated / neutral / calm |
| `escalated` | boolean | was human approval needed |
| `embedding` | knn_vector (384) | dense vector over description + resolution |

---

## API endpoints

All endpoints return JSON. Base URL: `http://localhost:8002`.

### `GET /health`
```json
{"status": "ok"}
```

### `GET /buildings/search?q=<text>&top_k=3`
Semantic search over building name, address, description.
Returns the top-k most similar buildings.

```bash
curl "http://localhost:8002/buildings/search?q=Musterstrasse+12"
curl "http://localhost:8002/buildings/search?q=Berlin+WEG+Altbau+6+Stockwerke"
```

### `GET /vendors/search?category=<cat>&top_k=5`
Filters by category, sorts by rating, uses vector similarity for description match.

```bash
curl "http://localhost:8002/vendors/search?category=heating"
curl "http://localhost:8002/vendors/search?category=electrical&top_k=3"
```

### `GET /incidents/search?building_id=<id>&category=<cat>&top_k=10`
Retrieve incident history for a building, optionally filtered by category.

```bash
curl "http://localhost:8002/incidents/search?building_id=PROP-001"
curl "http://localhost:8002/incidents/search?building_id=PROP-001&category=heating"
```

### `GET /incidents/semantic?q=<text>&building_id=<id>`
Free-text semantic search over incident descriptions and resolutions.
Useful for finding similar past cases.

```bash
curl "http://localhost:8002/incidents/semantic?q=radiator+cold+pressure+drop&building_id=PROP-001"
```

### `POST /admin/reindex`
Re-reads `data/seed_data.json` and re-indexes all documents.
Use after editing the seed file.

```bash
curl -X POST http://localhost:8002/admin/reindex
```

---

## Make targets

```bash
make ctx-health                          # service liveness
make ctx-search-building Q="Musterstrasse 12"
make ctx-search-vendor   CAT=heating
make ctx-incidents       BID=PROP-001
make ctx-semantic        Q="heating pressure" BID=PROP-001
make ctx-reindex                         # re-seed after data change

make os-health                           # OpenSearch cluster health
make os-indices                          # list indices + doc counts
```

---

## Enable in orchestrator

Set in `.env` or docker-compose environment:

```env
CONTEXT_SERVICE_URL=http://context-service:8002
```

When set, `property_tools.py` queries the context service first. On any error
(service down, timeout, no results) it silently falls back to the JSON fixture —
the demo never breaks.

---

## Adding more data

Edit `data/seed_data.json` and run:
```bash
make ctx-reindex
```

Or replace the file entirely and restart the `context-service` container:
```bash
docker compose restart context-service
```

---

## Production path

| Component | Dev (now) | Production |
|---|---|---|
| OpenSearch | Single node, no auth | OpenSearch Service (AWS) or Elastic Cloud |
| Embeddings | `BAAI/bge-small-en-v1.5` baked in image | Same or upgrade to larger model |
| Data source | `seed_data.json` file | ETL from property management DB (e.g. Domus, immoware24) |
| Re-indexing | Manual `POST /admin/reindex` | Webhook from DB on record change |
| Auth | None (dev) | API key or JWT |
