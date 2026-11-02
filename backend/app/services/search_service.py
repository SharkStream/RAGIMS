"""Custom search service (G2 — retrieval test endpoint).

Enforces tenant isolation + ``is_latest`` + ``is_deleted=false`` HARD-CODED
in the Qdrant filter — the caller can never relax them. Optional request
filters are whitelisted AND-extra conditions only (never tenant/visibility).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from qdrant_client import models as qmodels

from app.clients.embedder import BaseEmbedder, get_default_embedder
from app.core.db import SessionLocal
from app.services.storage import StorageService, get_storage

#: Extra request filters allowed to be AND-ed on top of the mandatory ones.
_EXTRA_FILTER_KEYS = {
    "doc_id",
    "access_level",
    "chunk_index",
}


@dataclass
class SearchHit:
    score: float
    text: str
    doc_id: str
    version: int | None
    page: int | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchTestResult:
    hits: list[SearchHit]
    took_embedding_ms: float
    took_search_ms: float
    took_total_ms: float


def _mandatory_filter(tenant_id: str) -> qmodels.Filter:
    """Security-critical filter — never overridable by request input."""
    return qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="tenant_id", match=qmodels.MatchValue(value=tenant_id)
            ),
            qmodels.FieldCondition(
                key="is_latest", match=qmodels.MatchValue(value=True)
            ),
            qmodels.FieldCondition(
                key="is_deleted", match=qmodels.MatchValue(value=False)
            ),
        ]
    )


def _extend_filter(base: qmodels.Filter, filters: dict[str, Any]) -> qmodels.Filter:
    """AND extra whitelisted equality conditions; unknown keys are ignored."""
    must = list(base.must or [])
    for key, value in filters.items():
        if key in _EXTRA_FILTER_KEYS:
            must.append(
                qmodels.FieldCondition(key=key, match=qmodels.MatchValue(value=value))
            )
    return qmodels.Filter(must=must)


def search_test(
    *,
    query: str,
    tenant_id: str,
    top_k: int = 10,
    filters: dict[str, Any] | None = None,
    embedder: BaseEmbedder | None = None,
    storage: StorageService | None = None,
) -> SearchTestResult:
    """Embed the query, search Qdrant under the hard tenant/version filter.

    Returns hits + per-phase timings (acceptance 3).
    """
    storage = storage or get_storage()
    emb = embedder

    t0 = time.perf_counter()
    if emb is None:
        # resolve the configured default model lazily
        with SessionLocal() as session:
            emb = get_default_embedder(session)
    vector = emb.embed_batch([query])[0]
    took_embedding_ms = (time.perf_counter() - t0) * 1000.0

    qfilter = _mandatory_filter(tenant_id)
    if filters:
        qfilter = _extend_filter(qfilter, filters)

    t1 = time.perf_counter()
    points = storage.vectors.search(vector, query_filter=qfilter, top_k=top_k)
    took_search_ms = (time.perf_counter() - t1) * 1000.0

    hits: list[SearchHit] = []
    for p in points:
        payload = p.payload or {}
        hits.append(
            SearchHit(
                score=float(p.score),
                text=str(payload.get("text", "")),
                doc_id=str(payload.get("doc_id", "")),
                version=(
                    int(payload["version"])
                    if payload.get("version") is not None
                    else None
                ),
                page=int(payload["page"]) if payload.get("page") is not None else None,
                metadata={
                    k: payload[k]
                    for k in (
                        "doc_version_id",
                        "chunk_index",
                        "access_level",
                        "chunk_hash",
                    )
                    if k in payload
                },
            )
        )
    return SearchTestResult(
        hits=hits,
        took_embedding_ms=took_embedding_ms,
        took_search_ms=took_search_ms,
        took_total_ms=took_embedding_ms + took_search_ms,
    )
