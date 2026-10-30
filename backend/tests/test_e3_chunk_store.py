"""E3 chunk persistence tests (offline logic; live probe covers the DB).

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_e3_chunk_store.py -v -p no:cacheprovider
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.chunkers.base import Chunk as ChunkDTO
from app.models.chunk import Chunk
from app.services.chunk_store import write_back_point_ids
from app.services.vectoring_service import point_id_for

FAKE_SESSION = SimpleNamespace(commit=lambda: None)


def make_dto(i: int) -> ChunkDTO:
    return ChunkDTO(text=f"text {i}", token_count=10 + i, page=i)


def test_write_back_aligns_ids_by_position() -> None:
    rows = [
        Chunk(
            doc_version_id="v1",
            doc_id="d1",
            version=1,
            chunk_index=i,
            text="t",
            chunk_hash="h",
        )
        for i in range(3)
    ]
    write_back_point_ids(FAKE_SESSION, rows, [f"p{i}" for i in range(3)])
    assert [r.qdrant_point_id for r in rows] == ["p0", "p1", "p2"]


def test_write_back_rejects_mismatch() -> None:
    rows = [
        Chunk(
            doc_version_id="v1",
            doc_id="d1",
            version=1,
            chunk_index=i,
            text="t",
            chunk_hash="h",
        )
        for i in range(2)
    ]
    with pytest.raises(ValueError, match="mismatch"):
        write_back_point_ids(FAKE_SESSION, rows, ["only-one"])


def test_write_back_matches_e2_point_ids() -> None:
    """The IDs E2 derives must be exactly what E3 stores back (F composes)."""
    rows = [
        Chunk(
            doc_version_id="v1",
            doc_id="d1",
            version=1,
            chunk_index=i,
            text="t",
            chunk_hash="h",
        )
        for i in range(2)
    ]
    ids = [point_id_for("v1", i) for i in range(2)]
    write_back_point_ids(FAKE_SESSION, rows, ids)
    assert rows[0].qdrant_point_id == point_id_for("v1", 0)
    assert rows[1].qdrant_point_id == point_id_for("v1", 1)


def test_chunk_dto_carries_metadata_for_meta_column() -> None:
    dto = ChunkDTO(
        chunk_index=0, text="t", token_count=1, metadata={"block_type": "heading"}
    )
    assert dto.metadata["block_type"] == "heading"
    # insert_chunks maps dto.metadata -> Chunk.meta (column ``metadata``)
