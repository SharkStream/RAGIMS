"""Audit-log API schemas (K1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    """One write-path audit entry (``GET /audit-logs`` row)."""

    id: str
    tenant_id: str
    user_id: str
    action: str
    resource_type: str
    resource_id: str
    detail: dict[str, Any] | None = None
    created_at: datetime
