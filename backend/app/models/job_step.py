"""Job step model — one row per pipeline step, ordered by ``step_order``."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CHAR, JSON, ForeignKeyConstraint, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import MYSQL_TABLE_KWARGS, Base, DateTime3, UUIDPkMixin

if TYPE_CHECKING:
    from app.models.ingestion_job import IngestionJob


class JobStep(UUIDPkMixin, Base):
    """任务步骤（F2 流水线逐步回写状态/耗时/产出；无 created_at/updated_at）。"""

    __tablename__ = "job_steps"
    __table_args__ = (
        Index("idx_job_steps_job_order", "job_id", "step_order"),
        ForeignKeyConstraint(
            ["job_id"],
            ["ingestion_jobs.id"],
            name="fk_job_steps_job",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        {**MYSQL_TABLE_KWARGS},
    )

    job_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    step_order: Mapped[int] = mapped_column(nullable=False)
    step_name: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="pending"
    )
    retry_count: Mapped[int] = mapped_column(nullable=False, server_default="0")
    input: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime3)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime3)
    error_message: Mapped[str | None] = mapped_column(Text)

    job: Mapped[IngestionJob] = relationship(back_populates="steps")
