"""N3 · evaluation_runs.kind（retrieval / generation 双维评估）。

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-13

* 新增 ``kind``：retrieval（存量，检索指标）/ generation（N3：答案合成质量，
  faithfulness + answer relevancy，LLM-as-judge）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_runs",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="retrieval"),
    )


def downgrade() -> None:
    op.drop_column("evaluation_runs", "kind")
