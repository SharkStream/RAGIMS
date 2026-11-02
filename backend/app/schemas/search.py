"""Search-test schemas (G2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SearchTestRequest(BaseModel):
    """Payload of ``POST /search/test``.

    ``tenant_id`` is deliberately NOT accepted here — it is taken from the
    authenticated user and hard-filtered server-side (never satisfiable by
    the caller).
    """

    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=20)
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Optional whitelisted AND-only equality filters "
        "(doc_id / access_level / chunk_index); tenant & visibility are "
        "always enforced and cannot be relaxed.",
    )


class SearchHit(BaseModel):
    score: float
    text: str
    doc_id: str
    version: int | None = None
    page: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchTestResponse(BaseModel):
    hits: list[SearchHit]
    took_embedding_ms: float
    took_search_ms: float
    took_total_ms: float
