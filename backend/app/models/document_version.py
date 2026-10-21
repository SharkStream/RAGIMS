"""Document version model — idempotency key ``(doc_id, content_hash)``."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    MYSQL_TABLE_KWARGS,
    Base,
    DateTime3,
    TimestampMixin,
    UUIDPkMixin,
)

if TYPE_CHECKING:
    from app.models.chunk import Chunk
    from app.models.document import Document


class DocumentVersion(UUIDPkMixin, TimestampMixin, Base):
    """文档版本（``UNIQUE(doc_id, content_hash)`` 幂等去重；行随版本推进）。"""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("doc_id", "content_hash", name="uq_doc_versions_doc_content"),
        ForeignKeyConstraint(
            ["doc_id"],
            ["documents.id"],
            name="fk_doc_versions_doc",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        {**MYSQL_TABLE_KWARGS},
    )

    doc_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    parse_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="pending"
    )
    chunk_count: Mapped[int] = mapped_column(nullable=False, server_default="0")
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    is_latest: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("1")
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0")
    )
    valid_from: Mapped[datetime | None] = mapped_column(DateTime3)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime3)

    doc: Mapped[Document] = relationship(back_populates="versions")
    chunks: Mapped[list[Chunk]] = relationship(back_populates="doc_version")
