"""Read-only effective settings (H5 settings page)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user, get_db
from app.schemas.common import ApiResponse, ok
from app.schemas.settings import EffectiveSettings
from app.services.settings_service import get_effective_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get(
    "/effective",
    response_model=ApiResponse[EffectiveSettings],
    summary="Effective settings: default embedding model + chunking (read-only)",
)
def read_effective_settings(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[EffectiveSettings]:
    """H5: the settings page renders this verbatim; no mutation endpoints here."""
    return ok(get_effective_settings(db))
