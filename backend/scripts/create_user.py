"""Create a user account (admin CLI companion to the K2 auth system).

Usage (from ``backend/``)::

    env/Scripts/python.exe scripts/create_user.py <username> <password> [role] [tenant_id]

* role defaults to ``viewer``; one of admin / editor / viewer.
* tenant defaults to the preset tenant; must already exist.
* username is unique per tenant (``uq_users_tenant_username``) — duplicates
  exit 2 without writing.
* every creation leaves an ``auth.user_created`` audit row (K1 semantics).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

# Make the script runnable as `python scripts/create_user.py` without
# PYTHONPATH plumbing (backend root onto sys.path before app imports).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import AuditLog, Tenant, User  # noqa: E402
from sqlalchemy import select  # noqa: E402

setup_logging(level=settings.app.log_level)

VALID_ROLES = ("admin", "editor", "viewer")
USAGE = (
    "usage: python scripts/create_user.py <username> <password> [role] [tenant_id]\n"
    "  role defaults to viewer; tenant defaults to the preset tenant."
)


def main(argv: list[str]) -> int:
    if len(argv) < 2 or len(argv) > 4:
        print(USAGE)
        return 2
    username, password = argv[0], argv[1]
    role = argv[2] if len(argv) > 2 else "viewer"
    tenant_id = argv[3] if len(argv) > 3 else "00000000-0000-0000-0000-000000000001"

    if role not in VALID_ROLES:
        print(f"error: role must be one of {VALID_ROLES}, got {role!r}")
        return 2
    if len(password) < 6:
        print("error: password must be at least 6 characters")
        return 2

    with SessionLocal() as session:
        if session.get(Tenant, tenant_id) is None:
            print(f"error: tenant {tenant_id} does not exist")
            return 2
        existing = session.scalars(
            select(User).where(User.tenant_id == tenant_id, User.username == username)
        ).one_or_none()
        if existing is not None:
            print(
                f"error: username {username!r} already exists in tenant "
                f"{tenant_id} (user {existing.id})"
            )
            return 2

        user = User(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            username=username,
            role=role,
            status="active",
            password_hash=hash_password(password),
        )
        session.add(user)
        session.flush()
        # K1 semantics: account management is a write path — leave a trail.
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                user_id=user.id,
                action="auth.user_created",
                resource_type="user",
                resource_id=user.id,
                detail={"username": username, "role": role},
            )
        )
        session.commit()
        print(
            f"+ user created: {user.id} ({username}, role={role}, tenant={tenant_id})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
