"""Shared FastAPI dependencies.

* :func:`get_db` — request-scoped SQLAlchemy session (``yield`` + ``finally``).
* :func:`get_current_user` — MVP stub returning the preset default tenant/user;
  replaced by real authentication in stage 3.

The preset IDs below are stable UUID strings: B2's ``scripts/seed.py`` must
create the default tenant/user with exactly these ids so routers can trust
``get_current_user().tenant_id`` from day one.
"""

from __future__ import annotations

from collections.abc import Generator

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import SessionLocal

#: Preset default tenant id (seeded by B2's seed script, CHAR(36)).
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
#: Preset default admin user id (seeded by B2's seed script, CHAR(36)).
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000002"


class CurrentUser(BaseModel):
    """Identity attached to every request until real auth lands (stage 3)."""

    id: str
    tenant_id: str
    username: str
    display_name: str | None = None
    role: str = "admin"


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped session; always closed when the request ends."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_current_user() -> CurrentUser:
    """MVP: fixed default tenant/user. Stage 3 swaps in real authentication."""
    return CurrentUser(
        id=DEFAULT_USER_ID,
        tenant_id=DEFAULT_TENANT_ID,
        username="admin",
        display_name="Default Admin",
        role="admin",
    )
