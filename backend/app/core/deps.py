"""Shared FastAPI dependencies.

* :func:`get_db` — request-scoped SQLAlchemy session (``yield`` + ``finally``).
* :func:`get_current_user` — K2 real authentication: a Bearer token is strictly
  verified (signature + expiry + live user row); role/tenant always come from
  the DB row, never from the token alone.

Legacy/dev mode: when ``SECURITY__AUTH_REQUIRED`` is false (default) a request
with **no** Authorization header falls back to the seeded admin identity so
pre-K2 integrations keep working. A present token is always verified.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.errors import AppError
from app.core.security import parse_token
from app.models.user import User

#: Preset default tenant id (seeded by B2's seed script, CHAR(36)).
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
#: Preset default admin user id (seeded by B2's seed script, CHAR(36)).
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000002"

_UNAUTHORIZED = AppError(
    "authentication required", code="ERR_UNAUTHORIZED", status_code=401
)

#: ``auto_error=False`` so a missing header reaches our own 401 handling.
_bearer = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    """Identity attached to every request (from token + users row)."""

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


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ] = None,
    db: Annotated[Session | None, Depends(get_db)] = None,
) -> CurrentUser:
    """Resolve the caller identity; strict when a token is present."""
    if credentials is not None:
        payload = parse_token(credentials.credentials)
        user_id = str(payload.get("user_id"))
        user = db.get(User, user_id) if db is not None else None
        if user is None or str(user.status) != "active":
            raise _UNAUTHORIZED
        return CurrentUser(
            id=str(user.id),
            tenant_id=str(user.tenant_id),
            username=str(user.username),
            role=str(user.role),
        )

    if settings.security.auth_required:
        raise _UNAUTHORIZED

    # Dev fallback (pre-K2 compatibility): seeded admin, token not required.
    return CurrentUser(
        id=DEFAULT_USER_ID,
        tenant_id=DEFAULT_TENANT_ID,
        username="admin",
        display_name="Default Admin",
        role="admin",
    )
