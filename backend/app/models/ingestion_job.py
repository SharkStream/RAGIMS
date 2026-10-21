"""Ingestion job model — Celery pipeline state machine root (F2)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CHAR, ForeignKeyConstraint, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    MYSQL_TABLE_KWARGS,
    Base,
    DateTime3,
    TimestampMixin,
    UUIDPkMixin,
)

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.document_version import DocumentVersion
    from app.models.job_step import JobStep
    from app.models.tenant import Tenant


class IngestionJob(UUIDPkMixin, TimestampMixin, Base):
    """摄取任务（状态机 ``pending→running→success/failed/cancelled``）。"""

    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        Index("idx_ingestion_jobs_tenant_status", "tenant_id", "status"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_jobs_tenant",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["doc_id"],
            ["documents.id"],
            name="fk_jobs_doc",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["doc_version_id"],
            ["document_versions.id"],
            name="fk_jobs_doc_version",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        {**MYSQL_TABLE_KWARGS},
    )

    tenant_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    doc_id: Mapped[str | None] = mapped_column(CHAR(36))
    doc_version_id: Mapped[str | None] = mapped_column(CHAR(36))
    job_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="full"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="pending"
    )
    priority: Mapped[int] = mapped_column(nullable=False, server_default="5")
    created_by: Mapped[str | None] = mapped_column(CHAR(36))
    celery_task_id: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime3)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime3)
    error_message: Mapped[str | None] = mapped_column(Text)

    tenant: Mapped[Tenant] = relationship()
    doc: Mapped[Document] = relationship(back_populates="jobs")
    doc_version: Mapped[DocumentVersion] = relationship()
    steps: Mapped[list[JobStep]] = relationship(back_populates="job")
