"""Role model + authorization dependencies (K3).

Three roles cover the MVP (plan.md stage 3): ``admin`` (full), ``editor``
(read-write documents), ``viewer`` (read + retrieval only). Resource-level ACL
(permission rows) stays deferred — role + document ``access_level`` covers the
scenarios (K4 consumes the level whitelist).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.core.deps import CurrentUser, get_current_user
from app.core.errors import AppError

#: Roles allowed to mutate documents/jobs (everything that is not a GET).
WRITER_ROLES = frozenset({"admin", "editor"})

#: Retrieval visibility whitelist per role (K4 hard filter; admin/editor see
#: everything, viewers never see confidential content).
ACCESS_LEVELS_BY_ROLE: dict[str, tuple[str, ...]] = {
    "admin": ("public", "internal", "confidential"),
    "editor": ("public", "internal", "confidential"),
    "viewer": ("public", "internal"),
}

_FORBIDDEN = AppError(
    "insufficient role for this operation",
    code="ERR_FORBIDDEN",
    status_code=403,
)


def role_can_write(role: str) -> bool:
    return role in WRITER_ROLES


def role_can_read_access_level(role: str, access_level: str) -> bool:
    return access_level in ACCESS_LEVELS_BY_ROLE.get(role, ())


def require_writer(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """FastAPI dependency: 403 unless the caller holds a writer role."""
    if not role_can_write(user.role):
        raise _FORBIDDEN
    return user


def require_admin(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """FastAPI dependency: 403 unless the caller is an admin (K7)."""
    if user.role != "admin":
        raise _FORBIDDEN
    return user
