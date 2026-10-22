"""Document API routes (C1 upload, C2 query/soft-delete).

``POST /documents/upload`` — multipart upload of pdf/docx/txt (≤ 50 MB by
default), validated then persisted by :mod:`app.services.document_service`.

C2 adds the read side: list (filter/search/paginate), detail (+ latest
version), chunk list of the current version, and MVP soft delete.

The routes stay thin: they forward to the service inside the request-scoped
session and wrap results in the unified ``ApiResponse`` envelope. All error
mapping (415/413/404/409/503) is done by the service + the global handlers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user, get_db
from app.schemas.common import ApiResponse, PageResult, ok
from app.schemas.document import (
    ChunkOut,
    DocumentDeleteResponse,
    DocumentDetail,
    DocumentOut,
    DocumentUploadResponse,
    DocumentVersionOut,
)
from app.services.document_service import (
    get_document_or_404,
    get_latest_version,
    list_document_chunks,
    list_documents,
    soft_delete_document,
    upload_document,
)

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.document_version import DocumentVersion

router = APIRouter(prefix="/documents", tags=["documents"])

#: Hard read cap: generous vs. the configured limit so oversize files are
#: rejected by the service with a precise ERR_FILE_TOO_LARGE envelope (a
#: 413 from the service carries a stable code the frontend can branch on).
_READ_CAP_MB = 200


@router.post(
    "/upload",
    response_model=ApiResponse[DocumentUploadResponse],
    summary="Upload a document (pdf/docx/txt, idempotent on content hash)",
    status_code=201,
)
def upload(
    file: Annotated[UploadFile, File(description="pdf / docx / txt file")],
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    datasource_id: Annotated[
        str | None, Form(description="optional datasource; defaults to tenant default")
    ] = None,
    title: Annotated[str | None, Form(description="optional display title")] = None,
) -> ApiResponse[DocumentUploadResponse]:
    """Validate → hash → persist + MinIO → enqueue ingestion job."""
    filename = file.filename or "unnamed"
    cap = _READ_CAP_MB * 1024 * 1024
    data = file.file.read(cap + 1)
    if len(data) > cap:  # pragma: no cover - guard for absurd payloads
        from app.core.errors import AppError

        raise AppError(
            f"file exceeds {_READ_CAP_MB} MB read cap",
            code="ERR_FILE_TOO_LARGE",
            status_code=413,
        )

    outcome = upload_document(
        db,
        data=data,
        file_name=filename,
        mime=file.content_type,
        tenant_id=user.tenant_id,
        user_id=user.id,
        datasource_id=datasource_id,
        title=title,
    )
    return ok(
        DocumentUploadResponse(
            doc_id=outcome.doc_id,
            version=outcome.version,
            job_id=outcome.job_id,
            status=outcome.status,
            duplicate=outcome.duplicate,
            file_path=outcome.file_path,
            content_hash=outcome.content_hash,
        )
    )


# --------------------------------------------------------------------------- #
# C2 · query + soft delete
# --------------------------------------------------------------------------- #


def _to_out(doc: Document) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        title=doc.title,
        file_name=doc.file_name,
        file_type=doc.file_type,
        status=doc.status,
        current_version=doc.current_version,
        datasource_id=doc.datasource_id,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _to_version_out(v: DocumentVersion) -> DocumentVersionOut:
    return DocumentVersionOut(
        id=v.id,
        version=v.version,
        content_hash=v.content_hash,
        file_path=v.file_path,
        file_size=v.file_size,
        parse_status=v.parse_status,
        chunk_count=v.chunk_count,
        is_latest=v.is_latest,
        created_at=v.created_at,
    )


@router.get(
    "",
    response_model=ApiResponse[PageResult[DocumentOut]],
    summary="List documents (filter / search / paginate; excludes deleted)",
)
def list_docs(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1, description="1-based page")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Annotated[
        str | None, Query(description="exact status filter (e.g. processing)")
    ] = None,
    file_type: Annotated[
        str | None, Query(description="exact file type: pdf / docx / txt")
    ] = None,
    keyword: Annotated[
        str | None, Query(description="LIKE search on title / file_name")
    ] = None,
) -> ApiResponse[PageResult[DocumentOut]]:
    """Tenant-scoped list; soft-deleted docs stay hidden unless asked for."""
    rows, total = list_documents(
        db,
        user.tenant_id,
        page=page,
        page_size=page_size,
        status=status,
        file_type=file_type,
        keyword=keyword,
    )
    return ok(
        PageResult.of(
            [_to_out(r) for r in rows], total=total, page=page, page_size=page_size
        )
    )


@router.get(
    "/{doc_id}",
    response_model=ApiResponse[DocumentDetail],
    summary="Document detail with its latest version",
)
def get_doc(
    doc_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[DocumentDetail]:
    """404 (``ERR_NOT_FOUND``) when missing / other tenant / soft-deleted."""
    doc = get_document_or_404(db, user.tenant_id, doc_id)
    version = get_latest_version(db, doc.id)
    return ok(
        DocumentDetail(
            **_to_out(doc).model_dump(),
            latest_version=(_to_version_out(version) if version is not None else None),
        )
    )


@router.get(
    "/{doc_id}/chunks",
    response_model=ApiResponse[PageResult[ChunkOut]],
    summary="Chunks of the current version, ordered by chunk_index",
)
def get_chunks(
    doc_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ApiResponse[PageResult[ChunkOut]]:
    """Ordered pagination over ``chunks(doc_version_id, chunk_index)``."""
    rows, total = list_document_chunks(
        db, user.tenant_id, doc_id, page=page, page_size=page_size
    )
    items = [
        ChunkOut(
            chunk_index=c.chunk_index,
            text=c.text,
            token_count=c.token_count,
            page=c.page,
            section=c.section,
        )
        for c in rows
    ]
    return ok(PageResult.of(items, total=total, page=page, page_size=page_size))


@router.delete(
    "/{doc_id}",
    response_model=ApiResponse[DocumentDeleteResponse],
    summary="Soft delete (status=deleted; async object cleanup is out of MVP)",
)
def delete_doc(
    doc_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[DocumentDeleteResponse]:
    """Marks the document deleted; list/detail treat it as nonexistent."""
    doc = soft_delete_document(db, user.tenant_id, doc_id)
    return ok(DocumentDeleteResponse(doc_id=doc.id, status=doc.status))
