"""Tenant model — MVP ships exactly one preset default tenant."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import MYSQL_TABLE_KWARGS, Base, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.models.datasource import Datasource
    from app.models.document import Document
    from app.models.user import User


class Tenant(UUIDPkMixin, TimestampMixin, Base):
    """租户（MVP 仅预置一条默认租户，见 scripts/seed.py）。"""

    __tablename__ = "tenants"
    __table_args__ = {**MYSQL_TABLE_KWARGS}

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="active"
    )

    users: Mapped[list[User]] = relationship(back_populates="tenant")
    datasources: Mapped[list[Datasource]] = relationship(back_populates="tenant")
    documents: Mapped[list[Document]] = relationship(back_populates="tenant")
