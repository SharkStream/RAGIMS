"""Datasource API schemas (C3 — MVP local-only placeholder)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DatasourceCreate(BaseModel):
    """Body of ``POST /datasources`` (MVP: only ``type=local`` is accepted)."""

    name: str = Field(min_length=1, max_length=128)
    type: str = Field(default="local", description="only 'local' is implemented")
    config: dict[str, Any] | None = None


class DatasourceOut(BaseModel):
    """Row of ``GET /datasources``."""

    id: str
    name: str
    type: str
    sync_mode: str
    status: str
    created_at: datetime
