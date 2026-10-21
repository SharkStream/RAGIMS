"""Chunk model — immutable per-version chunks; only ``created_at`` (B1 §3.7)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CHAR, JSON, ForeignKeyConstraint, Index, Integer, String
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    MYSQL_TABLE_KWARGS,
    Base,
    DateTime3,
    MediumText,
    UUIDPkMixin,
    utcnow_ms,
)

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.document_version import DocumentVersion


class Chunk(UUIDPkMixin, Base):
    """Chunk 元数据（行不可变，重摄入产生新版本；无 updated_at）。

    Note:
        ``metadata`` is reserved by SQLAlchemy's Declarative API, so the Python
        attribute is ``meta`` while the column keeps its B1 name ``metadata``.
    """

    __tablename__ = "chunks"
    __table_args__ = (
        Index("idx_chunks_version_index", "doc_version_id", "chunk_index"),
        Index("idx_chunks_doc_id", "doc_id"),
        ForeignKeyConstraint(
            ["doc_version_id"],
            ["document_versions.id"],
            name="fk_chunks_doc_version",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["doc_id"],
            ["documents.id"],
            name="fk_chunks_doc",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        {**MYSQL_TABLE_KWARGS},
    )

    doc_version_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    doc_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(MediumText, nullable=False)
    token_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    chunk_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    page: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(255))
    qdrant_point_id: Mapped[str | None] = mapped_column(CHAR(36))
    meta: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime3,
        nullable=False,
        default=utcnow_ms,
        server_default=sql_text("CURRENT_TIMESTAMP(3)"),
    )

    doc_version: Mapped[DocumentVersion] = relationship(back_populates="chunks")
    doc: Mapped[Document] = relationship()
