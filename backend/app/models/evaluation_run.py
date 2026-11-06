"""Evaluation-run model (L1) — one retrieval-quality benchmark invocation.

``dataset`` stores the input pairs (query + expected doc_ids); ``metrics``
the computed aggregates (recall@k / MRR / nDCG@k); ``result`` the per-query
breakdown for the report view and manual review (L3/L4). Tenant hard-isolated.
"""

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


class EvaluationRun(UUIDPkMixin, Base):
    """评估运行（plan.md 4.8）——一次基准测试的输入/指标/逐条结果。

    无 updated_at：运行创建后指标不可变，重跑即新建一行（可对比历史趋势）。
    查询走 ``(tenant_id, created_at)`` 复合索引倒序。
    """

    __tablename__ = "evaluation_runs"
    __table_args__ = (
        Index("idx_evaluation_runs_tenant_created", "tenant_id", "created_at"),
        {**MYSQL_TABLE_KWARGS},
    )

    tenant_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    user_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    #: Rerun lineage (L4.1): id of the run this one was derived from.
    #: Soft pointer on purpose — no FK, so runs can be cleaned up freely.
    parent_run_id: Mapped[str | None] = mapped_column(CHAR(36))
    dataset: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime3,
        nullable=False,
        default=utcnow_ms,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )
