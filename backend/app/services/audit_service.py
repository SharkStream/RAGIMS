"""Audit-log service (K1): write-path recording + paged tenant-scoped queries.

Recording is best-effort by design: an audit failure must never block the
business operation it observes (log + swallow). Reads are strict — always
tenant-scoped, newest first, riding the ``(tenant_id, created_at)`` index.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.models.audit_log import AuditLog

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

#: Known actions (documents.write-path set for MVP3; auth lands in K2).
ACTIONS_DOC_UPLOAD = "doc.upload"
ACTIONS_DOC_META_PATCH = "doc.meta_patch"
ACTIONS_DOC_ACTIVATE = "doc.activate"
ACTIONS_DOC_VERSION_DELETE = "doc.version_delete"
ACTIONS_DOC_SOFT_DELETE = "doc.soft_delete"
ACTIONS_DOC_REPROCESS = "doc.reprocess"


def record_audit(
    session: Session,
    *,
    tenant_id: str,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """Append one audit row; never raises (audit must not block business)."""
    try:
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                detail=detail,
            )
        )
        session.commit()
    except Exception as exc:  # noqa: BLE001 — best-effort by design
        session.rollback()
        logger.warning(f"audit record failed: {type(exc).__name__}: {exc}")


def list_audit_logs(
    session: Session,
    tenant_id: str,
    *,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AuditLog], int]:
    """Tenant-scoped, newest-first paged audit entries."""
    stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    count_stmt = (
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
    )
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
        count_stmt = count_stmt.where(AuditLog.action == action)
    if resource_type is not None:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
        count_stmt = count_stmt.where(AuditLog.resource_type == resource_type)
    if resource_id is not None:
        stmt = stmt.where(AuditLog.resource_id == resource_id)
        count_stmt = count_stmt.where(AuditLog.resource_id == resource_id)

    total = session.scalar(count_stmt) or 0
    rows = session.scalars(
        stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), int(total)
