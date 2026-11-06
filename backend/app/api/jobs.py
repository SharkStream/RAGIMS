"""Job API routes (G1): list, detail, steps, retry, cancel.

Read-only queries ride the ``ingestion_jobs(tenant_id, status)`` index and
feed the H3 job board. Retry creates a NEW job via :mod:`app.services.
job_service`; cancel is the F3 cooperative flag in document_service.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user, get_db
from app.core.permissions import require_writer
from app.schemas.common import ApiResponse, PageResult, ok
from app.schemas.document import JobCancelResponse
from app.schemas.job import JobOut, JobRetryResponse, JobStepOut
from app.services.document_service import cancel_job
from app.services.job_service import (
    get_job_or_404,
    get_job_steps,
    list_jobs,
    retry_job,
)

if TYPE_CHECKING:
    from app.models.ingestion_job import IngestionJob
    from app.models.job_step import JobStep

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _to_job_out(session: Session, job: IngestionJob) -> JobOut:
    return JobOut(
        id=str(job.id),
        doc_id=str(job.doc_id) if job.doc_id else None,
        doc_version_id=str(job.doc_version_id) if job.doc_version_id else None,
        job_type=str(job.job_type),
        status=str(job.status),
        priority=int(job.priority),
        celery_task_id=job.celery_task_id,
        error_message=job.error_message,
        created_by=job.created_by,
        created_at=_dt(job.created_at),
        updated_at=_dt(job.updated_at),
        started_at=_dt(job.started_at),
        finished_at=_dt(job.finished_at),
    )


def _dt(value: object) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _to_step_out(step: JobStep) -> JobStepOut:
    duration = None
    if step.started_at is not None and step.finished_at is not None:
        duration = int((step.finished_at - step.started_at).total_seconds() * 1000)
    return JobStepOut(
        step_order=int(step.step_order),
        step_name=str(step.step_name),
        status=str(step.status),
        retry_count=int(step.retry_count),
        input=step.input,
        output=step.output,
        error_message=step.error_message,
        started_at=_dt(step.started_at),
        finished_at=_dt(step.finished_at),
        duration_ms=duration,
    )


@router.get(
    "",
    response_model=ApiResponse[PageResult[JobOut]],
    summary="Paged job list (filters: status / job_type / doc_id)",
)
def list_jobs_endpoint(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    status: Annotated[
        str | None,
        Query(description="pending/running/succeeded/failed/cancelled"),
    ] = None,
    job_type: Annotated[str | None, Query(description="full/reprocess/retry")] = None,
    doc_id: Annotated[str | None, Query(description="filter by document")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ApiResponse[PageResult[JobOut]]:
    rows, total = list_jobs(
        db,
        user.tenant_id,
        status=status,
        job_type=job_type,
        doc_id=doc_id,
        page=page,
        page_size=page_size,
    )
    items = [_to_job_out(db, j) for j in rows]
    return ok(PageResult.of(items, total=total, page=page, page_size=page_size))


@router.get(
    "/{job_id}",
    response_model=ApiResponse[JobOut],
    summary="Job detail",
)
def get_job(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[JobOut]:
    job = get_job_or_404(db, user.tenant_id, job_id)
    return ok(_to_job_out(db, job))


@router.get(
    "/{job_id}/steps",
    response_model=ApiResponse[PageResult[JobStepOut]],
    summary="Steps of a job, ordered by step_order (timing/status/errors)",
)
def get_steps(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[PageResult[JobStepOut]]:
    rows = get_job_steps(db, user.tenant_id, job_id)
    items = [_to_step_out(s) for s in rows]
    return ok(
        PageResult.of(items, total=len(items), page=1, page_size=max(len(items), 1))
    )


@router.post(
    "/{job_id}/retry",
    response_model=ApiResponse[JobRetryResponse],
    summary="Re-dispatch a failed job as a NEW job row",
    status_code=201,
)
def retry(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_writer)],
) -> ApiResponse[JobRetryResponse]:
    new_job = retry_job(db, user.tenant_id, job_id, user_id=user.id)
    return ok(
        JobRetryResponse(
            job_id=str(new_job.id),
            status=str(new_job.status),
            retried_job_id=job_id,
        )
    )


@router.post(
    "/{job_id}/cancel",
    response_model=ApiResponse[JobCancelResponse],
    summary="Cooperatively cancel a pending/running job",
)
def cancel(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_writer)],
) -> ApiResponse[JobCancelResponse]:
    job = cancel_job(db, user.tenant_id, job_id)
    return ok(JobCancelResponse(job_id=str(job.id), status=str(job.status)))
