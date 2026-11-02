"""Ingestion pipeline (F2): parse -> clean -> chunk -> persist -> embed ->
upsert -> write back -> finalize, orchestrated as recorded steps.

Every stage runs inside :func:`app.workers.base.record_step`, so each
attempt lands in ``job_steps`` (order, timing, output/error) and failures
flip the parent job to ``failed``. The task autoretries transient
failures (Celery exponential backoff, max 3) — safe because every stage
is idempotent by construction:

- parse overwrites the parsed-text object (same key)
- insert_chunks reuses existing (doc_version_id, chunk_index) rows
- upsert writes the same deterministic point IDs (E2)
- write_back is a plain UPDATE (E3)

Cross-stage results stay in-process (single Celery task), no broker
round-trips; the chain names below map 1:1 onto ``job_steps.step_name``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chunkers.fixed_token_chunker import FixedTokenChunker
from app.clients.embedder import get_default_embedder
from app.core.db import SessionLocal
from app.core.logging import logger
from app.models.ingestion_job import IngestionJob
from app.services.chunk_store import (
    finalize_version,
    insert_chunks,
    write_back_point_ids,
)
from app.services.cleaning import clean
from app.services.parsing_service import parse_and_store
from app.services.storage import get_storage
from app.services.vectoring_service import upsert_doc_vectors
from app.workers.base import (
    PipelineCancelledError,
    finish_job,
    record_step,
)
from app.workers.celery_app import celery_app


def _in_session(
    session_factory: Callable[[], Session],
    fn: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Run ``fn(session, *args, **kwargs)`` inside a managed session."""
    with session_factory() as session:
        return fn(session, *args, **kwargs)


def _job_id_for(session_factory: Callable[[], Session], doc_version_id: str) -> str:
    with session_factory() as session:
        job = session.scalars(
            select(IngestionJob)
            .where(IngestionJob.doc_version_id == doc_version_id)
            .order_by(IngestionJob.created_at.desc())
            .limit(1)
        ).first()
        if job is None:
            raise LookupError(f"no ingestion_jobs row for version {doc_version_id}")
        return str(job.id)


def _persist(
    session_factory: Callable[[], Session], doc_version_id: str, chunk_dtos: list
) -> tuple:
    """Insert chunk rows + load doc/version rows (persist_chunks step body)."""
    from app.models.document import Document
    from app.models.document_version import DocumentVersion

    with session_factory() as session:
        version = session.get(DocumentVersion, doc_version_id)
        if version is None:
            raise LookupError(f"unknown doc_version {doc_version_id}")
        doc = session.get(Document, str(version.doc_id))
        if doc is None:
            raise LookupError(f"missing document row {version.doc_id}")
        rows = list(insert_chunks(session, doc, version, chunk_dtos))
        session.expunge_all()  # detach: later steps re-read these read-only rows
    return doc, version, rows


def run_pipeline(
    doc_version_id: str,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    embedder: Any = None,
    storage: Any = None,
) -> dict:
    """Execute the full stage chain for one doc version; return a summary."""
    job_id = _job_id_for(session_factory, doc_version_id)
    storage = storage or get_storage()

    with record_step(
        job_id,
        "parse",
        lambda: _in_session(session_factory, parse_and_store, doc_version_id),
        input={"doc_version_id": doc_version_id},
        session_factory=session_factory,
    ) as parsed:
        pass

    with record_step(
        job_id,
        "clean",
        lambda: clean(parsed),
        session_factory=session_factory,
    ) as cleaned:
        pass

    with record_step(
        job_id,
        "chunk",
        lambda: FixedTokenChunker().chunk(cleaned),
        session_factory=session_factory,
    ) as chunk_dtos:
        pass

    with record_step(
        job_id,
        "persist_chunks",
        lambda: _persist(session_factory, doc_version_id, chunk_dtos),
        session_factory=session_factory,
    ) as persisted:
        doc, version, rows = persisted

    if embedder is None:
        with session_factory() as session:
            embedder = get_default_embedder(session)
    with record_step(
        job_id,
        "embed",
        lambda: embedder.embed_with_usage([r.text for r in rows]),
        session_factory=session_factory,
    ) as embedded:
        vectors, usage = embedded

    with record_step(
        job_id,
        "upsert",
        lambda: upsert_doc_vectors(doc, version, rows, vectors, storage=storage),
        session_factory=session_factory,
    ) as point_ids:
        pass

    with record_step(
        job_id,
        "write_back",
        lambda: (
            _in_session(session_factory, write_back_point_ids, rows, point_ids),
            {"backfilled": len(point_ids)},
        )[1],
        session_factory=session_factory,
    ):
        pass

    _in_session(
        session_factory,
        finalize_version,
        version,
        embedding_model=embedder.model_name,
        chunk_count=len(rows),
    )
    finish_job(job_id, session_factory=session_factory)
    logger.info(
        f"[pipeline] job {job_id} done: {len(rows)} chunks, {usage.token_count} tokens"
    )
    return {
        "job_id": job_id,
        "chunk_count": len(rows),
        "token_count": usage.token_count,
    }


@celery_app.task(
    name="ragims.ingest_document",
    bind=True,
    autoretry_for=(Exception,),
    dont_autoretry_for=(PipelineCancelledError,),
    retry_backoff=2,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def ingest_document(self: Any, doc_version_id: str) -> dict:  # noqa: ANN001
    """Chain entrypoint: full pipeline with Celery-level exponential retry.

    A cancelled job ends the run quietly (no retry): the job keeps its
    ``cancelled`` status set by the cancel endpoint.
    """
    logger.info(
        f"[celery] ingest_document attempt {self.request.retries + 1}: {doc_version_id}"
    )
    try:
        return run_pipeline(doc_version_id)
    except PipelineCancelledError as exc:
        logger.info(f"[celery] pipeline cancelled: {exc}")
        return {"status": "cancelled"}
