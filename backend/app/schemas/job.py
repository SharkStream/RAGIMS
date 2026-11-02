"""Job-related API schemas (G1: list / detail / steps / retry)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class JobOut(BaseModel):
    """Row of ``GET /jobs`` and payload of ``GET /jobs/{id}``."""

    id: str = Field(description="ingestion_jobs.id (UUID string)")
    doc_id: str | None = None
    doc_version_id: str | None = None
    job_type: str = Field(description="full / reprocess / retry")
    status: str = Field(description="pending/running/succeeded/failed/cancelled")
    priority: int = 5
    celery_task_id: str | None = None
    error_message: str | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobStepOut(BaseModel):
    """Row of ``GET /jobs/{id}/steps`` (ordered by step_order)."""

    step_order: int
    step_name: str
    status: str = Field(description="running/succeeded/failed")
    retry_count: int = 0
    input: dict | None = None
    output: dict | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = Field(
        default=None,
        description="finished_at - started_at in milliseconds; None while running",
    )


class JobRetryResponse(BaseModel):
    """Payload of ``POST /jobs/{id}/retry`` (a NEW job row was dispatched)."""

    job_id: str = Field(description="id of the new retry job")
    status: str = Field(description="new job status (always 'pending')")
    retried_job_id: str = Field(description="id of the failed job being retried")
