"""Job query/retry service (G1).

Read side rides the ``ingestion_jobs(tenant_id, status)`` index; steps are
ordered by ``step_order``. Retry creates a NEW job row (full audit history
preserved) and dispatches it through the same F2 pipeline entrypoint.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.core.logging import logger
from app.models.ingestion_job import IngestionJob
from app.models.job_step import JobStep
from app.services.document_service import _dispatch_ingestion

_RETRYABLE = ("failed",)


def list_jobs(
    session: Session,
    tenant_id: str,
    *,
    status: str | None = None,
    job_type: str | None = None,
    doc_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[IngestionJob], int]:
    """Paged jobs, newest first; optional status/job_type/doc_id filters."""
    conds: list[Any] = [IngestionJob.tenant_id == tenant_id]
    if status:
        conds.append(IngestionJob.status == status)
    if job_type:
        conds.append(IngestionJob.job_type == job_type)
    if doc_id:
        conds.append(IngestionJob.doc_id == doc_id)
    base = select(IngestionJob).where(*conds)
    total = session.scalar(select(func.count()).select_from(IngestionJob).where(*conds))
    rows = session.scalars(
        base.order_by(IngestionJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), int(total or 0)


def get_job_or_404(session: Session, tenant_id: str, job_id: str) -> IngestionJob:
    job = session.get(IngestionJob, job_id)
    if job is None or job.tenant_id != tenant_id:
        raise NotFoundError(f"job {job_id} not found")
    return job


def get_job_steps(session: Session, tenant_id: str, job_id: str) -> list[JobStep]:
    """Steps of a job ordered by step_order (404-scoped on the job)."""
    get_job_or_404(session, tenant_id, job_id)
    rows = session.scalars(
        select(JobStep).where(JobStep.job_id == job_id).order_by(JobStep.step_order)
    ).all()
    return list(rows)


def retry_job(
    session: Session, tenant_id: str, job_id: str, *, user_id: str | None = None
) -> IngestionJob:
    """Re-dispatch a failed job as a NEW row (audit trail preserved).

    Only ``failed`` jobs can be retried; anything else is a 409. The new job
    reuses the original doc_version_id so the idempotent pipeline re-runs it.
    """
    job = get_job_or_404(session, tenant_id, job_id)
    if job.status not in _RETRYABLE:
        raise AppError(
            f"job {job_id} is {job.status} and cannot be retried",
            code="ERR_CONFLICT",
            status_code=409,
            details={"job_id": job_id, "status": job.status},
        )
    if job.doc_version_id is None:
        raise AppError(
            f"job {job_id} has no doc_version_id to re-run",
            code="ERR_CONFLICT",
            status_code=409,
        )
    new_job = IngestionJob(
        tenant_id=tenant_id,
        doc_id=job.doc_id,
        doc_version_id=job.doc_version_id,
        job_type=job.job_type,
        status="pending",
        created_by=user_id,
    )
    session.add(new_job)
    session.commit()

    celery_task_id = _dispatch_ingestion(str(job.doc_version_id))
    if celery_task_id:
        new_job.celery_task_id = celery_task_id
        session.commit()
    logger.info(
        f"job retried: {job_id} -> {new_job.id} (task={celery_task_id or 'n/a'})"
    )
    return new_job
