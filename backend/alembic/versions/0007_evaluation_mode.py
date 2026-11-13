"""L4.1/N2 · evaluation_runs 加 retrieval_mode（ablation 维度）。

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-12

* 新增 ``retrieval_mode``：dense / hybrid / hybrid_rerank——同一数据集跨
  检索模式跑评估即可生成 ablation 对比。存量行为 dense（default）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_runs",
        sa.Column("retrieval_mode", sa.String(length=32), nullable=False, server_default="dense"),
    )


def downgrade() -> None:
    op.drop_column("evaluation_runs", "retrieval_mode")
