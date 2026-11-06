"""Auth API routes (K2 login/me + K7 user management).

``POST /auth/login`` verifies the pbkdf2 password and issues a stateless HMAC
token; ``GET /auth/me`` echoes the resolved identity. K7 adds admin-only user
management (create / list / patch) — every mutation is audited, cross-tenant
targets are 404, and an admin can never patch their own row (anti-lockout).
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import CurrentUser, get_current_user, get_db
from app.core.errors import AppError
from app.core.permissions import require_admin
from app.core.security import hash_password, issue_token, verify_password
from app.models.user import User
from app.schemas.common import ApiResponse, PageResult, ok
from app.schemas.user import UserCreateRequest, UserOut, UserPatchRequest
from app.services.audit_service import record_audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_in: int
    user: CurrentUser


_UNAUTHORIZED = AppError(
    "invalid username or password", code="ERR_UNAUTHORIZED", status_code=401
)

#: K7 password policy: ≥8 chars with at least one letter and one digit.
_PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,128}$")

_CONFLICT = AppError("resource state conflict", code="ERR_CONFLICT", status_code=409)


@router.post(
    "/login",
    response_model=ApiResponse[LoginResponse],
    summary="Login with username/password, receive a bearer token",
)
def login(
    body: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[LoginResponse]:
    user = db.scalars(select(User).where(User.username == body.username)).first()
    # Same error for unknown user / wrong password / disabled account — no
    # account enumeration.
    if user is None or not verify_password(body.password, user.password_hash):
        raise _UNAUTHORIZED
    if str(user.status) != "active":
        raise _UNAUTHORIZED

    current = CurrentUser(
        id=str(user.id),
        tenant_id=str(user.tenant_id),
        username=str(user.username),
        role=str(user.role),
    )
    record_audit(
        db,
        tenant_id=current.tenant_id,
        user_id=current.id,
        action="auth.login",
        resource_type="user",
        resource_id=current.id,
        detail={"username": current.username},
    )
    return ok(
        LoginResponse(
            token=issue_token(
                user_id=current.id,
                tenant_id=current.tenant_id,
                role=current.role,
                username=current.username,
            ),
            expires_in=settings.security.token_ttl_seconds,
            user=current,
        )
    )


@router.get(
    "/me",
    response_model=ApiResponse[CurrentUser],
    summary="Echo the authenticated identity (validates the token)",
)
def me(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[CurrentUser]:
    return ok(user)


# --------------------------------------------------------------------------- #
# K7 · user management (admin-only)
# --------------------------------------------------------------------------- #


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=str(u.id),
        tenant_id=str(u.tenant_id),
        username=str(u.username),
        email=u.email,
        role=str(u.role),
        status=str(u.status),
        created_at=u.created_at,
        updated_at=u.updated_at,
    )


def _same_tenant_or_404(db: Session, tenant_id: str, user_id: str) -> User:
    """K7: cross-tenant targets are indistinguishable from missing ones."""
    user = db.get(User, user_id)
    if user is None or str(user.tenant_id) != tenant_id:
        raise AppError(
            f"user {user_id} not found", code="ERR_NOT_FOUND", status_code=404
        )
    return user


def _check_password_policy(password: str) -> None:
    if not _PASSWORD_RE.match(password):
        raise AppError(
            "password must be at least 8 characters and contain letters and digits",
            code="ERR_VALIDATION",
            status_code=422,
        )


@router.post(
    "/users",
    response_model=ApiResponse[UserOut],
    status_code=201,
    summary="Create a user in the admin's own tenant (admin-only)",
)
def create_user(
    body: UserCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[CurrentUser, Depends(require_admin)],
) -> ApiResponse[UserOut]:
    _check_password_policy(body.password)
    dup = db.scalars(
        select(User).where(
            User.tenant_id == admin.tenant_id, User.username == body.username
        )
    ).one_or_none()
    if dup is not None:
        raise AppError(
            f"username {body.username!r} already exists",
            code="ERR_CONFLICT",
            status_code=409,
        )
    user = User(
        id=str(uuid.uuid4()),
        tenant_id=admin.tenant_id,
        username=body.username,
        email=body.email,
        role=body.role,
        status="active",
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    record_audit(
        db,
        tenant_id=admin.tenant_id,
        user_id=admin.id,
        action="auth.user_created",
        resource_type="user",
        resource_id=str(user.id),
        detail={"username": body.username, "role": body.role},
    )
    return ok(_user_out(user))


@router.get(
    "/users",
    response_model=ApiResponse[PageResult[UserOut]],
    summary="List the admin's own tenant users (admin-only)",
)
def list_users(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[CurrentUser, Depends(require_admin)],
    status: Annotated[str | None, Query(description="active / disabled")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ApiResponse[PageResult[UserOut]]:
    stmt = select(User).where(User.tenant_id == admin.tenant_id)
    count_stmt = (
        select(func.count()).select_from(User).where(User.tenant_id == admin.tenant_id)
    )
    if status is not None:
        stmt = stmt.where(User.status == status)
        count_stmt = count_stmt.where(User.status == status)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return ok(
        PageResult.of(
            [_user_out(r) for r in rows],
            total=int(total),
            page=page,
            page_size=page_size,
        )
    )


@router.patch(
    "/users/{user_id}",
    response_model=ApiResponse[UserOut],
    summary="Change role / status / password (admin-only; never on yourself)",
)
def patch_user(
    user_id: str,
    body: UserPatchRequest,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[CurrentUser, Depends(require_admin)],
) -> ApiResponse[UserOut]:
    fields = {
        k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None
    }
    if not fields:
        raise AppError(
            "no updatable field provided", code="ERR_BAD_REQUEST", status_code=400
        )
    if user_id == admin.id:
        # Anti-lockout: an admin cannot demote/disable/re-password themselves.
        raise AppError(
            "you cannot modify your own account via the API",
            code="ERR_CONFLICT",
            status_code=409,
        )

    user = _same_tenant_or_404(db, admin.tenant_id, user_id)
    old_role, old_status = str(user.role), str(user.status)

    if "password" in fields:
        _check_password_policy(fields["password"])
        user.password_hash = hash_password(fields["password"])
    if "role" in fields:
        user.role = fields["role"]
    if "status" in fields:
        user.status = fields["status"]
    db.commit()

    actions: list[tuple[str, dict[str, object]]] = []
    if "password" in fields:
        actions.append(("auth.password_reset", {"username": user.username}))
    if "role" in fields and old_role != str(user.role):
        actions.append(
            (
                "auth.role_changed",
                {
                    "username": user.username,
                    "from": old_role,
                    "to": str(user.role),
                },
            )
        )
    if "status" in fields and old_status != str(user.status):
        actions.append(
            (
                (
                    "auth.user_disabled"
                    if str(user.status) == "disabled"
                    else "auth.user_enabled"
                ),
                {"username": user.username},
            )
        )
    for action, detail in actions:
        record_audit(
            db,
            tenant_id=admin.tenant_id,
            user_id=admin.id,
            action=action,
            resource_type="user",
            resource_id=str(user.id),
            detail=detail,
        )
    return ok(_user_out(user))
