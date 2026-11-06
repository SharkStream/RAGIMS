"""User-management API schemas (K7)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UserCreateRequest(BaseModel):
    """``POST /auth/users`` body (admin-only)."""

    username: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="viewer", pattern=r"^(admin|editor|viewer)$")
    email: str | None = Field(default=None, max_length=255)


class UserPatchRequest(BaseModel):
    """``PATCH /auth/users/{id}`` body — all fields optional."""

    role: str | None = Field(default=None, pattern=r"^(admin|editor|viewer)$")
    status: str | None = Field(default=None, pattern=r"^(active|disabled)$")
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserOut(BaseModel):
    """User row for admin listing — never includes password_hash.

    ``created_at``/``updated_at`` are nullable because freshly constructed
    (not yet flushed) ORM objects have no server-default values yet.
    """

    id: str
    tenant_id: str
    username: str
    email: str | None = None
    role: str
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
