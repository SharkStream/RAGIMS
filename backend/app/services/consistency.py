"""Consistency service (E4): idempotent re-processing + point-id repair.

Two guarantees on top of E2/E3:

1. :func:`purge_version_points` deletes a version's points before a
   re-upsert, so a re-processing run whose chunk count changed never
   leaves stale points behind (delete-before-upsert beats pure overwrite
   for the shrink case).
2. :func:`repair_missing_point_ids` reconciles ``chunks`` rows with a NULL
   ``qdrant_point_id``: if the deterministic point already lives in
   Qdrant (matched via payload ``chunk_index``), the ID is filled back at
   zero cost; otherwise the chunk is re-embedded and re-upserted.

Both are safe to run repeatedly — every step is idempotent (E2/E3).
"""

from __future__ import annotations

from qdrant_client import models as qmodels
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.embedder import get_default_embedder
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.services.storage import StorageService, get_storage
from app.services.vectoring_service import point_id_for, upsert_doc_vectors


def version_filter(doc_version_id: str) -> qmodels.Filter:
    """Filter selecting every point of one doc version."""
    return qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="doc_version_id", match=qmodels.MatchValue(value=doc_version_id)
            )
        ]
    )


def purge_version_points(
    doc_version_id: str, *, storage: StorageService | None = None
) -> int:
    """Delete all points of a doc version; return the pre-delete count (E4 step 1)."""
    storage = storage or get_storage()
    return storage.delete_points_by_filter(version_filter(doc_version_id))


def find_missing_point_ids(session: Session) -> list[Chunk]:
    """Chunks whose ``qdrant_point_id`` is still NULL (reconcile scan)."""
    return list(
        session.scalars(select(Chunk).where(Chunk.qdrant_point_id.is_(None))).all()
    )


def repair_missing_point_ids(
    session: Session, *, storage: StorageService | None = None, batch_size: int = 500
) -> dict[str, int]:
    """Repair chunks missing ``qdrant_point_id`` (E4 step 2, MVP reconciliation).

    Per affected doc version: fetch the version's points from Qdrant once
    (filter-only search with a dummy vector), then for each missing row
    either back-fill the existing point ID (payload ``chunk_index`` match)
    or re-embed + re-upsert the chunk. Returns a counts report.
    """
    storage = storage or get_storage()
    report = {"backfilled": 0, "reembedded": 0}
    missing = find_missing_point_ids(session)
    if not missing:
        return report

    # the search must match the collection dim — read it from the model config
    dim = get_default_embedder(session).dimension
    dummy = [0.0] * dim

    by_version: dict[str, list[Chunk]] = {}
    for row in missing:
        by_version.setdefault(row.doc_version_id, []).append(row)

    for version_id, rows in by_version.items():
        # existing points for this version, if any: chunk_index -> point_id
        try:
            hits = storage.search_vectors(
                dummy, query_filter=version_filter(version_id), top_k=batch_size
            )
        except Exception:  # noqa: BLE001 — collection may not exist yet
            hits = []
        known = {h.payload.get("chunk_index"): str(h.id) for h in hits if h.payload}

        doc = session.get(Document, rows[0].doc_id)
        version = session.get(DocumentVersion, version_id)
        if doc is None or version is None:
            raise LookupError(
                f"chunk rows reference missing doc/version: {rows[0].doc_id}/{version_id}"
            )
        to_embed: list[Chunk] = []
        for row in rows:
            point_id = known.get(row.chunk_index)
            if point_id:
                row.qdrant_point_id = point_id
                report["backfilled"] += 1
            else:
                to_embed.append(row)
        if to_embed:
            embedder = get_default_embedder(session)
            vectors, _ = embedder.embed_with_usage([r.text for r in to_embed])
            ids = upsert_doc_vectors(doc, version, to_embed, vectors, storage=storage)
            for row, point_id in zip(to_embed, ids, strict=True):
                row.qdrant_point_id = point_id or point_id_for(
                    version_id, row.chunk_index
                )
            report["reembedded"] += len(to_embed)
        session.commit()
    return report
