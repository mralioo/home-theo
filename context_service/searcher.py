"""
Search functions: hybrid (knn_vector + BM25) when embeddings available,
BM25-only fallback otherwise.
"""
from __future__ import annotations

import logging

from opensearchpy import OpenSearch

import embedder
from indexer import get_client

logger = logging.getLogger(__name__)


def _knn_query(field: str, vector: list[float], k: int) -> dict:
    return {"knn": {field: {"vector": vector, "k": k}}}


def _bm25_building_query(q: str) -> dict:
    return {
        "multi_match": {
            "query": q,
            "fields": ["name^3", "address^2", "city^2", "description", "access_notes"],
            "fuzziness": "AUTO",
        }
    }


def _bm25_vendor_query(category: str, extra: str = "") -> dict:
    return {
        "bool": {
            "must": {"term": {"categories": category}},
            "should": [
                {"match": {"description": extra or category}},
            ],
        }
    }


# ── Public search API ─────────────────────────────────────────────────────────

def search_buildings(query: str, top_k: int = 3) -> list[dict]:
    client = get_client()
    vec = embedder.embed(query)

    if vec:
        body = {
            "query": _knn_query("embedding", vec, top_k),
            "size": top_k,
        }
    else:
        body = {"query": _bm25_building_query(query), "size": top_k}

    resp = client.search(index="buildings", body=body)
    return [hit["_source"] for hit in resp["hits"]["hits"]]


def search_vendors(
    category: str,
    building_id: str | None = None,
    top_k: int = 5,
) -> list[dict]:
    client = get_client()
    vec = embedder.embed(category)

    if vec:
        body = {
            "query": {
                "bool": {
                    "must": [_knn_query("embedding", vec, top_k)],
                    "filter": {"term": {"categories": category}},
                }
            },
            "sort": [{"rating": {"order": "desc"}}],
            "size": top_k,
        }
    else:
        body = {
            "query": _bm25_vendor_query(category),
            "sort": [{"rating": {"order": "desc"}}],
            "size": top_k,
        }

    resp = client.search(index="vendors", body=body)
    return [hit["_source"] for hit in resp["hits"]["hits"]]


def search_incidents(
    building_id: str,
    category: str | None = None,
    top_k: int = 10,
) -> list[dict]:
    client = get_client()

    must: list[dict] = [{"term": {"building_id": building_id}}]
    if category:
        must.append({"term": {"category": category}})

    body = {
        "query": {"bool": {"must": must}},
        "sort": [{"date": {"order": "desc"}}],
        "size": top_k,
    }

    resp = client.search(index="incidents", body=body)
    return [hit["_source"] for hit in resp["hits"]["hits"]]


def search_incidents_semantic(query: str, building_id: str, top_k: int = 5) -> list[dict]:
    """Free-text semantic search over incidents for a building."""
    client = get_client()
    vec = embedder.embed(query)

    if vec:
        body = {
            "query": {
                "bool": {
                    "must": [_knn_query("embedding", vec, top_k)],
                    "filter": {"term": {"building_id": building_id}},
                }
            },
            "size": top_k,
        }
    else:
        body = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"building_id": building_id}},
                        {"match": {"description": query}},
                    ]
                }
            },
            "size": top_k,
        }

    resp = client.search(index="incidents", body=body)
    return [hit["_source"] for hit in resp["hits"]["hits"]]
