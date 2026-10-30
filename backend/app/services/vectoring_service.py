"""Vector upsert service (E2): deterministic IDs, complete payloads, batches.

``point_id_for`` derives a stable UUIDv5 from ``doc_version_id`` +
``chunk_index`` — re-processing the same document version re-upserts the
same point IDs, so Qdrant never accumulates duplicates (acceptance 2).

Payload carries the full retrieval filter set (tenant/version/access) and
mirrors the ``chunks`` row so E3's consistency checks can compare counts.

Stage F calls ``upsert_doc_vectors`` after embedding; E3 owns the
``chunks.qdrant_point_id`` write-back.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from qdrant_client import models as qmodels

from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.services.storage import StorageService, get_storage
from app.utils.retry import with_backoff

#: Points per upsert call — Qdrant handles thousands, this keeps retries fine-grained.
UPSERT_BATCH_SIZE = 128


def point_id_for(doc_version_id: str, chunk_index: int) -> str:
    """Deterministic point ID: uuid5 over namespace + version + index (E2 step 3)."""
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"ragims:chunk:{doc_version_id}:{chunk_index}")
    )


def build_payload(doc: Document, version: DocumentVersion, chunk: Chunk) -> dict:
    """Retrieval payload (E2 step 2) — mirrors the ``chunks`` row."""
    return {
        "tenant_id": doc.tenant_id,
        "doc_id": doc.id,
        "doc_version_id": version.id,
        "version": version.version,
        "is_latest": True,
        "is_deleted": False,
        "access_level": doc.access_level,
        "chunk_index": chunk.chunk_index,
        "page": chunk.page,
        "chunk_hash": chunk.chunk_hash,
        "text": chunk.text,
    }


def build_point(
    doc: Document, version: DocumentVersion, chunk: Chunk, vector: list[float]
) -> qmodels.PointStruct:
    return qmodels.PointStruct(
        id=point_id_for(version.id, chunk.chunk_index),
        vector=vector,
        payload=build_payload(doc, version, chunk),
    )


def _is_transient(exc: BaseException) -> bool:
    """Retry network/timeout errors; validation errors are permanent."""
    return not isinstance(exc, (ValueError, TypeError, KeyError))


def upsert_doc_vectors(
    doc: Document,
    version: DocumentVersion,
    chunks: list[Chunk],
    vectors: list[list[float]],
    *,
    storage: StorageService | None = None,
    batch_size: int = UPSERT_BATCH_SIZE,
    retry_when: Callable[[BaseException], bool] | None = None,
) -> list[str]:
    """Ensure the collection, upsert points in batches, return point IDs (E2 step 4).

    Retry policy mirrors E1: transient failures back off exponentially, the
    last exception propagates. Point count must match chunk count exactly.
    """
    if len(chunks) != len(vectors):
        raise ValueError(
            f"chunks/vectors mismatch: {len(chunks)} chunks vs {len(vectors)} vectors"
        )
    if not chunks:
        return []

    storage = storage or get_storage()
    storage.ensure_vector_collection(dimension=len(vectors[0]))

    points = [
        build_point(doc, version, chunk, vector)
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    predicate = retry_when or _is_transient
    for start in range(0, len(points), batch_size):

        def upsert_batch(
            batch: list[qmodels.PointStruct] = points[start : start + batch_size],
        ) -> None:
            storage.upsert_points(batch)

        with_backoff(upsert_batch, retry_when=predicate)
    return [str(p.id) for p in points]
