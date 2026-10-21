"""Declarative base, mixins, and shared MySQL conventions for ORM models.

Conventions mirror ``docs/db-schema.md`` (B1):

* UUID primary keys are ``CHAR(36)`` strings (``uuid4()`` hex-dashed), chosen
  over ``BINARY(16)`` so rows stay readable without casts in the MVP.
* Timestamps are ``DATETIME(3)`` storing **naive UTC** values. They are
  maintained on both sides on purpose:

  - Python-side ``default``/``onupdate`` so ORM instances carry fresh values
    right after flush without a server round-trip;
  - DB-level ``DEFAULT`` / ``ON UPDATE CURRENT_TIMESTAMP(3)`` so raw-SQL
    writes (seed/cleanup scripts, manual fixes) are timestamped too.

* JSON columns use ``sqlalchemy.JSON`` (renders native MySQL ``JSON``).
* Every table is InnoDB / utf8mb4 / utf8mb4_unicode_ci.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import CHAR, DateTime, MetaData, Text, text
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# --------------------------------------------------------------------------- #
# Shared table options / constraint naming
# --------------------------------------------------------------------------- #

#: Table options applied to every model (docs/db-schema.md §1). Models merge a
#: copy of this dict into their ``__table_args__``.
MYSQL_TABLE_KWARGS: dict[str, Any] = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}

#: Deterministic names for constraints that are not named explicitly. B2 names
#: every FK / unique / composite index explicitly (see docs/db-schema.md), so
#: this is a safety net for future constraints.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(referred_table_name)s_%(referred_column_0_name)s",
    "pk": "pk_%(table_name)s",
}

# --------------------------------------------------------------------------- #
# Shared column types (MySQL-first, portable fallbacks for other dialects)
# --------------------------------------------------------------------------- #

#: UUID stored as ``CHAR(36)``.
UUIDStr = str

#: ``DATETIME(3)`` on MySQL; plain ``DATETIME`` elsewhere.
DateTime3 = DateTime().with_variant(MySQLDateTime(fsp=3), "mysql")

#: ``MEDIUMTEXT`` on MySQL (16MB, for chunk text); plain ``TEXT`` elsewhere.
MediumText = Text().with_variant(MEDIUMTEXT(), "mysql")


def utcnow_ms() -> datetime:
    """Naive UTC now truncated to milliseconds (matches ``DATETIME(3)``)."""
    now = datetime.now(UTC).replace(tzinfo=None)
    return now.replace(microsecond=(now.microsecond // 1000) * 1000)


# --------------------------------------------------------------------------- #
# Base and mixins
# --------------------------------------------------------------------------- #


class Base(DeclarativeBase):
    """Declarative base; importing :mod:`app.models` registers all tables."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPkMixin:
    """``id CHAR(36)`` primary key with a Python-side ``uuid4`` default."""

    id: Mapped[str] = mapped_column(
        CHAR(36), primary_key=True, default=lambda: str(uuid4())
    )


class TimestampMixin:
    """``created_at`` / ``updated_at`` (``DATETIME(3)``, naive UTC).

    ``updated_at`` is maintained automatically on every ORM update via
    ``onupdate`` and on every DB-level update via ``ON UPDATE
    CURRENT_TIMESTAMP(3)``.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime3,
        nullable=False,
        default=utcnow_ms,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime3,
        nullable=False,
        default=utcnow_ms,
        onupdate=utcnow_ms,
        server_default=text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
    )
