"""G2 retrieval-test tests (offline — fake embedder + fake vector store).

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_g2_search.py -v -p no:cacheprovider
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from qdrant_client import models as qmodels


class FakeVectorStore:
    def __init__(self) -> None:
        self.calls: list[tuple[list[float], qmodels.Filter | None, int]] = []

    def search(self, query_vector, query_filter=None, top_k=5, **kw):
        self.calls.append((query_vector, query_filter, top_k))
        return [
            SimpleNamespace(
                score=0.93 - i * 0.05,
                payload={
                    "tenant_id": "t-1",
                    "doc_id": f"d-{i}",
                    "doc_version_id": f"v-{i}",
                    "version": 1,
                    "is_latest": True,
                    "is_deleted": False,
                    "chunk_index": i,
                    "page": i + 1,
                    "access_level": "internal",
                    "chunk_hash": f"h{i}",
                    "text": f"chunk {i} about quarterly revenue",
                },
            )
            for i in range(min(top_k, 3))
        ]


class FakeEmbedder:
    dimension = 4
    model_name = "fake"

    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_batch(self, texts, **kw):
        self.queries.extend(texts)
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


def make_result(**kw):
    from app.services.search_service import search_test

    vec = FakeVectorStore()
    emb = FakeEmbedder()
    result = search_test(
        query=kw.get("query", "revenue"),
        tenant_id=kw.get("tenant_id", "t-1"),
        top_k=kw.get("top_k", 5),
        filters=kw.get("filters"),
        embedder=emb,
        storage=SimpleNamespace(vectors=vec),
    )
    return result, emb, vec


# --------------------------------------------------------------------------- #
# acceptance 1: relevant chunks + sane scores
# --------------------------------------------------------------------------- #


def test_returns_hits_with_scores_and_payload_fields() -> None:
    result, emb, vec = make_result()
    assert [h.doc_id for h in result.hits] == ["d-0", "d-1", "d-2"]
    scores = [h.score for h in result.hits]
    assert scores == sorted(scores, reverse=True)  # descending
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert result.hits[0].text.startswith("chunk 0")
    assert result.hits[0].version == 1 and result.hits[0].page == 1
    assert result.hits[0].metadata["chunk_index"] == 0
    assert emb.queries == ["revenue"]
    assert vec.calls[0][2] == 5  # top_k forwarded


# --------------------------------------------------------------------------- #
# acceptance 2: tenant isolation + visibility are hard-coded (security)
# --------------------------------------------------------------------------- #


def test_mandatory_conditions_always_present() -> None:
    result, _, vec = make_result()
    must = vec.calls[0][1].must
    keys = {c.key for c in must}
    assert keys == {"tenant_id", "is_latest", "is_deleted"}
    values = {c.key: c.match.value for c in must}
    assert values["tenant_id"] == "t-1"
    assert values["is_latest"] is True
    assert values["is_deleted"] is False


def test_request_filters_cannot_relax_security_keys() -> None:
    malicious = {
        "tenant_id": "t-evil",
        "is_latest": False,
        "is_deleted": True,
        "doc_id": "d-9",  # whitelisted -> allowed
    }
    result, _, vec = make_result(filters=malicious)
    must = vec.calls[0][1].must
    values = {c.key: c.match.value for c in must}
    # security keys untouched
    assert values["tenant_id"] == "t-1"
    assert values["is_latest"] is True
    assert values["is_deleted"] is False
    # whitelisted extra filter AND-ed
    assert values["doc_id"] == "d-9"
    assert result.hits[0].doc_id == "d-0"  # fake store ignores filters


# --------------------------------------------------------------------------- #
# acceptance 3: per-phase timings
# --------------------------------------------------------------------------- #


def test_timings_reported_and_positive() -> None:
    result, _, _ = make_result()
    assert result.took_embedding_ms >= 0
    assert result.took_search_ms >= 0
    assert result.took_total_ms == pytest.approx(
        result.took_embedding_ms + result.took_search_ms, rel=1e-6
    )


# --------------------------------------------------------------------------- #
# route registered; tenant_id not part of the request body
# --------------------------------------------------------------------------- #


def test_route_registered_and_body_schema_has_no_tenant_id() -> None:
    from app.main import app

    client = TestClient(app)
    spec = client.get("/openapi.json").json()
    assert "/api/search/test" in spec["paths"]
    body = spec["paths"]["/api/search/test"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    schema = spec["components"]["schemas"][body.rsplit("/", 1)[-1]]
    assert "tenant_id" not in schema["properties"]  # security: not client-supplied
