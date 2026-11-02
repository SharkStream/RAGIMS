"""Stats API (G3): minimal dashboard aggregates."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user, get_db
from app.schemas.common import ApiResponse, ok
from app.schemas.stats import StatsResponse
from app.services.stats_service import collect_stats

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get(
    "",
    response_model=ApiResponse[StatsResponse],
    summary="Dashboard aggregates (documents / chunks / job success / today)",
)
def get_stats(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[StatsResponse]:
    result = collect_stats(db, user.tenant_id)
    return ok(
        StatsResponse(
            total_documents=result.total_documents,
            total_chunks=result.total_chunks,
            total_jobs=result.total_jobs,
            succeeded_jobs=result.succeeded_jobs,
            failed_jobs=result.failed_jobs,
            processed_today=result.processed_today,
            success_rate=result.success_rate,
        )
    )
