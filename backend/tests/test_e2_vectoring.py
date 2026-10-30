"""E2 vector upsert tests (offline — fake VectorStore via StorageService).

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_e2_vectoring.py -v -p no:cacheprovider
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import tiktoken
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.services.vectoring_service import (
    UPSERT_BATCH_SIZE,
    build_payload,
    point_id_for,
    upsert_doc_vectors,
)

ENC = tiktoken.get_encoding("cl100k_base")


class FakeVectorStore:
    """Records ensure_collection/upsert calls; can fail the first N upserts."""

    def __init__(self, fail_times: int = 0):
        self.ensured: list[tuple[str, int | None]] = []
        self.upserted: list[list] = []
        self.fail_times = fail_times
        self.calls = 0

    def ensure_collection(self, name: str, dimension: int | None) -> str:
        self.ensured.append((name, dimension))
        return name

    def upsert_points(self, points, collection: str) -> None:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError("qdrant hiccup")
        self.upserted.append(list(points))


def fake_storage(store: FakeVectorStore) -> SimpleNamespace:
    return SimpleNamespace(
        ensure_vector_collection=lambda dimension=None: store.ensure_collection(
            "documents", dimension
        ),
        upsert_points=lambda points: store.upsert_points(points, "documents"),
    )


def make_rows(n: int = 3):
    doc = Document(
        id="d1",
        tenant_id="t1",
        datasource_id="ds1",
        file_name="f.txt",
        file_type="txt",
        access_level="internal",
    )
    version = DocumentVersion(id="v1", doc_id="d1", version=2, content_hash="h")
    chunks = [
        Chunk(
            doc_version_id="v1",
            doc_id="d1",
            version=2,
            chunk_index=i,
            text=f"chunk text {i}",
            chunk_hash=f"h{i}",
            page=i + 1,
        )
        for i in range(n)
    ]
    return doc, version, chunks


def vectors(n: int, dim: int = 8) -> list[list[float]]:
    return [[float(i)] * dim for i in range(n)]


# --------------------------------------------------------------------------- #
# point id strategy (E2 step 3)
# --------------------------------------------------------------------------- #


def test_point_id_is_deterministic() -> None:
    a = point_id_for("version-x", 3)
    b = point_id_for("version-x", 3)
    assert a == b
    assert len(a) == 36 and a.count("-") == 4  # uuid5 string form


def test_point_id_differs_per_index_and_version() -> None:
    assert point_id_for("v1", 0) != point_id_for("v1", 1)
    assert point_id_for("v1", 0) != point_id_for("v2", 0)


# --------------------------------------------------------------------------- #
# payload (E2 step 2, acceptance 1)
# --------------------------------------------------------------------------- #


def test_payload_has_full_filter_set() -> None:
    doc, version, chunks = make_rows(1)
    payload = build_payload(doc, version, chunks[0])
    assert payload["tenant_id"] == "t1"
    assert payload["doc_id"] == "d1"
    assert payload["doc_version_id"] == "v1"
    assert payload["version"] == 2
    assert payload["is_latest"] is True  # acceptance: is_latest=true
    assert payload["is_deleted"] is False
    assert payload["access_level"] == "internal"
    assert payload["chunk_index"] == 0
    assert payload["page"] == 1
    assert payload["chunk_hash"] == "h0"
    assert payload["text"] == "chunk text 0"


# --------------------------------------------------------------------------- #
# batching, collection dimension, retry
# --------------------------------------------------------------------------- #


def test_ensures_collection_with_vector_dimension() -> None:
    doc, version, chunks = make_rows(2)
    store = FakeVectorStore()
    upsert_doc_vectors(
        doc, version, chunks, vectors(2, dim=16), storage=fake_storage(store)
    )
    assert store.ensured == [("documents", 16)]


def test_upsert_is_batched() -> None:
    n = UPSERT_BATCH_SIZE + 10
    doc, version, chunks = make_rows(n)
    store = FakeVectorStore()
    ids = upsert_doc_vectors(
        doc, version, chunks, vectors(n), storage=fake_storage(store)
    )
    assert len(ids) == n
    assert [len(b) for b in store.upserted] == [UPSERT_BATCH_SIZE, 10]


def test_transient_upsert_failure_is_retried() -> None:
    doc, version, chunks = make_rows(2)
    store = FakeVectorStore(fail_times=1)
    ids = upsert_doc_vectors(
        doc,
        version,
        chunks,
        vectors(2),
        storage=fake_storage(store),
        retry_when=lambda e: isinstance(e, ConnectionError),
    )
    assert len(ids) == 2 and store.calls == 2


def test_permanent_upsert_failure_propagates() -> None:
    doc, version, chunks = make_rows(1)
    store = FakeVectorStore()
    store.upsert_points = lambda points, collection: (_ for _ in ()).throw(
        ValueError("bad")
    )
    with pytest.raises(ValueError):
        upsert_doc_vectors(
            doc, version, chunks, vectors(1), storage=fake_storage(store)
        )


def test_mismatched_counts_rejected() -> None:
    doc, version, chunks = make_rows(2)
    with pytest.raises(ValueError, match="mismatch"):
        upsert_doc_vectors(
            doc, version, chunks, vectors(3), storage=fake_storage(FakeVectorStore())
        )


def test_empty_input_is_noop() -> None:
    doc, version, _ = make_rows(0)
    store = FakeVectorStore()
    assert upsert_doc_vectors(doc, version, [], [], storage=fake_storage(store)) == []
    assert store.ensured == []


# --------------------------------------------------------------------------- #
# idempotency (acceptance 2)
# --------------------------------------------------------------------------- #


def test_repeat_upsert_yields_identical_point_ids() -> None:
    doc, version, chunks = make_rows(4)
    store = FakeVectorStore()
    first = upsert_doc_vectors(
        doc, version, chunks, vectors(4), storage=fake_storage(store)
    )
    second = upsert_doc_vectors(
        doc, version, chunks, vectors(4), storage=fake_storage(store)
    )
    assert first == second  # same IDs -> upsert overwrites, no duplicates
    ids = [str(p.id) for batch in store.upserted for p in batch]
    assert len(ids) == 8 and len(set(ids)) == 4  # 8 upserts, 4 distinct IDs


def test_point_payload_matches_point_id_index() -> None:
    doc, version, chunks = make_rows(2)
    store = FakeVectorStore()
    upsert_doc_vectors(doc, version, chunks, vectors(2), storage=fake_storage(store))
    for point, chunk in zip(store.upserted[0], chunks, strict=True):
        assert point.id == point_id_for("v1", chunk.chunk_index)
        assert point.payload["chunk_index"] == chunk.chunk_index
        assert len(point.vector) == 8
