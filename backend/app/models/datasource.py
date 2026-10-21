"""Datasource model — MVP implements only ``type='local'`` uploads."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CHAR, JSON, ForeignKeyConstraint, String
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
    from app.models.tenant import Tenant


class Datasource(UUIDPkMixin, TimestampMixin, Base):
    """数据源（MVP 仅 local；cron/webhook 与外部源延后）。"""

    __tablename__ = "datasources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_datasources_tenant",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        {**MYSQL_TABLE_KWARGS},
    )

    tenant_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="local"
    )
    config: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    sync_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="manual"
    )
    sync_cron: Mapped[str | None] = mapped_column(String(64))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime3)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="active"
    )

    tenant: Mapped[Tenant] = relationship(back_populates="datasources")
    documents: Mapped[list[Document]] = relationship(back_populates="datasource")
