"""Audit-log API routes (K1): paged, tenant-scoped write-path history."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user, get_db
from app.schemas.audit import AuditLogOut
from app.schemas.common import ApiResponse, PageResult, ok
from app.services.audit_service import list_audit_logs

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get(
    "",
    response_model=ApiResponse[PageResult[AuditLogOut]],
    summary="Paged audit logs (filters: action / resource_type / resource_id)",
)
def list_audit_logs_endpoint(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    action: Annotated[str | None, Query(description="e.g. doc.upload")] = None,
    resource_type: Annotated[str | None, Query(description="e.g. document")] = None,
    resource_id: Annotated[str | None, Query(description="filter by resource")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ApiResponse[PageResult[AuditLogOut]]:
    """Newest first; tenant scope is taken from the authenticated user only."""
    rows, total = list_audit_logs(
        db,
        user.tenant_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        page=page,
        page_size=page_size,
    )
    items = [
        AuditLogOut(
            id=str(r.id),
            tenant_id=str(r.tenant_id),
            user_id=str(r.user_id),
            action=str(r.action),
            resource_type=str(r.resource_type),
            resource_id=str(r.resource_id),
            detail=r.detail,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return ok(PageResult.of(items, total=total, page=page, page_size=page_size))
