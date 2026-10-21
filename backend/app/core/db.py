"""SQLAlchemy engine & session factory for the MySQL 8 metadata database.

The engine is created at import time but connects lazily — importing this module
never opens a socket. ``core.deps.get_db`` hands out request-scoped sessions
from :data:`SessionLocal`; B2 (ORM & migration) defines the models on top, so
this module deliberately imports nothing from ``app.models``.
"""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.mysql.dsn,
    pool_pre_ping=True,  # silently reconnect stale pooled connections
    pool_size=settings.mysql.pool_size,
    pool_recycle=settings.mysql.pool_recycle,
    echo=settings.mysql.echo,
    # Cap TCP connect time so /readyz fails fast instead of hanging.
    connect_args={"connect_timeout": 10},
)


@event.listens_for(engine, "connect")
def _set_session_utc(dbapi_connection, _connection_record) -> None:
    """Pin every pooled session to UTC.

    B1 convention: ``DATETIME(3)`` columns store naive UTC. Python-side
    defaults write UTC, but DB-side ``DEFAULT/ON UPDATE CURRENT_TIMESTAMP(3)``
    follows the server timezone (often +08:00) unless the session is pinned —
    a silent 8-hour skew between ORM writes and raw-SQL writes otherwise.
    Alembic's engine (alembic/env.py) applies the same listener.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SET time_zone = '+00:00'")
    finally:
        cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)
