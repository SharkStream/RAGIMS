"""Audit log model (K1) — one row per write-path action, tenant-scoped."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CHAR, JSON, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    MYSQL_TABLE_KWARGS,
    Base,
    DateTime3,
    UUIDPkMixin,
    utcnow_ms,
)


class AuditLog(UUIDPkMixin, Base):
    """审计日志（plan.md 4.7，K1 落地）——写路径一行一动作，租户硬隔离。

    只增不改：无 updated_at；查询走 ``(tenant_id, created_at)`` 复合索引倒序。
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("idx_audit_logs_tenant_created", "tenant_id", "created_at"),
        {**MYSQL_TABLE_KWARGS},
    )

    tenant_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    user_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime3,
        nullable=False,
        default=utcnow_ms,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )
