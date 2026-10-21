"""Alembic migration environment for the RAGIMS metadata database.

Customizations versus the stock template:

* The database URL is injected from ``app.core.config.settings.mysql.dsn``
  (pydantic-settings reads ``backend/.env`` / environment) — ``alembic.ini``
  intentionally stays credential-free.
* ``target_metadata`` points at :mod:`app.models` so autogenerate discovers
  all 9 MVP tables (B2 step 4).
* ``backend/`` is put on ``sys.path`` explicitly so Alembic works regardless
  of the invocation working directory.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, event, pool

# Make "app" importable regardless of the process working directory
# (alembic.ini's prepend_sys_path only covers the invocation cwd).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.models import Base  # noqa: E402

# The Alembic Config object, which provides access to values in alembic.ini.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Single source of truth for the DSN (no credentials in alembic.ini). The URL
# is passed straight to create_engine/context below — NOT via
# ``config.set_main_option``, because URL-encoded characters (e.g. ``%40`` in
# passwords) break configparser interpolation.
DATABASE_URL = settings.mysql.dsn

# Model metadata for autogenerate support.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode: emit SQL to stdout, no DB connection."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode: connect and emit DDL."""
    connectable = create_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": 10},
    )

    # Keep DB-side CURRENT_TIMESTAMP(3) in UTC, matching app writes (B1 §1).
    @event.listens_for(connectable, "connect")
    def _set_session_utc(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SET time_zone = '+00:00'")
        finally:
            cursor.close()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
