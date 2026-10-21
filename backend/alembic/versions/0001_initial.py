"""B1 · MVP 9 张表初始迁移（MySQL 8）。

Revision ID: 0001
Revises:
Create Date: 2026-10-21

由 Alembic autogenerate 产物人工复核整理（B2 step 4）：

* 表与列定义与 ``docs/db-schema.md``（B1）逐字段一致，建表顺序按 FK 拓扑：
  tenants → users → datasources → embedding_models → documents →
  document_versions → chunks → ingestion_jobs → job_steps。
* 复合/唯一索引并入 ``op.create_table``（而非事后的 ``op.create_index``），
  使 InnoDB 直接复用这些索引满足 FK 前缀要求，避免 FK 单列索引被重复创建。
* 所有 FK 为 ``ON DELETE RESTRICT ON UPDATE RESTRICT``，显式命名与 B1 文档一致。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the 9 MVP tables (FK-topological order, indexes inline)."""
    op.create_table(
        "tenants",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            server_default=sa.text("CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "users",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("tenant_id", sa.CHAR(length=36), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=32), server_default="admin", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            server_default=sa.text("CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_users_tenant",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("tenant_id", "username", name="uq_users_tenant_username"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "datasources",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("tenant_id", sa.CHAR(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("type", sa.String(length=32), server_default="local", nullable=False),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("sync_mode", sa.String(length=16), server_default="manual", nullable=False),
        sa.Column("sync_cron", sa.String(length=64), nullable=True),
        sa.Column(
            "last_sync_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            server_default=sa.text("CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_datasources_tenant",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasources")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "embedding_models",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_embedding_models")),
        sa.UniqueConstraint(
            "provider", "model_name", name="uq_embedding_models_provider_model"
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("tenant_id", sa.CHAR(length=36), nullable=False),
        sa.Column("datasource_id", sa.CHAR(length=36), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=16), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=True),
        sa.Column("author", sa.String(length=128), nullable=True),
        sa.Column("department", sa.String(length=128), nullable=True),
        sa.Column("document_type", sa.String(length=64), nullable=True),
        sa.Column(
            "access_level", sa.String(length=32), server_default="internal", nullable=False
        ),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("current_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="processing", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            server_default=sa.text("CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_documents_tenant",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["datasource_id"],
            ["datasources.id"],
            name="fk_documents_datasource",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        # Covers fk_documents_tenant — no separate single-column index is created.
        sa.Index("idx_documents_tenant_status", "tenant_id", "status", unique=False),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "document_versions",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("doc_id", sa.CHAR(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("file_size", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "parse_status", sa.String(length=32), server_default="pending", nullable=False
        ),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column("is_latest", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "valid_from",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            nullable=True,
        ),
        sa.Column(
            "valid_to",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            server_default=sa.text("CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["doc_id"],
            ["documents.id"],
            name="fk_doc_versions_doc",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_versions")),
        # Idempotency key (doc_id, content_hash); covers fk_doc_versions_doc.
        sa.UniqueConstraint("doc_id", "content_hash", name="uq_doc_versions_doc_content"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("doc_version_id", sa.CHAR(length=36), nullable=False),
        sa.Column("doc_id", sa.CHAR(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text().with_variant(mysql.MEDIUMTEXT(), "mysql"), nullable=False),
        sa.Column("token_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chunk_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(length=255), nullable=True),
        sa.Column("qdrant_point_id", sa.CHAR(length=36), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            server_default=sa.text("CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["doc_version_id"],
            ["document_versions.id"],
            name="fk_chunks_doc_version",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["doc_id"],
            ["documents.id"],
            name="fk_chunks_doc",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
        # Both indexes cover their FK columns — no FK auto-index duplicates.
        sa.Index(
            "idx_chunks_version_index", "doc_version_id", "chunk_index", unique=False
        ),
        sa.Index("idx_chunks_doc_id", "doc_id", unique=False),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("tenant_id", sa.CHAR(length=36), nullable=False),
        sa.Column("doc_id", sa.CHAR(length=36), nullable=True),
        sa.Column("doc_version_id", sa.CHAR(length=36), nullable=True),
        sa.Column("job_type", sa.String(length=32), server_default="full", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="5", nullable=False),
        sa.Column("created_by", sa.CHAR(length=36), nullable=True),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            nullable=True,
        ),
        sa.Column(
            "finished_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            server_default=sa.text("CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_jobs_tenant",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["doc_id"],
            ["documents.id"],
            name="fk_jobs_doc",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["doc_version_id"],
            ["document_versions.id"],
            name="fk_jobs_doc_version",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_jobs")),
        # Covers fk_jobs_tenant.
        sa.Index(
            "idx_ingestion_jobs_tenant_status", "tenant_id", "status", unique=False
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "job_steps",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("job_id", sa.CHAR(length=36), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("input", sa.JSON(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            nullable=True,
        ),
        sa.Column(
            "finished_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql"),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["ingestion_jobs.id"],
            name="fk_job_steps_job",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_steps")),
        # Covers fk_job_steps_job.
        sa.Index("idx_job_steps_job_order", "job_id", "step_order", unique=False),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )


def downgrade() -> None:
    """Drop the 9 MVP tables in reverse FK order (indexes die with tables)."""
    op.drop_table("job_steps")
    op.drop_table("ingestion_jobs")
    op.drop_table("chunks")
    op.drop_table("document_versions")
    op.drop_table("documents")
    op.drop_table("users")
    op.drop_table("datasources")
    op.drop_table("embedding_models")
    op.drop_table("tenants")
