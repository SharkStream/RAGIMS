"""E4 consistency tests (offline — fake storage/session where possible).

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_e4_consistency.py -v -p no:cacheprovider
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.services.consistency import (
    repair_missing_point_ids,
    version_filter,
)
from qdrant_client import models as qmodels

# --------------------------------------------------------------------------- #
# version filter (E4 step 1 prerequisite)
# --------------------------------------------------------------------------- #


def test_version_filter_targets_doc_version_id() -> None:
    flt = version_filter("v-123")
    cond = flt.must[0]
    assert isinstance(cond, qmodels.FieldCondition)
    assert cond.key == "doc_version_id"
    assert cond.match.value == "v-123"


# --------------------------------------------------------------------------- #
# purge + upsert composition (E4 step 1: delete-before-upsert)
# --------------------------------------------------------------------------- #


class FakeVectorStore:
    def __init__(self) -> None:
        self.points: dict[str, list] = {}
        self.deleted_filters: list = []

    def delete_points_by_filter(self, query_filter, collection: str) -> int:
        self.deleted_filters.append(query_filter)
        return 0


def fake_storage(store: FakeVectorStore) -> SimpleNamespace:
    return SimpleNamespace(
        delete_points_by_filter=lambda query_filter: store.delete_points_by_filter(
            query_filter, "documents"
        ),
        search_vectors=lambda *a, **kw: [],
    )


def test_purge_deletes_by_version_filter() -> None:
    store = FakeVectorStore()
    purge = SimpleNamespace(
        delete_points_by_filter=lambda f: store.delete_points_by_filter(f, "documents")
    )
    from app.services.consistency import purge_version_points

    count = purge_version_points("v-1", storage=purge)
    assert count == 0
    assert len(store.deleted_filters) == 1
    cond = store.deleted_filters[0].must[0]
    assert cond.key == "doc_version_id" and cond.match.value == "v-1"


def test_repair_backfills_existing_point_without_embedding(monkeypatch) -> None:
    """Chunk missing point_id but point exists in Qdrant -> zero-cost fill."""

    class Row:
        def __init__(self, idx: int, version: str = "v1", doc: str = "d1") -> None:
            self.chunk_index = idx
            self.doc_version_id = version
            self.doc_id = doc
            self.text = f"text {idx}"
            self.qdrant_point_id = None

    rows = [Row(0)]
    hit = SimpleNamespace(id="pt-1", payload={"chunk_index": 0})
    storage = SimpleNamespace(
        search_vectors=lambda *a, **kw: [hit],
        delete_points_by_filter=lambda f: 0,
        upsert_points=lambda points: pytest.fail("must not re-embed"),
    )

    class Session:
        def __init__(self) -> None:
            self.commits = 0

        def scalars(self, *a, **kw):  # noqa: ANN002, ANN003
            return SimpleNamespace(all=lambda: rows)

        def get(self, *a, **kw):  # noqa: ANN002, ANN003
            return SimpleNamespace(id="d1", version=1)

        def commit(self) -> None:
            self.commits += 1

    session = Session()
    # dimension probe: monkeypatch the embedder used inside repair
    import app.services.consistency as cons

    class FakeEmb:
        dimension = 8

    monkeypatch.setattr(cons, "get_default_embedder", lambda s: FakeEmb())
    report = repair_missing_point_ids(session, storage=storage)
    assert report == {"backfilled": 1, "reembedded": 0}
    assert rows[0].qdrant_point_id == "pt-1"


def test_repair_reembeds_when_point_missing(monkeypatch) -> None:
    """Point absent from Qdrant -> re-embed + re-upsert + write back."""

    class Row:
        def __init__(self, idx: int, version: str = "v1", doc: str = "d1") -> None:
            self.chunk_index = idx
            self.doc_version_id = version
            self.doc_id = doc
            self.text = f"text {idx}"
            self.qdrant_point_id = None

    rows = [Row(2)]
    storage = SimpleNamespace(
        search_vectors=lambda *a, **kw: [],
        delete_points_by_filter=lambda f: 0,
        upsert_points=lambda points: None,
    )

    class Session:
        def scalars(self, *a, **kw):  # noqa: ANN002, ANN003
            return SimpleNamespace(all=lambda: rows)

        def get(self, *a, **kw):  # noqa: ANN002, ANN003
            return SimpleNamespace(id="d1", version=1)

        def commit(self) -> None:
            pass

    import app.services.consistency as cons

    class FakeEmb:
        dimension = 8

        def embed_with_usage(self, texts):
            assert texts == ["text 2"]
            return [[0.5] * 8], SimpleNamespace(token_count=3)

    captured: dict = {}

    def fake_upsert(doc, version, chunks, vectors, *, storage=None, **kw):
        captured["chunks"] = list(chunks)
        return [f"new-{c.chunk_index}" for c in chunks]

    monkeypatch.setattr(cons, "get_default_embedder", lambda s: FakeEmb())
    monkeypatch.setattr(cons, "upsert_doc_vectors", fake_upsert)
    report = repair_missing_point_ids(Session(), storage=storage)
    assert report == {"backfilled": 0, "reembedded": 1}
    assert rows[0].qdrant_point_id == "new-2"
    assert captured["chunks"][0] is rows[0]


def test_repair_noop_when_nothing_missing() -> None:
    class Session:
        def scalars(self, *a, **kw):  # noqa: ANN002, ANN003
            return SimpleNamespace(all=lambda: [])

    report = repair_missing_point_ids(Session(), storage=SimpleNamespace())
    assert report == {"backfilled": 0, "reembedded": 0}
