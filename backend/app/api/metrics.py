"""Prometheus metrics endpoint (M1).

``GET /api/metrics`` serves the standard text exposition format so any
Prometheus instance can scrape it. Deliberately **unauthenticated** (the
Prometheus convention): it contains only aggregate counters/gauges — no
business payloads. DB-derived gauges are computed per scrape.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.metrics import render_http_metrics
from app.models import (
    Chunk,
    Document,
    DocumentVersion,
    EvaluationRun,
    IngestionJob,
    JobStep,
    QualityCheck,
    User,
)

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _db_lines(session: Session) -> list[str]:
    """Gauges derived from the metadata DB at scrape time."""
    lines: list[str] = []

    def gauge(name: str, help_text: str, value: float, labels: str = "") -> None:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name}{labels} {value}")

    def count(model: type) -> int:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)

    # per-status document gauges
    for status, n in session.execute(
        select(Document.status, func.count()).group_by(Document.status)
    ).all():
        gauge(
            "ragims_documents_total",
            "Documents by status.",
            int(n),
            f'{{status="{status}"}}',
        )

    gauge(
        "ragims_document_versions_total", "Document versions.", count(DocumentVersion)
    )
    gauge("ragims_chunks_total", "Chunks.", count(Chunk))
    gauge("ragims_quality_check_rows_total", "Quality check rows.", count(QualityCheck))
    gauge("ragims_evaluation_runs_total", "Evaluation runs.", count(EvaluationRun))
    gauge("ragims_users_total", "User accounts.", count(User))

    jobs_by_status = session.execute(
        select(IngestionJob.status, func.count()).group_by(IngestionJob.status)
    ).all()
    total_jobs = 0
    for status, n in jobs_by_status:
        total_jobs += int(n)
        gauge(
            "ragims_jobs_total",
            "Ingestion jobs by status.",
            int(n),
            f'{{status="{status}"}}',
        )
    gauge("ragims_jobs_total", "Ingestion jobs by status.", total_jobs)

    # queue depth: jobs still to be worked on
    pending = sum(
        int(n) for s, n in jobs_by_status if s in ("pending", "running", "retrying")
    )
    gauge("ragims_jobs_queue_depth", "Jobs pending or running.", pending)

    # embedding tokens consumed (cost basis, M2 uses the same source)
    tokens = (
        session.scalar(select(func.sum(JobStep.output["token_count"].as_integer())))
        or 0
    )
    gauge("ragims_embedding_tokens_total", "Embedding tokens consumed.", int(tokens))

    # average step duration from job_steps (started/finished both present)
    dur = session.execute(
        select(
            JobStep.step_name,
            func.avg(
                func.timestampdiff(
                    text("MICROSECOND"),
                    JobStep.started_at,
                    JobStep.finished_at,
                )
                / 1_000_000.0
            ),
        )
        .where(JobStep.started_at.is_not(None), JobStep.finished_at.is_not(None))
        .group_by(JobStep.step_name)
    ).all()
    for step_name, avg_seconds in dur:
        if avg_seconds is None:
            continue
        gauge(
            "ragims_job_step_duration_seconds_avg",
            "Average wall time per pipeline step.",
            round(float(avg_seconds), 4),
            f'{{step="{step_name}"}}',
        )
    return lines


@router.get(
    "",
    summary="Prometheus metrics (text exposition; unauthenticated by convention)",
    include_in_schema=True,
)
def metrics(db: Annotated[Session, Depends(get_db)]) -> Response:
    body = "\n".join([*render_http_metrics(), *_db_lines(db)]) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4")
