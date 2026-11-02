"""Minimal dashboard statistics (G3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.document import Document
from app.models.ingestion_job import IngestionJob


@dataclass
class StatsResult:
    total_documents: int
    total_chunks: int
    total_jobs: int
    succeeded_jobs: int
    failed_jobs: int
    processed_today: int
    success_rate: float | None  # None when no terminal job yet


def collect_stats(session: Session, tenant_id: str) -> StatsResult:
    """Aggregate per-tenant counts; jobs ride the ``(tenant_id,status)`` index."""
    total_documents = int(
        session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.tenant_id == tenant_id, Document.status != "deleted")
        )
        or 0
    )
    total_chunks = int(
        session.scalar(
            select(func.count())
            .select_from(Chunk)
            .join(Document, Chunk.doc_id == Document.id)
            .where(Document.tenant_id == tenant_id)
        )
        or 0
    )
    total_jobs = int(
        session.scalar(
            select(func.count())
            .select_from(IngestionJob)
            .where(IngestionJob.tenant_id == tenant_id)
        )
        or 0
    )
    succeeded_jobs = int(
        session.scalar(
            select(func.count())
            .select_from(IngestionJob)
            .where(
                IngestionJob.tenant_id == tenant_id, IngestionJob.status == "succeeded"
            )
        )
        or 0
    )
    failed_jobs = int(
        session.scalar(
            select(func.count())
            .select_from(IngestionJob)
            .where(IngestionJob.tenant_id == tenant_id, IngestionJob.status == "failed")
        )
        or 0
    )
    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    processed_today = int(
        session.scalar(
            select(func.count())
            .select_from(IngestionJob)
            .where(
                IngestionJob.tenant_id == tenant_id,
                IngestionJob.created_at >= day_start,
            )
        )
        or 0
    )

    terminal = succeeded_jobs + failed_jobs
    success_rate = (succeeded_jobs / terminal) if terminal else None
    return StatsResult(
        total_documents=total_documents,
        total_chunks=total_chunks,
        total_jobs=total_jobs,
        succeeded_jobs=succeeded_jobs,
        failed_jobs=failed_jobs,
        processed_today=processed_today,
        success_rate=success_rate,
    )
