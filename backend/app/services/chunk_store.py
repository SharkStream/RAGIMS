"""Chunk persistence (E3): MySQL-first order with idempotent re-runs.

Stage order contract (E3 step 3) — stage F calls these in sequence:

1. :func:`insert_chunks` — batch insert into ``chunks`` (idempotent per
   ``(doc_version_id, chunk_index)``: re-runs reuse existing rows, so a
   failed pipeline retry never duplicates rows).
2. E2 :func:`app.services.vectoring_service.upsert_doc_vectors` — Qdrant.
3. :func:`write_back_point_ids` — fill ``chunks.qdrant_point_id``.

:func:`finalize_version` records ``chunk_count``/``embedding_model`` after
the chunk set is stable. Any step can be re-run: inserts are no-ops for
existing indexes, upserts overwrite the same point IDs (E2), and the
write-back is a plain UPDATE.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chunkers.base import Chunk as ChunkDTO
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion


def existing_index_map(session: Session, doc_version_id: str) -> dict[int, Chunk]:
    """``chunk_index -> row`` for the version's already-persisted chunks."""
    rows = session.scalars(
        select(Chunk).where(Chunk.doc_version_id == doc_version_id)
    ).all()
    return {row.chunk_index: row for row in rows}


def insert_chunks(
    session: Session,
    doc: Document,
    version: DocumentVersion,
    chunks: list[ChunkDTO],
) -> list[Chunk]:
    """Batch-insert chunk rows, skipping indexes that already exist (E3 step 1).

    Returns rows aligned with ``chunks`` (inserted or reused). Rows are
    immutable per the model contract — re-ingestion creates a new version.
    """
    known = existing_index_map(session, version.id)
    rows: list[Chunk] = []
    for dto in chunks:
        row = known.get(dto.chunk_index)
        if row is None:
            row = Chunk(
                doc_version_id=version.id,
                doc_id=doc.id,
                version=version.version,
                chunk_index=dto.chunk_index,
                text=dto.text,
                token_count=dto.token_count,
                chunk_hash=dto.chunk_hash,
                page=dto.page,
                meta=dict(dto.metadata) if dto.metadata else None,
            )
            session.add(row)
        rows.append(row)
    session.commit()
    return rows


def finalize_version(
    session: Session,
    version: DocumentVersion,
    *,
    embedding_model: str,
    chunk_count: int | None = None,
) -> None:
    """Update ``document_versions.chunk_count``/``embedding_model`` (E3 step 2)."""
    if chunk_count is None:
        chunk_count = len(existing_index_map(session, version.id))
    version.chunk_count = chunk_count
    version.embedding_model = embedding_model
    session.commit()


def write_back_point_ids(
    session: Session, chunks: list[Chunk], point_ids: list[str]
) -> None:
    """Fill ``chunks.qdrant_point_id`` after the Qdrant upsert (E3 step 3)."""
    if len(chunks) != len(point_ids):
        raise ValueError(
            f"chunks/point_ids mismatch: {len(chunks)} vs {len(point_ids)}"
        )
    for row, point_id in zip(chunks, point_ids, strict=True):
        row.qdrant_point_id = point_id
    session.commit()
