"""User model — MVP seeds a single default admin per preset tenant."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CHAR, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import MYSQL_TABLE_KWARGS, Base, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class User(UUIDPkMixin, TimestampMixin, Base):
    """用户（MVP 无真实认证，路由使用预置默认管理员，阶段 3 替换）。"""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "username", name="uq_users_tenant_username"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_users_tenant",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        {**MYSQL_TABLE_KWARGS},
    )

    tenant_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="admin"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="active"
    )

    tenant: Mapped[Tenant] = relationship(back_populates="users")
