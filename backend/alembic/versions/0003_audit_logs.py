"""K1 · audit_logs 表（权限与多租户阶段第一步）。

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-05

* 新增 ``audit_logs``：写路径审计（plan.md 4.7），租户硬隔离 + 倒序复合索引。
* 只增不改：无 updated_at；detail 用 MySQL 原生 JSON。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("tenant_id", sa.CHAR(36), nullable=False),
        sa.Column("user_id", sa.CHAR(36), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.CHAR(36), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime().with_variant(sa.dialects.mysql.DATETIME(fsp=3), "mysql"),
            server_default=sa.text("CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "idx_audit_logs_tenant_created",
        "audit_logs",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_audit_logs_tenant_created", table_name="audit_logs")
    op.drop_table("audit_logs")
