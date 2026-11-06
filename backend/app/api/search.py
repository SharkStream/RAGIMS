"""Search test API (G2).

``POST /search/test`` — management-side retrieval probe. Tenant identity comes
from the authenticated token (not the request body), so cross-tenant leakage
is structurally impossible.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUser, get_current_user
from app.schemas.common import ApiResponse, ok
from app.schemas.search import (
    SearchHit,
    SearchTestRequest,
    SearchTestResponse,
)
from app.services.search_service import search_test

router = APIRouter(prefix="/search", tags=["search"])


@router.post(
    "/test",
    response_model=ApiResponse[SearchTestResponse],
    summary="Retrieval test: embed query + Qdrant search (tenant-scoped)",
)
def search_test_endpoint(
    body: SearchTestRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[SearchTestResponse]:
    result = search_test(
        query=body.query,
        tenant_id=user.tenant_id,
        top_k=body.top_k,
        filters=body.filters,
        role=user.role,
    )
    hits = [
        SearchHit(
            score=h.score,
            text=h.text,
            doc_id=h.doc_id,
            version=h.version,
            page=h.page,
            metadata=h.metadata,
        )
        for h in result.hits
    ]
    return ok(
        SearchTestResponse(
            hits=hits,
            took_embedding_ms=result.took_embedding_ms,
            took_search_ms=result.took_search_ms,
            took_total_ms=result.took_total_ms,
        )
    )
