"""Embedding model configuration — global registry, no tenant scoping in MVP."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import CHAR, JSON, Boolean, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import MYSQL_TABLE_KWARGS, Base


class EmbeddingModel(Base):
    """Embedding 模型配置（种子写入一条默认配置；无 created_at/updated_at，沿用 plan.md §4.6）。

    与其他模型同样使用 ``CHAR(36)`` UUID 主键，但不继承 ``UUIDPkMixin``——
    该 mixin 仅为 ``Declarative`` 基类预留（基类自身无主键），此表直接声明。
    """

    __tablename__ = "embedding_models"
    __table_args__ = (
        UniqueConstraint(
            "provider", "model_name", name="uq_embedding_models_provider_model"
        ),
        {**MYSQL_TABLE_KWARGS},
    )

    id: Mapped[str] = mapped_column(
        CHAR(36), primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    dimension: Mapped[int] = mapped_column(nullable=False)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0")
    )
