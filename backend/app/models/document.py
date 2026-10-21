"""Document model — top-level document metadata with soft delete."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import CHAR, JSON, ForeignKeyConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import MYSQL_TABLE_KWARGS, Base, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.models.datasource import Datasource
    from app.models.document_version import DocumentVersion
    from app.models.ingestion_job import IngestionJob
    from app.models.tenant import Tenant


class Document(UUIDPkMixin, TimestampMixin, Base):
    """文档主表（软删除：``status='deleted'``；检索强制 ``tenant_id`` 过滤）。"""

    __tablename__ = "documents"
    __table_args__ = (
        Index("idx_documents_tenant_status", "tenant_id", "status"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_documents_tenant",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["datasource_id"],
            ["datasources.id"],
            name="fk_documents_datasource",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        {**MYSQL_TABLE_KWARGS},
    )

    tenant_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    datasource_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(512))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024))
    author: Mapped[str | None] = mapped_column(String(128))
    department: Mapped[str | None] = mapped_column(String(128))
    document_type: Mapped[str | None] = mapped_column(String(64))
    access_level: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="internal"
    )
    tags: Mapped[list[Any] | None] = mapped_column(JSON)
    current_version: Mapped[int] = mapped_column(nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="processing"
    )

    tenant: Mapped[Tenant] = relationship(back_populates="documents")
    datasource: Mapped[Datasource] = relationship(back_populates="documents")
    versions: Mapped[list[DocumentVersion]] = relationship(back_populates="doc")
    jobs: Mapped[list[IngestionJob]] = relationship(back_populates="doc")
