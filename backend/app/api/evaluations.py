"""Evaluation API routes (L3) — create/run, list history, read a report.

All routes are tenant-scoped via the authenticated user; creating a run is a
write path and is audited as ``eval.run`` (L3 extends the K1 action set).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user, get_db
from app.models.evaluation_run import EvaluationRun
from app.schemas.common import ApiResponse, PageResult, ok
from app.schemas.evaluation import (
    EvaluationCreateRequest,
    EvaluationRunOut,
    EvaluationSummary,
    ReviewRequest,
)
from app.services.audit_service import (
    ACTIONS_EVAL_REVIEW,
    ACTIONS_EVAL_RUN,
    record_audit,
)
from app.services.evaluation_service import create_and_run_evaluation

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


def _run_out(r: EvaluationRun) -> EvaluationRunOut:
    return EvaluationRunOut(
        id=str(r.id),
        name=str(r.name),
        parent_run_id=r.parent_run_id,
        dataset=list(r.dataset),
        metrics=r.metrics,
        result=r.result,
        created_at=r.created_at,
    )


@router.post(
    "",
    response_model=ApiResponse[EvaluationRunOut],
    status_code=201,
    summary="Create a benchmark and run it synchronously over the live index",
)
def create_evaluation(
    body: EvaluationCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[EvaluationRunOut]:
    """Runs every query through the real retrieval path and stores the report."""
    if body.parent_run_id is not None:
        parent = db.get(EvaluationRun, body.parent_run_id)
        if parent is None or str(parent.tenant_id) != user.tenant_id:
            from app.core.errors import AppError

            raise AppError(
                f"parent evaluation {body.parent_run_id} not found",
                code="ERR_NOT_FOUND",
                status_code=404,
            )
    run = create_and_run_evaluation(
        db,
        tenant_id=user.tenant_id,
        user_id=user.id,
        name=body.name,
        dataset=[item.model_dump() for item in body.dataset],
        top_k=body.top_k,
        parent_run_id=body.parent_run_id,
    )
    record_audit(
        db,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action=ACTIONS_EVAL_RUN,
        resource_type="evaluation_run",
        resource_id=str(run.id),
        detail={
            "name": body.name,
            "queries": len(body.dataset),
            "top_k": body.top_k,
            "recall@k": (run.metrics or {}).get("recall@k"),
            "parent_run_id": body.parent_run_id,
        },
    )
    return ok(_run_out(run))


@router.get(
    "",
    response_model=ApiResponse[PageResult[EvaluationSummary]],
    summary="Evaluation history for the tenant (newest first)",
)
def list_evaluations(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ApiResponse[PageResult[EvaluationSummary]]:
    stmt = select(EvaluationRun).where(EvaluationRun.tenant_id == user.tenant_id)
    count_stmt = (
        select(func.count())
        .select_from(EvaluationRun)
        .where(EvaluationRun.tenant_id == user.tenant_id)
    )
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(EvaluationRun.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        EvaluationSummary(
            id=str(r.id),
            name=str(r.name),
            parent_run_id=r.parent_run_id,
            queries=len(r.dataset) if r.dataset else None,
            metrics=r.metrics,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return ok(PageResult.of(items, total=int(total), page=page, page_size=page_size))


@router.get(
    "/{run_id}",
    response_model=ApiResponse[EvaluationRunOut],
    summary="One evaluation report (dataset + metrics + per-query results)",
)
def get_evaluation(
    run_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[EvaluationRunOut]:
    run = db.get(EvaluationRun, run_id)
    if run is None or str(run.tenant_id) != user.tenant_id:
        from app.core.errors import AppError

        raise AppError(
            f"evaluation {run_id} not found", code="ERR_NOT_FOUND", status_code=404
        )
    return ok(_run_out(run))


@router.patch(
    "/{run_id}/results/{index}",
    response_model=ApiResponse[EvaluationRunOut],
    summary="Manually review one query result (L4 human-in-the-loop)",
)
def review_result(
    run_id: str,
    index: int,
    body: ReviewRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[EvaluationRunOut]:
    """Attach a human verdict + note to one per-query row of the report."""
    run = db.get(EvaluationRun, run_id)
    if run is None or str(run.tenant_id) != user.tenant_id:
        from app.core.errors import AppError

        raise AppError(
            f"evaluation {run_id} not found", code="ERR_NOT_FOUND", status_code=404
        )
    if run.result is None or not 0 <= index < len(run.result):
        from app.core.errors import AppError

        raise AppError(
            f"result index {index} out of range",
            code="ERR_BAD_REQUEST",
            status_code=400,
        )
    row = dict(run.result[index])
    row["review"] = {"verdict": body.verdict, "note": body.note}
    run.result = [dict(r) if i != index else row for i, r in enumerate(run.result)]
    db.commit()
    record_audit(
        db,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action=ACTIONS_EVAL_REVIEW,
        resource_type="evaluation_run",
        resource_id=str(run.id),
        detail={"index": index, "verdict": body.verdict, "query": row.get("query")},
    )
    return ok(_run_out(run))
