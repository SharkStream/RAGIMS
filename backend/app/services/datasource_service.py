"""Datasource service functions (C3 — MVP placeholder).

Kept tiny on purpose: the connector framework (remote sources, sync) is a
post-MVP feature. ``create_local_datasource`` enforces the name-uniqueness
the DB schema deliberately leaves to the application layer.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import DuplicateError
from app.models.datasource import Datasource


def list_datasources(session: Session, tenant_id: str) -> list[Datasource]:
    """Tenant-scoped datasource list, newest first."""
    rows = session.scalars(
        select(Datasource)
        .where(Datasource.tenant_id == tenant_id)
        .order_by(Datasource.created_at.desc(), Datasource.id)
    ).all()
    return list(rows)


def create_local_datasource(
    session: Session, tenant_id: str, name: str, config: dict[str, Any] | None = None
) -> Datasource:
    """Create a ``local`` datasource; duplicate names → 409."""
    exists = session.scalar(
        select(func.count())
        .select_from(Datasource)
        .where(Datasource.tenant_id == tenant_id, Datasource.name == name)
    )
    if exists:
        raise DuplicateError(f"datasource name {name!r} already exists")
    ds = Datasource(tenant_id=tenant_id, name=name, type="local", config=config)
    session.add(ds)
    session.commit()
    return ds
