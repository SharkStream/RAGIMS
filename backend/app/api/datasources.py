"""Datasource API routes (C3 — MVP placeholder, ``type=local`` only).

The connector framework (remote sources, sync schedules) is a post-MVP
feature: ``POST`` rejects any type other than ``local`` with 501
``ERR_NOT_IMPLEMENTED`` so the frontend can already render the option set.

C1's upload path auto-associates the tenant's ``default`` datasource (created
by the seed script, lazily re-created by ``document_service`` if missing).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user, get_db
from app.core.errors import ERR_NOT_IMPLEMENTED, AppError
from app.models.datasource import Datasource
from app.schemas.common import ApiResponse, ok
from app.schemas.datasource import DatasourceCreate, DatasourceOut
from app.services.datasource_service import create_local_datasource, list_datasources

router = APIRouter(prefix="/datasources", tags=["datasources"])

#: The only datasource type implemented in the MVP.
SUPPORTED_TYPE = "local"


def _to_out(ds: Datasource) -> DatasourceOut:
    return DatasourceOut(
        id=ds.id,
        name=ds.name,
        type=ds.type,
        sync_mode=ds.sync_mode,
        status=ds.status,
        created_at=ds.created_at,
    )


@router.get(
    "",
    response_model=ApiResponse[list[DatasourceOut]],
    summary="List the tenant's datasources",
)
def list_datasources_route(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[list[DatasourceOut]]:
    """Tenant-scoped, newest first."""
    rows = list_datasources(db, user.tenant_id)
    return ok([_to_out(r) for r in rows])


@router.post(
    "",
    response_model=ApiResponse[DatasourceOut],
    summary="Create a local datasource (other types → 501)",
    status_code=201,
)
def create_datasource_route(
    body: DatasourceCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[DatasourceOut]:
    """MVP accepts only ``type=local``; duplicate names → 409."""
    if body.type != SUPPORTED_TYPE:
        raise AppError(
            f"datasource type {body.type!r} is not implemented "
            f"(MVP supports only '{SUPPORTED_TYPE}')",
            code=ERR_NOT_IMPLEMENTED,
            status_code=501,
            details={"type": body.type, "supported": [SUPPORTED_TYPE]},
        )
    ds = create_local_datasource(db, user.tenant_id, body.name, body.config)
    return ok(_to_out(ds))
