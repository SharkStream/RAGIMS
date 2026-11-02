"""Pipeline task base (F1): job_steps bookkeeping + job status transitions.

:func:`record_step` wraps one pipeline stage: it inserts a ``job_steps``
row (``running`` + ``started_at``), runs the callable, then records
``succeeded``/``failed`` with output or error message. A failing step
marks the parent job ``failed`` and re-raises so Celery sees the error.

Stages re-run safely by design (E-stage idempotency): each call creates a
new step row — the audit trail of every attempt, not a dedup ledger.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.logging import logger
from app.models.base import utcnow_ms
from app.models.ingestion_job import IngestionJob
from app.models.job_step import JobStep


class PipelineCancelledError(Exception):
    """Raised when a job was marked ``cancelled`` before a step started.

    Not a pipeline failure: the task wrapper swallows it (no Celery
    retry) and the job keeps its ``cancelled`` status.
    """


@contextmanager
def record_step(
    job_id: str,
    step_name: str,
    fn: Callable[[], Any],
    *,
    input: dict[str, Any] | None = None,  # noqa: A002 — mirrors job_steps.input
    session_factory: Callable[[], Session] = SessionLocal,
) -> Iterator[Any]:
    """Record a ``job_steps`` row around ``fn``; fail the job on exception.

    Yields the (fresh) session so the wrapped callable can persist its own
    artifacts with the same transaction scope.
    """
    with session_factory() as session:
        order = (
            session.scalar(
                select(JobStep.step_order)
                .where(JobStep.job_id == job_id)
                .order_by(JobStep.step_order.desc())
                .limit(1)
            )
            or 0
        ) + 1
        # cancel recognition (F3): a job marked cancelled must not start the
        # next step — raise before any step row touches the job.
        job_now = session.get(IngestionJob, job_id)
        if job_now is not None and job_now.status == "cancelled":
            raise PipelineCancelledError(
                f"job {job_id} cancelled before step {step_name}"
            )
        step = JobStep(
            id=str(uuid4()),
            job_id=job_id,
            step_order=order,
            step_name=step_name,
            status="running",
            input=input,
            started_at=utcnow_ms(),
        )
        session.add(step)
        _set_job_status(session, job_id, "running")
        session.commit()
        try:
            result = fn()
        except Exception as exc:
            step.status = "failed"
            step.error_message = f"{type(exc).__name__}: {exc}"[:60000]
            step.finished_at = utcnow_ms()
            _set_job_status(session, job_id, "failed", error=step.error_message)
            session.commit()
            logger.exception(f"[pipeline] step {step_name} failed for job {job_id}")
            raise
        step.status = "succeeded"
        step.output = _serialize(result)
        step.finished_at = utcnow_ms()
        session.commit()
        yield result
        logger.info(
            f"[pipeline] step {step_name} (#{order}) succeeded for job {job_id}"
        )


def finish_job(
    job_id: str, *, session_factory: Callable[[], Session] = SessionLocal
) -> None:
    """Mark the job ``succeeded`` after its last step passes."""
    with session_factory() as session:
        _set_job_status(session, job_id, "succeeded")
        session.commit()


def _set_job_status(
    session: Session, job_id: str, status: str, *, error: str | None = None
) -> None:
    job = session.get(IngestionJob, job_id)
    if job is None:
        return
    job.status = status
    if error is not None:
        job.error_message = error


def _serialize(result: Any) -> dict[str, Any] | None:
    """Best-effort JSON dict for ``job_steps.output``."""
    if result is None:
        return None
    if isinstance(result, dict):
        return result
    return {"result": str(result)[:2000]}
