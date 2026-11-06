"""L4.1 · evaluation_runs 加 parent_run_id（重跑溯源，替代 -rerun 名字后缀）。

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-06

* 新增 ``parent_run_id``：重跑时记录派生来源的 run id（NULL = 首次创建）。
* 故意**不加 FK**：run 行可被独立清理，溯源是软指针（悬空即视为未知来源）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_runs",
        sa.Column("parent_run_id", sa.CHAR(36), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evaluation_runs", "parent_run_id")
