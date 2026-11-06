"""L1 · quality_checks + evaluation_runs 表（质量与评估阶段第一步）。

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-06

* 新增 ``quality_checks``（plan.md 4.8）：文档版本级质量检查结果，
  ``(doc_version_id, check_type)`` 复合索引；版本删除时级联清理。
* 新增 ``evaluation_runs``（plan.md 4.8）：检索评估基准（数据集/指标/逐条
  结果 JSON），租户硬隔离 + ``(tenant_id, created_at)`` 倒序复合索引；
  只增不改（重跑即新行）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quality_checks",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("doc_version_id", sa.CHAR(36), nullable=False),
        sa.Column("check_type", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime().with_variant(sa.dialects.mysql.DATETIME(fsp=3), "mysql"),
            server_default=sa.text("CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_quality_checks"),
        sa.ForeignKeyConstraint(
            ["doc_version_id"],
            ["document_versions.id"],
            name="fk_quality_checks_version",
            ondelete="CASCADE",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "idx_quality_checks_doc_version",
        "quality_checks",
        ["doc_version_id", "check_type"],
        unique=False,
    )
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("tenant_id", sa.CHAR(36), nullable=False),
        sa.Column("user_id", sa.CHAR(36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("dataset", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime().with_variant(sa.dialects.mysql.DATETIME(fsp=3), "mysql"),
            server_default=sa.text("CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evaluation_runs"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "idx_evaluation_runs_tenant_created",
        "evaluation_runs",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_evaluation_runs_tenant_created", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index("idx_quality_checks_doc_version", table_name="quality_checks")
    op.drop_table("quality_checks")
