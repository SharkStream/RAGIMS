"""J1 · documents 增量更新唯一性（生成列 + 唯一约束）。

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04

* 新增 VIRTUAL 生成列 ``active_uniq``：live 行恒为 'ACTIVE'，deleted 行取自身
  id —— 使 ``UNIQUE(tenant_id, file_name, active_uniq)`` 只约束"同名 live 文档
  唯一"（J1 增量更新的 DB 级并发兜底），软删历史永不占用名字。
* 生成列 DDL Alembic 不原生支持，走原生 SQL（MySQL 8 语法）；生成列上的唯一
  索引用 op.create_unique_constraint。
* 生成列不可写入：ORM 层 Computed() 已声明，INSERT/UPDATE 自动跳过该列。
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE documents "
        "ADD COLUMN active_uniq CHAR(36) "
        "GENERATED ALWAYS AS (IF(`status` = 'deleted', `id`, 'ACTIVE')) VIRTUAL, "
        "ADD UNIQUE KEY uq_documents_active_name "
        "(tenant_id, file_name, active_uniq)"
    )


def downgrade() -> None:
    op.drop_constraint("uq_documents_active_name", "documents", type_="unique")
    op.execute("ALTER TABLE documents DROP COLUMN active_uniq")
