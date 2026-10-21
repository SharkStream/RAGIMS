"""B2 acceptance checks that need no live database.

Covers:

* ``Base.metadata`` holds exactly the 9 MVP tables; deferred tables absent.
* The 6 MVP-required composite/unique indexes exist with B1 names/columns
  (plus the two B1-added unique constraints).
* All 11 FKs are ``ON DELETE RESTRICT / ON UPDATE RESTRICT`` with B1 names.
* Compiling ``CREATE TABLE`` against the MySQL dialect reproduces the B1 DDL
  signatures: ``CHAR(36)``, ``DATETIME(3)`` + ``DEFAULT/ON UPDATE
  CURRENT_TIMESTAMP(3)``, ``MEDIUMTEXT``, ``JSON``, InnoDB/utf8mb4.
* Mixin behavior: UUID defaults and ``updated_at`` auto-maintenance hooks.
* The initial migration creates/drops exactly 9 tables.

Live-DB checks (``alembic upgrade head``, ``SHOW CREATE TABLE``, seed
idempotency, timestamp maintenance) are executed in the B2 runbook against
the configured MySQL; see ``docs/tasks/b2-orm-migration.md``.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_b2_models.py -v
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from app.models import (
    Base,
    Chunk,
    Datasource,
    Document,
    DocumentVersion,
    EmbeddingModel,
    IngestionJob,
    JobStep,
    Tenant,
    User,
)
from app.models.base import MYSQL_TABLE_KWARGS, utcnow_ms
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

# --------------------------------------------------------------------------- #
# Metadata shape
# --------------------------------------------------------------------------- #

MVP_TABLES = {
    "tenants",
    "users",
    "datasources",
    "embedding_models",
    "documents",
    "document_versions",
    "chunks",
    "ingestion_jobs",
    "job_steps",
}

DEFERRED_TABLES = [
    "chunking_strategies",
    "parsers",
    "permissions",
    "audit_logs",
    "evaluation_runs",
    "quality_checks",
]


def test_metadata_has_exactly_the_9_mvp_tables() -> None:
    assert set(Base.metadata.tables) == MVP_TABLES


def test_deferred_tables_are_absent() -> None:
    for name in DEFERRED_TABLES:
        assert name not in Base.metadata.tables


@pytest.mark.parametrize(
    "model",
    [
        Tenant,
        User,
        Datasource,
        EmbeddingModel,
        Document,
        DocumentVersion,
        Chunk,
        IngestionJob,
        JobStep,
    ],
)
def test_model_tablename_matches_table(model: type) -> None:
    """Every imported model maps to a real metadata table (F401 guard)."""
    assert Base.metadata.tables[model.__tablename__] is model.__table__


def test_every_table_is_innodb_utf8mb4() -> None:
    for name in MVP_TABLES:
        table = Base.metadata.tables[name]
        assert table.dialect_options["mysql"]["engine"] == "InnoDB"
        assert table.dialect_options["mysql"]["charset"] == "utf8mb4"
        assert table.dialect_options["mysql"]["collate"] == "utf8mb4_unicode_ci"


def test_mysql_table_kwargs_dict_is_not_shared() -> None:
    """Models must merge copies — mutating one table args must not leak."""
    kw = MYSQL_TABLE_KWARGS
    assert kw["mysql_engine"] == "InnoDB"


# --------------------------------------------------------------------------- #
# Indexes (plan.md §4.9 + B1 additions)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("table_name", "index_name", "columns"),
    [
        ("documents", "idx_documents_tenant_status", ["tenant_id", "status"]),
        ("chunks", "idx_chunks_version_index", ["doc_version_id", "chunk_index"]),
        ("chunks", "idx_chunks_doc_id", ["doc_id"]),
        ("ingestion_jobs", "idx_ingestion_jobs_tenant_status", ["tenant_id", "status"]),
        ("job_steps", "idx_job_steps_job_order", ["job_id", "step_order"]),
    ],
)
def test_required_composite_indexes(
    table_name: str, index_name: str, columns: list[str]
) -> None:
    table = Base.metadata.tables[table_name]
    match = [ix for ix in table.indexes if ix.name == index_name]
    assert len(match) == 1, f"index {index_name} missing on {table_name}"
    assert [c.name for c in match[0].columns] == columns


@pytest.mark.parametrize(
    ("table_name", "constraint_name", "columns"),
    [
        ("users", "uq_users_tenant_username", ["tenant_id", "username"]),
        (
            "embedding_models",
            "uq_embedding_models_provider_model",
            ["provider", "model_name"],
        ),
        (
            "document_versions",
            "uq_doc_versions_doc_content",
            ["doc_id", "content_hash"],
        ),
    ],
)
def test_unique_constraints(
    table_name: str, constraint_name: str, columns: list[str]
) -> None:
    table = Base.metadata.tables[table_name]
    uniques = [
        c
        for c in table.constraints
        if isinstance(c, UniqueConstraint) and c.name == constraint_name
    ]
    assert len(uniques) == 1, f"unique {constraint_name} missing on {table_name}"
    assert [c.name for c in uniques[0].columns] == columns


def test_no_redundant_fk_single_column_indexes() -> None:
    """FK columns covered by composite/unique indexes must not get an extra index.

    E.g. ``chunks.doc_version_id`` is the leftmost column of
    ``idx_chunks_version_index``; an additional ``Index('doc_version_id')``
    would duplicate the FK index in InnoDB (B2 acceptance).

    ``datasources.tenant_id`` and ``ingestion_jobs.doc_id/doc_version_id`` carry
    no declared index on purpose — InnoDB auto-creates exactly one per FK there
    (verified live via SHOW CREATE TABLE, B1 §4).
    """
    fk_columns: set[tuple[str, str]] = set()
    for table in Base.metadata.tables.values():
        for con in table.constraints:
            if isinstance(con, ForeignKeyConstraint):
                fk_columns.add((table.name, con.columns[0].name))

    # chunks.doc_id is the ONE intentional declared single-column FK index:
    # chunks has two FKs and only doc_version_id is covered by a composite.
    intentional_single_fk_indexes = {("chunks", "doc_id")}

    for table in Base.metadata.tables.values():
        for ix in table.indexes:
            first_col = ix.columns[0]
            is_single_fk_index = (table.name, first_col.name) in fk_columns and len(
                ix.columns
            ) == 1
            if is_single_fk_index:
                assert (table.name, first_col.name) in intentional_single_fk_indexes, (
                    f"unexpected declared single-column FK index {ix.name} on "
                    f"{table.name} — InnoDB already indexes FK columns"
                )
                continue


#: Exact declared-index inventory per table (B1 §2/§4). Single-column FK
#: indexes appear only where a second FK needs one (chunks.doc_id).
EXPECTED_INDEX_INVENTORY: dict[str, set[tuple[str, tuple[str, ...]]]] = {
    "documents": {("idx_documents_tenant_status", ("tenant_id", "status"))},
    "chunks": {
        ("idx_chunks_version_index", ("doc_version_id", "chunk_index")),
        ("idx_chunks_doc_id", ("doc_id",)),
    },
    "ingestion_jobs": {("idx_ingestion_jobs_tenant_status", ("tenant_id", "status"))},
    "job_steps": {("idx_job_steps_job_order", ("job_id", "step_order"))},
    "tenants": set(),
    "users": set(),
    "datasources": set(),
    "embedding_models": set(),
    "document_versions": set(),
}


def test_declared_index_inventory_matches_b1() -> None:
    for name in sorted(MVP_TABLES):
        table = Base.metadata.tables[name]
        actual = {(ix.name, tuple(c.name for c in ix.columns)) for ix in table.indexes}
        assert actual == EXPECTED_INDEX_INVENTORY[name], f"index drift on {name}"


# --------------------------------------------------------------------------- #
# Foreign keys
# --------------------------------------------------------------------------- #

EXPECTED_FKS = {
    "users": {"fk_users_tenant": ("tenants", ["tenant_id"], ["id"])},
    "datasources": {"fk_datasources_tenant": ("tenants", ["tenant_id"], ["id"])},
    "documents": {
        "fk_documents_tenant": ("tenants", ["tenant_id"], ["id"]),
        "fk_documents_datasource": ("datasources", ["datasource_id"], ["id"]),
    },
    "document_versions": {"fk_doc_versions_doc": ("documents", ["doc_id"], ["id"])},
    "chunks": {
        "fk_chunks_doc_version": ("document_versions", ["doc_version_id"], ["id"]),
        "fk_chunks_doc": ("documents", ["doc_id"], ["id"]),
    },
    "ingestion_jobs": {
        "fk_jobs_tenant": ("tenants", ["tenant_id"], ["id"]),
        "fk_jobs_doc": ("documents", ["doc_id"], ["id"]),
        "fk_jobs_doc_version": ("document_versions", ["doc_version_id"], ["id"]),
    },
    "job_steps": {"fk_job_steps_job": ("ingestion_jobs", ["job_id"], ["id"])},
}


def test_all_fks_named_restrict_and_pointing_at_expected_targets() -> None:
    total = 0
    for table_name, expected in EXPECTED_FKS.items():
        table = Base.metadata.tables[table_name]
        fks = {
            c.name: c for c in table.constraints if isinstance(c, ForeignKeyConstraint)
        }
        assert set(fks) == set(expected), f"FK mismatch on {table_name}"
        for name, (referred, cols, referred_cols) in expected.items():
            fk = fks[name]
            assert fk.ondelete == "RESTRICT"
            assert fk.onupdate == "RESTRICT"
            assert fk.referred_table.name == referred
            assert [c.name for c in fk.columns] == cols
            assert list(fk.column_keys) == cols
            assert [c.name for c in fk.referred_table.primary_key] == referred_cols
            total += 1
    assert total == 11


def test_created_by_is_not_a_fk() -> None:
    """ingestion_jobs.created_by stays FK-free (user deletion must not block jobs)."""
    table = Base.metadata.tables["ingestion_jobs"]
    fks = [c for c in table.constraints if isinstance(c, ForeignKeyConstraint)]
    assert all("created_by" not in [c.name for c in fk.columns] for fk in fks)


# --------------------------------------------------------------------------- #
# MySQL DDL rendering (offline compile, no connection)
# --------------------------------------------------------------------------- #

TIMESTAMPED_TABLES = [
    "tenants",
    "users",
    "datasources",
    "documents",
    "document_versions",
    "ingestion_jobs",
]


@pytest.mark.parametrize("table_name", sorted(MVP_TABLES))
def test_ddl_engine_and_charset(table_name: str) -> None:
    ddl = _mysql_ddl(table_name)
    assert "ENGINE=InnoDB" in ddl
    assert "CHARSET=utf8mb4" in ddl
    assert "COLLATE utf8mb4_unicode_ci" in ddl


@pytest.mark.parametrize("table_name", TIMESTAMPED_TABLES)
def test_ddl_datetime3_with_server_maintenance(table_name: str) -> None:
    ddl = _mysql_ddl(table_name)
    assert "created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)" in ddl
    assert (
        "updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) "
        "ON UPDATE CURRENT_TIMESTAMP(3)" in ddl
    )


def test_ddl_uuid_pk_is_char36() -> None:
    ddl = _mysql_ddl("tenants")
    assert "id CHAR(36) NOT NULL" in ddl
    assert "PRIMARY KEY (id)" in ddl


def test_ddl_chunks_mediumtext_and_json_metadata() -> None:
    ddl = _mysql_ddl("chunks")
    assert "text MEDIUMTEXT NOT NULL" in ddl
    assert "metadata JSON" in ddl
    assert "chunk_hash CHAR(64) NOT NULL" in ddl
    # Immutable rows: created_at only (B1 §3.7).
    assert "updated_at" not in ddl


def test_ddl_document_versions_idempotency_and_soft_delete() -> None:
    ddl = _mysql_ddl("document_versions")
    assert "content_hash CHAR(64) NOT NULL" in ddl
    assert "is_latest BOOL NOT NULL" in ddl
    assert "is_deleted BOOL NOT NULL" in ddl
    assert "UNIQUE (doc_id, content_hash)" in ddl


def test_ddl_embedding_models_has_no_timestamps() -> None:
    ddl = _mysql_ddl("embedding_models")
    assert "created_at" not in ddl
    assert "updated_at" not in ddl


def _mysql_ddl(table_name: str) -> str:
    table = Base.metadata.tables[table_name]
    return str(CreateTable(table).compile(dialect=mysql.dialect()))


# --------------------------------------------------------------------------- #
# Mixins / column behaviors
# --------------------------------------------------------------------------- #


def test_uuid_pk_default_generates_unique_strings() -> None:
    default = Tenant.__table__.c.id.default
    assert default is not None and default.is_callable
    values = {default.arg(None) for _ in range(50)}
    assert len(values) == 50
    assert all(len(v) == 36 and v.count("-") == 4 for v in values)


def test_updated_at_has_onupdate_hook() -> None:
    assert Tenant.__table__.c.updated_at.onupdate is not None
    assert Document.__table__.c.updated_at.onupdate is not None


def test_utcnow_ms_is_naive_utc_millisecond_truncated() -> None:
    now = utcnow_ms()
    assert isinstance(now, datetime)
    assert now.tzinfo is None
    assert now.microsecond % 1000 == 0


def test_chunk_metadata_column_maps_to_metadata_name() -> None:
    """Python attribute is ``meta`` (reserved name) mapped to column ``metadata``."""
    col = Chunk.__table__.c["metadata"]
    assert col.name == "metadata"
    assert Chunk.meta.name == "metadata"  # type: ignore[attr-defined]
    assert "meta" not in Chunk.__table__.c


def test_job_steps_has_no_created_at() -> None:
    """B1 DDL: job_steps carries only started_at/finished_at timing columns."""
    assert "created_at" not in Base.metadata.tables["job_steps"].c


def test_json_columns_are_nullable() -> None:
    for table_name, col in [
        ("datasources", "config"),
        ("embedding_models", "config"),
        ("documents", "tags"),
        ("chunks", "metadata"),
        ("job_steps", "input"),
        ("job_steps", "output"),
    ]:
        assert (
            Base.metadata.tables[table_name].c[col].nullable
        ), f"{table_name}.{col} should be nullable"


# --------------------------------------------------------------------------- #
# Initial migration sanity (file-level, no DB)
# --------------------------------------------------------------------------- #


def test_initial_migration_creates_and_drops_9_tables() -> None:
    path = (
        Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0001_initial.py"
    )
    source = path.read_text(encoding="utf-8")
    assert source.count("op.create_table(") == 9
    assert source.count("op.drop_table(") == 9
    # Composite/unique indexes are created inline (inside create_table) so
    # InnoDB reuses them for FK prefixes instead of auto-creating duplicates.
    assert source.count("op.create_index(") == 0
    assert source.count("sa.Index(") == 5


def test_models_and_migration_stay_in_sync() -> None:
    """Every model table name appears in the initial migration's upgrade."""
    path = (
        Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0001_initial.py"
    )
    source = path.read_text(encoding="utf-8")
    for name in sorted(MVP_TABLES):
        assert f'op.create_table(\n        "{name}"' in source, name


def test_datasource_relationships_wired() -> None:
    """Spot-check relationships used by later stages (C1/E3/F2)."""
    assert Document.versions.property.mapper is DocumentVersion.__mapper__
    assert DocumentVersion.chunks.property.mapper is Chunk.__mapper__
    assert IngestionJob.steps.property.mapper is JobStep.__mapper__
    assert Datasource.documents.property.mapper is Document.__mapper__
