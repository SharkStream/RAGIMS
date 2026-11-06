"""Quality-check model (L1) — pipeline output checks, one row per check type.

Rows are written by the worker (L2) right before finalize; scores feed the
quality dashboard (L4). Tenant comes via the joined document version's
document; queries are doc_version-scoped.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CHAR, JSON, Float, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    MYSQL_TABLE_KWARGS,
    Base,
    DateTime3,
    UUIDPkMixin,
    utcnow_ms,
)


class QualityCheck(UUIDPkMixin, Base):
    """质量检查结果（plan.md 4.8）——一行一个检查项，版本级留痕。

    check_type: empty_ratio / duplicate_ratio / length_spread（L2 内置三项，
    后续可扩 OCR 缺失、编码异常等）；score 归一到 [0,1]，detail 存原始计数。
    """

    __tablename__ = "quality_checks"
    __table_args__ = (
        Index("idx_quality_checks_doc_version", "doc_version_id", "check_type"),
        {**MYSQL_TABLE_KWARGS},
    )

    doc_version_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey(
            "document_versions.id", ondelete="CASCADE", name="fk_quality_checks_version"
        ),
        nullable=False,
    )
    check_type: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime3,
        nullable=False,
        default=utcnow_ms,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )
