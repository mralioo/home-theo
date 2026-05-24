"""Thin wrapper around fastembed. Falls back gracefully if unavailable."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

EMBED_DIM = 384  # BAAI/bge-small-en-v1.5
_MODEL_NAME = "BAAI/bge-small-en-v1.5"
_model = None


def load_model() -> None:
    global _model
    try:
        from fastembed import TextEmbedding
        _model = TextEmbedding(_MODEL_NAME)
        logger.info("Embedding model loaded: %s", _MODEL_NAME)
    except Exception as exc:
        logger.warning("fastembed unavailable (%s) — vector search disabled, BM25 only", exc)


def embed(text: str) -> list[float] | None:
    if _model is None:
        return None
    try:
        return list(_model.embed([text]))[0].tolist()
    except Exception as exc:
        logger.debug("embed failed: %s", exc)
        return None
