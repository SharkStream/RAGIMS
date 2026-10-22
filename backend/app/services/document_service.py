"""Document upload business logic (C1 step 4).

Flow for ``POST /documents/upload``::

    validate → sha256 → idempotency lookup (tenant + file_name + hash)
    → [tx] documents + document_versions + MinIO upload + ingestion_jobs → commit
    → dispatch Celery task → persist celery_task_id

Idempotency: an upload whose ``(tenant_id, file_name, content_hash)`` matches
the latest version of a non-deleted document returns the existing records with
``duplicate=True`` — no new rows, no MinIO write, no Celery dispatch. Same
content under a *different* file name is treated as an intentional upload
(per-user copy), not a duplicate.

Error mapping (see ``app.core.errors``): unsupported type → 415, oversize →
413, unknown datasource → 404, MinIO/Redis failure → 503, other surprises →
the global handler's 500 envelope. The metadata transaction rolls back on any
MinIO failure, so a rejected upload leaves zero rows and zero objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ERR_UNAVAILABLE, AppError, NotFoundError
from app.core.logging import logger
from app.models.chunk import Chunk
from app.models.datasource import Datasource
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.ingestion_job import IngestionJob
from app.services.storage import get_storage
from app.utils.hashing import sha256_hex

#: ext → allowed MIME types (client-reported; extension is the primary check).
ALLOWED_TYPES: dict[str, set[str]] = {
    "pdf": {"application/pdf"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/x-zip-compressed",
    },
    "txt": set(),  # any "text/*" or octet-stream; see _mime_ok
}

#: Sentinel MIME browsers send when they cannot tell (treated as unknown).
_GENERIC_MIME = "application/octet-stream"


@dataclass(slots=True)
class UploadOutcome:
    """Result of an upload — mirrors ``DocumentUploadResponse`` fields."""

    doc_id: str
    version: int
    job_id: str
    status: str
    duplicate: bool
    file_path: str
    content_hash: str


def _mime_ok(ext: str, mime: str | None) -> bool:
    if not mime or mime == _GENERIC_MIME:
        return True
    if ext == "txt":
        return mime.startswith("text/")
    return mime in ALLOWED_TYPES[ext]


def validate_upload(
    file_name: str,
    mime: str | None,
    size_bytes: int,
    *,
    max_bytes: int | None = None,
) -> str:
    """Check extension + MIME + size; return the normalized extension.

    Raises :class:`AppError` with stable codes (415/413) so the global handler
    emits a machine-readable envelope.
    """
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    if ext not in ALLOWED_TYPES:
        raise AppError(
            f"unsupported file type: {ext or '(none)'} — allowed: pdf, docx, txt",
            code="ERR_FILE_TYPE_NOT_ALLOWED",
            status_code=415,
            details={"file_type": ext, "allowed": sorted(ALLOWED_TYPES)},
        )
    if not _mime_ok(ext, mime):
        raise AppError(
            f"MIME type {mime!r} does not match .{ext} files",
            code="ERR_FILE_TYPE_NOT_ALLOWED",
            status_code=415,
            details={"file_type": ext, "mime": mime},
        )
    limit = settings.app.upload_max_mb * 1024 * 1024 if max_bytes is None else max_bytes
    if size_bytes <= 0:
        raise AppError(
            "empty file",
            code="ERR_FILE_TOO_LARGE",
            status_code=413,
            details={"size_bytes": size_bytes},
        )
    if size_bytes > limit:
        raise AppError(
            f"file too large: {size_bytes} bytes (limit {limit})",
            code="ERR_FILE_TOO_LARGE",
            status_code=413,
            details={"size_bytes": size_bytes, "limit_bytes": limit},
        )
    return ext


def _get_or_create_default_datasource(session: Session, tenant_id: str) -> Datasource:
    """Return the tenant's ``default`` datasource, creating it on first use."""
    ds = session.scalars(
        select(Datasource).where(
            Datasource.tenant_id == tenant_id, Datasource.name == "default"
        )
    ).first()
    if ds is None:
        ds = Datasource(tenant_id=tenant_id, name="default", type="local")
        session.add(ds)
        session.flush()
        logger.info(f"created default datasource {ds.id} for tenant {tenant_id}")
    return ds


def _find_duplicate(
    session: Session, tenant_id: str, file_name: str, content_hash: str
) -> tuple[Document, DocumentVersion, IngestionJob | None] | None:
    """Latest non-deleted version of (tenant, file_name) with the same hash."""
    row = session.execute(
        select(Document, DocumentVersion)
        .join(DocumentVersion, DocumentVersion.doc_id == Document.id)
        .where(
            Document.tenant_id == tenant_id,
            Document.file_name == file_name,
            Document.status != "deleted",
            DocumentVersion.content_hash == content_hash,
            DocumentVersion.is_latest.is_(True),
        )
        .order_by(DocumentVersion.version.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    doc, version = row
    job = session.scalars(
        select(IngestionJob)
        .where(IngestionJob.doc_version_id == version.id)
        .order_by(IngestionJob.created_at.desc())
        .limit(1)
    ).first()
    return doc, version, job


def _dispatch_ingestion(doc_version_id: str) -> str | None:
    """Publish the Celery task; return its id, or None when broker is down.

    Import inside the function so unit tests / offline tooling never need a
    broker just to import the service module.
    """
    try:
        from app.workers.tasks import ingest_document

        return ingest_document.delay(doc_version_id).id
    except Exception as exc:  # noqa: BLE001 — broker down must not fail the upload
        logger.warning(
            f"celery dispatch failed (job stays pending, F1 will re-drive): "
            f"{type(exc).__name__}: {exc}"
        )
        return None


def upload_document(
    session: Session,
    *,
    data: bytes,
    file_name: str,
    mime: str | None = None,
    tenant_id: str,
    user_id: str | None = None,
    datasource_id: str | None = None,
    title: str | None = None,
    max_bytes: int | None = None,
) -> UploadOutcome:
    """Validate → hash → (idempotent?) → persist + MinIO + job → dispatch."""
    ext = validate_upload(file_name, mime, len(data), max_bytes=max_bytes)
    content_hash = sha256_hex(data)

    hit = _find_duplicate(session, tenant_id, file_name, content_hash)
    if hit is not None:
        doc, version, job = hit
        logger.info(
            f"idempotent upload hit: doc={doc.id} v{version.version} "
            f"(hash {content_hash[:12]}…)"
        )
        return UploadOutcome(
            doc_id=doc.id,
            version=version.version,
            job_id=job.id if job else "",
            status=doc.status,
            duplicate=True,
            file_path=version.file_path,
            content_hash=content_hash,
        )

    if datasource_id is not None:
        ds = session.get(Datasource, datasource_id)
        if ds is None or ds.tenant_id != tenant_id:
            raise NotFoundError(
                f"datasource {datasource_id} not found in tenant {tenant_id}"
            )
    else:
        ds = _get_or_create_default_datasource(session, tenant_id)

    doc_id = str(uuid4())
    version_id = str(uuid4())
    file_path = f"{settings.minio.bucket_raw}/{tenant_id}/{doc_id}/1/{file_name}"
    storage = get_storage()

    # One metadata transaction (session autobegin): MinIO failure triggers
    # rollback so a rejected upload leaves zero rows and zero objects (C1 §5).
    try:
        document = Document(
            id=doc_id,
            tenant_id=tenant_id,
            datasource_id=ds.id,
            title=title or file_name.rsplit(".", 1)[0],
            file_name=file_name,
            file_type=ext,
            status="processing",
            current_version=1,
        )
        version = DocumentVersion(
            id=version_id,
            doc_id=doc_id,
            version=1,
            content_hash=content_hash,
            file_path=file_path,
            file_size=len(data),
            parse_status="pending",
            is_latest=True,
        )
        session.add_all([document, version])
        session.flush()  # ids/timestamps before the object upload

        bucket, object_name = file_path.split("/", 1)
        storage.objects.upload_file(bucket, object_name, data)

        job = IngestionJob(
            tenant_id=tenant_id,
            doc_id=doc_id,
            doc_version_id=version_id,
            job_type="full",
            status="pending",
            created_by=user_id,
        )
        session.add(job)
        session.commit()
    except AppError:
        session.rollback()
        raise
    except Exception as exc:
        # MinIO/DB failure inside the tx (C1 §5): roll back and surface a
        # machine-readable 503 so the caller can retry later.
        session.rollback()
        logger.error(f"upload tx failed, rolled back: {type(exc).__name__}: {exc}")
        raise AppError(
            f"upload failed while writing storage/db: {type(exc).__name__}",
            code=ERR_UNAVAILABLE,
            status_code=503,
            details={"file_name": file_name},
        ) from exc

    celery_task_id = _dispatch_ingestion(version_id)
    if celery_task_id:
        job.celery_task_id = celery_task_id
        session.commit()

    logger.info(
        f"upload ok: doc={doc_id} v1 job={job.id} bytes={len(data)} "
        f"task={celery_task_id or 'n/a'}"
    )
    return UploadOutcome(
        doc_id=doc_id,
        version=1,
        job_id=job.id,
        status=document.status,
        duplicate=False,
        file_path=file_path,
        content_hash=content_hash,
    )


# --------------------------------------------------------------------------- #
# C2 · queries + soft delete
# --------------------------------------------------------------------------- #


def get_document_or_404(session: Session, tenant_id: str, doc_id: str) -> Document:
    """Tenant-scoped document lookup; soft-deleted docs read as 404."""
    doc = session.get(Document, doc_id)
    if doc is None or doc.tenant_id != tenant_id or doc.status == "deleted":
        raise NotFoundError(f"document {doc_id} not found")
    return doc


def list_documents(
    session: Session,
    tenant_id: str,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    file_type: str | None = None,
    keyword: str | None = None,
) -> tuple[list[Document], int]:
    """Filtered/paginated document list; default excludes soft-deleted.

    The mandatory ``tenant_id`` predicate drives the composite index
    ``idx_documents_tenant_status (tenant_id, status)``.
    """
    conditions = [Document.tenant_id == tenant_id]
    if status is None:
        conditions.append(Document.status != "deleted")
    else:
        conditions.append(Document.status == status)
    if file_type is not None:
        conditions.append(Document.file_type == file_type)
    if keyword:
        like = f"%{keyword}%"
        conditions.append(Document.title.like(like) | Document.file_name.like(like))

    total = session.scalar(
        select(func.count()).select_from(Document).where(*conditions)
    )
    rows = session.scalars(
        select(Document)
        .where(*conditions)
        .order_by(Document.created_at.desc(), Document.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), int(total or 0)


def get_latest_version(session: Session, doc_id: str) -> DocumentVersion | None:
    """The ``is_latest=true`` version of a document (may be None pre-parse)."""
    return session.scalars(
        select(DocumentVersion)
        .where(
            DocumentVersion.doc_id == doc_id,
            DocumentVersion.is_latest.is_(True),
        )
        .order_by(DocumentVersion.version.desc())
        .limit(1)
    ).first()


def list_document_chunks(
    session: Session,
    tenant_id: str,
    doc_id: str,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Chunk], int]:
    """Chunks of the document's **current** version, ordered by chunk_index.

    404-scoped on the document; an existing document without any parsed
    version simply returns an empty page.
    """
    doc = get_document_or_404(session, tenant_id, doc_id)
    version = session.scalars(
        select(DocumentVersion).where(
            DocumentVersion.doc_id == doc.id,
            DocumentVersion.version == doc.current_version,
        )
    ).first()
    if version is None:
        return [], 0
    base = select(Chunk).where(Chunk.doc_version_id == version.id)
    total = session.scalar(
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.doc_version_id == version.id)
    )
    rows = session.scalars(
        base.order_by(Chunk.chunk_index).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(rows), int(total or 0)


def soft_delete_document(session: Session, tenant_id: str, doc_id: str) -> Document:
    """MVP soft delete: ``status='deleted'`` + versions marked ``is_deleted``."""
    doc = get_document_or_404(session, tenant_id, doc_id)
    doc.status = "deleted"
    session.execute(
        sa_update(DocumentVersion)
        .where(DocumentVersion.doc_id == doc.id)
        .values(is_deleted=True)
    )
    session.commit()
    logger.info(f"document soft-deleted: {doc.id}")
    return doc
