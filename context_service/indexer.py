"""
Creates OpenSearch indices and seeds them from data/seed_data.json.
Indices:
  buildings  — property profiles
  vendors    — contractor profiles with rates + reviews
  incidents  — historical maintenance cases per building
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from opensearchpy import OpenSearch
from tenacity import retry, stop_after_attempt, wait_fixed

import embedder

logger = logging.getLogger(__name__)

DATA_PATH = os.environ.get("DATA_PATH", "/data/seed_data.json")
OS_URL    = os.environ.get("OPENSEARCH_URL", "http://localhost:9200")

DIM = embedder.EMBED_DIM

# ── Index mappings ────────────────────────────────────────────────────────────

BUILDINGS_MAPPING = {
    "settings": {"index": {"knn": True}},
    "mappings": {
        "properties": {
            "id":                     {"type": "keyword"},
            "name":                   {"type": "text", "analyzer": "standard"},
            "address":                {"type": "text", "analyzer": "standard"},
            "city":                   {"type": "keyword"},
            "type":                   {"type": "keyword"},
            "manager_name":           {"type": "text"},
            "manager_email":          {"type": "keyword"},
            "manager_phone":          {"type": "keyword"},
            "units":                  {"type": "integer"},
            "built_year":             {"type": "integer"},
            "access_notes":           {"type": "text"},
            "key_holder":             {"type": "text"},
            "approval_threshold_eur": {"type": "float"},
            "preferred_vendors":      {"type": "object", "enabled": True},
            "description":            {"type": "text"},
            "embedding":              {"type": "knn_vector", "dimension": DIM},
        }
    },
}

VENDORS_MAPPING = {
    "settings": {"index": {"knn": True}},
    "mappings": {
        "properties": {
            "id":                       {"type": "keyword"},
            "name":                     {"type": "text", "analyzer": "standard"},
            "categories":               {"type": "keyword"},
            "city":                     {"type": "keyword"},
            "phone":                    {"type": "keyword"},
            "email":                    {"type": "keyword"},
            "hourly_rate_eur":          {"type": "float"},
            "emergency_surcharge_pct":  {"type": "integer"},
            "rating":                   {"type": "float"},
            "review_count":             {"type": "integer"},
            "avg_response_time_hours":  {"type": "float"},
            "languages":                {"type": "keyword"},
            "certifications":           {"type": "text"},
            "description":              {"type": "text"},
            "embedding":                {"type": "knn_vector", "dimension": DIM},
        }
    },
}

INCIDENTS_MAPPING = {
    "settings": {"index": {"knn": True}},
    "mappings": {
        "properties": {
            "id":              {"type": "keyword"},
            "building_id":     {"type": "keyword"},
            "date":            {"type": "date"},
            "category":        {"type": "keyword"},
            "urgency":         {"type": "keyword"},
            "description":     {"type": "text"},
            "resolution":      {"type": "text"},
            "vendor_id":       {"type": "keyword"},
            "vendor_name":     {"type": "keyword"},
            "cost_eur":        {"type": "float"},
            "duration_days":   {"type": "integer"},
            "tenant_sentiment":{"type": "keyword"},
            "escalated":       {"type": "boolean"},
            "embedding":       {"type": "knn_vector", "dimension": DIM},
        }
    },
}


# ── Client ────────────────────────────────────────────────────────────────────

def get_client() -> OpenSearch:
    return OpenSearch(OS_URL, use_ssl=False, verify_certs=False)


@retry(stop=stop_after_attempt(20), wait=wait_fixed(3))
def wait_for_opensearch() -> OpenSearch:
    client = get_client()
    info = client.info()
    logger.info("OpenSearch ready: %s", info["version"]["number"])
    return client


# ── Index helpers ─────────────────────────────────────────────────────────────

def _ensure_index(client: OpenSearch, name: str, mapping: dict) -> None:
    if not client.indices.exists(index=name):
        client.indices.create(index=name, body=mapping)
        logger.info("Created index: %s", name)
    else:
        logger.info("Index exists: %s", name)


def _index_doc(client: OpenSearch, index: str, doc_id: str, body: dict) -> None:
    client.index(index=index, id=doc_id, body=body, refresh=True)


# ── Seeding ───────────────────────────────────────────────────────────────────

def _embed_text(*parts: str) -> list[float] | None:
    text = " ".join(p for p in parts if p)
    return embedder.embed(text)


def seed_all() -> None:
    logger.info("Waiting for OpenSearch…")
    client = wait_for_opensearch()

    _ensure_index(client, "buildings", BUILDINGS_MAPPING)
    _ensure_index(client, "vendors",   VENDORS_MAPPING)
    _ensure_index(client, "incidents", INCIDENTS_MAPPING)

    data_file = Path(DATA_PATH)
    if not data_file.exists():
        logger.warning("Seed file not found: %s — skipping seeding", DATA_PATH)
        return

    data = json.loads(data_file.read_text())

    # Buildings
    for b in data.get("buildings", []):
        doc = {**b}
        vec = _embed_text(b.get("name", ""), b.get("address", ""), b.get("description", ""))
        if vec:
            doc["embedding"] = vec
        _index_doc(client, "buildings", b["id"], doc)
    logger.info("Indexed %d buildings", len(data.get("buildings", [])))

    # Vendors
    for v in data.get("vendors", []):
        doc = {**v}
        vec = _embed_text(
            v.get("name", ""),
            " ".join(v.get("categories", [])),
            v.get("description", ""),
        )
        if vec:
            doc["embedding"] = vec
        _index_doc(client, "vendors", v["id"], doc)
    logger.info("Indexed %d vendors", len(data.get("vendors", [])))

    # Incidents
    for inc in data.get("incidents", []):
        doc = {**inc}
        vec = _embed_text(inc.get("description", ""), inc.get("resolution", ""))
        if vec:
            doc["embedding"] = vec
        _index_doc(client, "incidents", inc["id"], doc)
    logger.info("Indexed %d incidents", len(data.get("incidents", [])))
