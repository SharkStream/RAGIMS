"""Embedding cost statistics (M2).

``GET /stats/costs`` aggregates the token accounting that the pipeline writes
into the embed step's structured output (``job_steps.output.token_count``):

* grand total tokens + embed call count
* per-day breakdown (last N days, day = step finished_at date, UTC)

Read-only, any authenticated user, tenant-scoped via the ingestion job chain.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user, get_db
from app.models import IngestionJob, JobStep
from app.schemas.common import ApiResponse, ok

router = APIRouter(prefix="/stats", tags=["stats"])


def _token_expr() -> Any:
    return JobStep.output["token_count"].as_integer()


@router.get(
    "/costs",
    response_model=ApiResponse[dict[str, Any]],
    summary="Embedding token cost: grand total + per-day breakdown",
)
def cost_summary(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> ApiResponse[dict[str, Any]]:
    """Aggregates `job_steps.output.token_count` from embed steps."""
    embed_steps = (
        select(JobStep, IngestionJob.tenant_id)
        .join(IngestionJob, JobStep.job_id == IngestionJob.id)
        .where(
            JobStep.step_name == "embed",
            JobStep.status == "succeeded",
            IngestionJob.tenant_id == user.tenant_id,
        )
        .subquery()
    )
    token_col = embed_steps.c.output["token_count"].as_integer()

    total_tokens = db.scalar(select(func.sum(token_col)).select_from(embed_steps)) or 0
    embed_calls = db.scalar(select(func.count()).select_from(embed_steps)) or 0

    per_day = db.execute(
        select(
            func.date(embed_steps.c.finished_at).label("day"),
            func.sum(token_col).label("tokens"),
            func.count().label("calls"),
        )
        .select_from(embed_steps)
        .group_by(func.date(embed_steps.c.finished_at))
        .order_by(func.date(embed_steps.c.finished_at).desc())
        .limit(days)
    ).all()

    return ok(
        {
            "total_tokens": int(total_tokens),
            "embed_calls": int(embed_calls),
            "days": [
                {
                    "day": str(day),
                    "tokens": int(tokens or 0),
                    "embed_calls": int(calls),
                }
                for day, tokens, calls in per_day
            ],
        }
    )
