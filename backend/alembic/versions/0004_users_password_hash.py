"""K2 · users.password_hash 列（认证落地）。

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-05

* ``users`` 补 ``password_hash VARCHAR(255) NULL``：pbkdf2 存储格式
  ``pbkdf2$iterations$salt_hex$hash_hex``（app/core/security.py）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_hash")
