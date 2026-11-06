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
from typing import Any
from uuid import uuid4

from qdrant_client import models as qmodels
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import (
    ERR_BAD_REQUEST,
    ERR_CONFLICT,
    ERR_DUPLICATE,
    ERR_UNAVAILABLE,
    AppError,
    NotFoundError,
)
from app.core.logging import logger
from app.models.chunk import Chunk
from app.models.datasource import Datasource
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.ingestion_job import IngestionJob
from app.models.job_step import JobStep
from app.models.quality_check import QualityCheck
from app.schemas.document import DocumentPatchRequest
from app.services.parsing_service import parsed_object_key
from app.services.storage import StorageService, get_storage
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
    "md": set(),  # Markdown is plain text: same permissive MIME rule as txt
}

#: Extensions treated as plain text (any "text/*" MIME or no MIME at all).
_TEXT_EXTENSIONS = ("txt", "md")

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
    if ext in _TEXT_EXTENSIONS:
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
        allowed = ", ".join(sorted(ALLOWED_TYPES))
        raise AppError(
            f"unsupported file type: {ext or '(none)'} — allowed: {allowed}",
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


def _find_version_head(
    session: Session, tenant_id: str, file_name: str
) -> Document | None:
    """Live document with the same name, row-locked for version appends (J1).

    ``FOR UPDATE`` serialises concurrent uploads of the same name: the second
    writer blocks until the first commits, then sees the new ``current_version``
    (so it either hits the duplicate path or appends N+1 — never N twice).
    """
    return (
        session.execute(
            select(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.file_name == file_name,
                Document.status != "deleted",
            )
            .with_for_update()
        )
        .scalars()
        .first()
    )


def _is_lock_race(exc: OperationalError) -> bool:
    """MySQL 1213 (deadlock) / 1205 (lock wait timeout) = retryable race."""
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "args", (None,))[0] if orig is not None else None
    return code in (1213, 1205)


def _latest_version_of(session: Session, doc_id: str) -> DocumentVersion | None:
    return session.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.doc_id == doc_id, DocumentVersion.is_latest.is_(True))
        .limit(1)
    ).first()


def _latest_job_of(session: Session, doc_version_id: str) -> IngestionJob | None:
    return session.scalars(
        select(IngestionJob)
        .where(IngestionJob.doc_version_id == doc_version_id)
        .order_by(IngestionJob.created_at.desc())
        .limit(1)
    ).first()


def _duplicate_outcome(
    session: Session,
    doc: Document,
    version: DocumentVersion,
    content_hash: str,
) -> UploadOutcome:
    job = _latest_job_of(session, version.id)
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
    """Validate → hash → resolve target → persist + MinIO + job → dispatch.

    J1 three-way resolution against the row-locked same-name head:

    * no live head → create a new document at v1;
    * head whose latest version has the same hash → idempotent duplicate;
    * head with a different hash → append version N+1 (old latest demoted,
      doc re-enters the pipeline; MinIO paths carry the version segment so
      old objects stay intact).

    A concurrent first-upload of the same name loses the ``active_name``
    unique race (0002 migration), rolls back and re-resolves exactly once —
    closing the I2 SELECT-then-INSERT window at the DB level.
    """
    ext = validate_upload(file_name, mime, len(data), max_bytes=max_bytes)
    content_hash = sha256_hex(data)
    storage = get_storage()

    race_error: Exception | None = None
    for _attempt in range(2):
        head = _find_version_head(session, tenant_id, file_name)

        if head is not None:
            latest = _latest_version_of(session, head.id)
            if latest is not None and latest.content_hash == content_hash:
                return _duplicate_outcome(session, head, latest, content_hash)
            return _append_version(
                session,
                head=head,
                latest=latest,
                ext=ext,
                data=data,
                file_name=file_name,
                content_hash=content_hash,
                user_id=user_id,
                storage=storage,
            )

        try:
            return _create_document(
                session,
                ext=ext,
                data=data,
                file_name=file_name,
                tenant_id=tenant_id,
                user_id=user_id,
                datasource_id=datasource_id,
                title=title,
                content_hash=content_hash,
                storage=storage,
            )
        except IntegrityError as exc:
            # unique (tenant, file_name, active_name): a same-name document
            # appeared between our SELECT and INSERT — re-resolve once, so the
            # loser joins the winner as duplicate/appended version.
            session.rollback()
            race_error = exc
            logger.warning(
                f"upload race on {file_name!r} (concurrent same-name create); re-resolving"
            )
    raise AppError(
        f"concurrent upload race for {file_name!r} could not be resolved",
        code=ERR_DUPLICATE,
        status_code=409,
        details={"file_name": file_name},
    ) from race_error


def _append_version(
    session: Session,
    *,
    head: Document,
    latest: DocumentVersion | None,
    ext: str,
    data: bytes,
    file_name: str,
    content_hash: str,
    user_id: str | None,
    storage: StorageService,
) -> UploadOutcome:
    """Append version N+1 to the row-locked same-name document (J1)."""
    doc_id = head.id
    next_version = head.current_version + 1
    version_id = str(uuid4())
    file_path = f"{settings.minio.bucket_raw}/{head.tenant_id}/{doc_id}/{next_version}/{file_name}"

    try:
        if latest is not None:
            latest.is_latest = False
        version = DocumentVersion(
            id=version_id,
            doc_id=doc_id,
            version=next_version,
            content_hash=content_hash,
            file_path=file_path,
            file_size=len(data),
            parse_status="pending",
            is_latest=True,
        )
        session.add(version)
        head.current_version = next_version
        head.status = "processing"
        session.flush()  # ids/timestamps before the object upload

        bucket, object_name = file_path.split("/", 1)
        storage.objects.upload_file(bucket, object_name, data)

        job = IngestionJob(
            tenant_id=head.tenant_id,
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
        session.rollback()
        logger.error(
            f"append-version tx failed, rolled back: {type(exc).__name__}: {exc}"
        )
        raise AppError(
            f"upload failed while writing storage/db: {type(exc).__name__}",
            code=ERR_UNAVAILABLE,
            status_code=503,
            details={"file_name": file_name},
        ) from exc

    # Upload-grabs-latest semantics (J1/J4 tradeoff): MySQL now points at the
    # new version, so the OLD version's Qdrant points must drop is_latest
    # right away — otherwise retrieval keeps serving stale content while the
    # new version's points are not upserted yet. Best-effort: a failure here
    # is reported by the reconcile drift rule (does not fail the upload).
    try:
        storage.set_payload_by_filter(
            {"is_latest": False},
            qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="tenant_id", match=qmodels.MatchValue(value=head.tenant_id)
                    ),
                    qmodels.FieldCondition(
                        key="doc_id", match=qmodels.MatchValue(value=doc_id)
                    ),
                    qmodels.FieldCondition(
                        key="is_latest", match=qmodels.MatchValue(value=True)
                    ),
                ]
            ),
        )
    except Exception as exc:  # noqa: BLE001 — reconcile will report the drift
        logger.warning(
            f"qdrant demote-latest failed after append: {type(exc).__name__}: {exc}"
        )

    celery_task_id = _dispatch_ingestion(version_id)
    if celery_task_id:
        job.celery_task_id = celery_task_id
        session.commit()

    logger.info(
        f"upload ok (append): doc={doc_id} v{next_version} job={job.id} "
        f"bytes={len(data)} task={celery_task_id or 'n/a'}"
    )
    return UploadOutcome(
        doc_id=doc_id,
        version=next_version,
        job_id=job.id,
        status=head.status,
        duplicate=False,
        file_path=file_path,
        content_hash=content_hash,
    )


def _create_document(
    session: Session,
    *,
    ext: str,
    data: bytes,
    file_name: str,
    tenant_id: str,
    user_id: str | None,
    datasource_id: str | None,
    title: str | None,
    content_hash: str,
    storage: StorageService,
) -> UploadOutcome:
    """Create a fresh document at v1 (the old C1 happy path)."""
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
    except IntegrityError:
        # unique-name race (J1): re-raise for the retry loop in upload_document
        session.rollback()
        raise
    except OperationalError as exc:
        session.rollback()
        if _is_lock_race(exc):
            # gap-lock deadlock / lock-wait between concurrent same-name
            # first uploads (FOR UPDATE on a not-yet-existing row) — let the
            # retry loop re-resolve instead of surfacing a 503.
            raise
        logger.error(f"upload tx failed, rolled back: {type(exc).__name__}: {exc}")
        raise AppError(
            f"upload failed while writing storage/db: {type(exc).__name__}",
            code=ERR_UNAVAILABLE,
            status_code=503,
            details={"file_name": file_name},
        ) from exc
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


def list_document_versions(
    session: Session,
    tenant_id: str,
    doc_id: str,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[DocumentVersion], int]:
    """Version history of a document, newest first (J2)."""
    doc = get_document_or_404(session, tenant_id, doc_id)
    scope = DocumentVersion.doc_id == doc.id
    total = session.scalar(
        select(func.count()).select_from(DocumentVersion).where(scope)
    )
    rows = session.scalars(
        select(DocumentVersion)
        .where(scope)
        .order_by(DocumentVersion.version.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), int(total or 0)


def update_document_meta(
    session: Session,
    tenant_id: str,
    doc_id: str,
    patch: DocumentPatchRequest,
    *,
    storage: StorageService | None = None,
) -> Document:
    """Metadata-only update (J3): touches ONE ``documents`` row.

    No job, no chunk rewrite, no re-embedding, no worker import. Deleted
    documents are immutable (409); ``null`` fields are skipped (no clearing
    of ``title``); ``tags`` replaces the whole list (``[]`` clears it).

    K4: an ``access_level`` change also rewrites the level on ALL Qdrant
    points of the document (flush → payload flip → commit, J4 semantics:
    503 + rollback when Qdrant is unreachable).
    """
    doc = session.get(Document, doc_id)
    if doc is None or doc.tenant_id != tenant_id:
        raise NotFoundError(f"document {doc_id} not found")
    if doc.status == "deleted":
        # Deleted documents stay visible to PATCH only as a 409 state conflict
        # (J3): they exist but are immutable, unlike list/detail which hide them.
        raise AppError(
            f"document {doc.id} is deleted and cannot be modified",
            code=ERR_CONFLICT,
            status_code=409,
            details={"doc_id": doc.id},
        )

    fields = {
        k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None
    }
    if not fields:
        raise AppError(
            "no updatable field provided (null values are skipped)",
            code=ERR_BAD_REQUEST,
            status_code=400,
        )

    if "datasource_id" in fields:
        ds = session.get(Datasource, fields["datasource_id"])
        if ds is None or ds.tenant_id != tenant_id:
            raise NotFoundError(
                f"datasource {fields['datasource_id']} not found in tenant {tenant_id}"
            )

    level_changed = "access_level" in fields and str(fields["access_level"]) != str(
        doc.access_level
    )

    if not level_changed:
        for key, value in fields.items():
            setattr(doc, key, value)
        session.commit()
        logger.info(f"document meta updated: {doc.id} fields={sorted(fields)}")
        return doc

    storage = storage or get_storage()
    new_level = str(fields["access_level"])
    level_filter = qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="tenant_id", match=qmodels.MatchValue(value=tenant_id)
            ),
            qmodels.FieldCondition(
                key="doc_id", match=qmodels.MatchValue(value=doc.id)
            ),
        ]
    )
    try:
        for key, value in fields.items():
            setattr(doc, key, value)
        session.flush()  # staged; committed only after Qdrant agrees

        # K4: the level is enforced at retrieval time from point payloads,
        # so every version's points must carry the new value immediately.
        storage.set_payload_by_filter({"access_level": new_level}, level_filter)
        session.commit()
    except AppError:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()  # MySQL stays untouched when Qdrant is down
        logger.error(
            f"access_level sync failed, rolled back: {type(exc).__name__}: {exc}"
        )
        raise AppError(
            f"access_level sync failed: {type(exc).__name__}",
            code=ERR_UNAVAILABLE,
            status_code=503,
            details={"doc_id": doc.id, "access_level": new_level},
        ) from exc
    logger.info(f"document meta updated: {doc.id} fields={sorted(fields)}")
    return doc


def get_document_version(
    session: Session, tenant_id: str, doc_id: str, version: int
) -> DocumentVersion:
    """One version by in-document ordinal (``version`` is not a global ID).

    404 when the document is missing/other-tenant **or** the ordinal does not
    exist for it (J2).
    """
    doc = get_document_or_404(session, tenant_id, doc_id)
    row = session.scalars(
        select(DocumentVersion).where(
            DocumentVersion.doc_id == doc.id,
            DocumentVersion.version == version,
        )
    ).first()
    if row is None:
        raise NotFoundError(f"version {version} not found for document {doc.id}")
    return row


def _tenant_live_doc(session: Session, tenant_id: str, doc_id: str) -> Document:
    """Document lookup that also sees deleted rows (J3/J4 state semantics)."""
    doc = session.get(Document, doc_id)
    if doc is None or doc.tenant_id != tenant_id:
        raise NotFoundError(f"document {doc_id} not found")
    return doc


def activate_document_version(
    session: Session,
    tenant_id: str,
    doc_id: str,
    version: int,
    *,
    storage: StorageService | None = None,
) -> Document:
    """Activate a historical version as latest — instant rollback (J4).

    MySQL pointer flip + Qdrant payload flip (demote current, promote target,
    tenant-scoped filters), zero parsing / embedding / object ops. The MySQL
    transaction commits only after both Qdrant writes succeed; a Qdrant
    failure rolls back everything and surfaces 503 ``ERR_UNAVAILABLE``.
    """
    storage = storage or get_storage()
    doc = _tenant_live_doc(session, tenant_id, doc_id)
    if doc.status == "deleted":
        raise AppError(
            f"document {doc.id} is deleted and cannot be modified",
            code=ERR_CONFLICT,
            status_code=409,
            details={"doc_id": doc.id},
        )
    target = session.scalars(
        select(DocumentVersion).where(
            DocumentVersion.doc_id == doc.id,
            DocumentVersion.version == version,
        )
    ).first()
    if target is None:
        raise NotFoundError(f"version {version} not found for document {doc.id}")
    if target.is_latest:
        logger.info(f"activate no-op: v{version} already latest for {doc.id}")
        return doc
    if target.parse_status != "parsed":
        raise AppError(
            f"version {version} is not parsed yet (status={target.parse_status})",
            code=ERR_CONFLICT,
            status_code=409,
            details={
                "doc_id": doc.id,
                "version": version,
                "parse_status": target.parse_status,
            },
        )

    demote_filter = qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="tenant_id", match=qmodels.MatchValue(value=tenant_id)
            ),
            qmodels.FieldCondition(
                key="doc_id", match=qmodels.MatchValue(value=doc.id)
            ),
            qmodels.FieldCondition(
                key="is_latest", match=qmodels.MatchValue(value=True)
            ),
        ]
    )
    promote_filter = qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="tenant_id", match=qmodels.MatchValue(value=tenant_id)
            ),
            qmodels.FieldCondition(
                key="doc_id", match=qmodels.MatchValue(value=doc.id)
            ),
            qmodels.FieldCondition(
                key="version", match=qmodels.MatchValue(value=version)
            ),
        ]
    )

    try:
        previous = _latest_version_of(session, doc.id)
        if previous is not None:
            previous.is_latest = False
        target.is_latest = True
        doc.current_version = version
        doc.status = "succeeded"
        session.flush()  # staged; committed only after Qdrant agrees

        # Qdrant payload flip: demote first so the two versions never both
        # match is_latest=true (seconds-level retrieval gap is accepted, J4).
        storage.set_payload_by_filter({"is_latest": False}, demote_filter)
        storage.set_payload_by_filter({"is_latest": True}, promote_filter)
        session.commit()
    except AppError:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()  # MySQL stays untouched when Qdrant is down
        logger.error(f"activate failed, rolled back: {type(exc).__name__}: {exc}")
        raise AppError(
            f"version activation failed: {type(exc).__name__}",
            code=ERR_UNAVAILABLE,
            status_code=503,
            details={"doc_id": doc.id, "version": version},
        ) from exc

    logger.info(
        f"version activated: doc={doc.id} v{version} "
        f"(rollback from v{previous.version if previous else 'n/a'})"
    )
    return doc


def list_document_quality(
    session: Session, tenant_id: str, doc_id: str
) -> list[dict[str, Any]]:
    """Quality-check rows for a document, latest version first (L2 read side).

    Each item carries the version ordinal so the dashboard can show per-version
    trends; versions without checks are simply absent from the output.
    """
    doc = get_document_or_404(session, tenant_id, doc_id)
    rows = session.execute(
        select(QualityCheck, DocumentVersion.version)
        .join(DocumentVersion, QualityCheck.doc_version_id == DocumentVersion.id)
        .where(DocumentVersion.doc_id == doc.id)
        .order_by(DocumentVersion.version.desc(), QualityCheck.check_type)
    ).all()
    return [
        {
            "version": version,
            "doc_version_id": check.doc_version_id,
            "check_type": check.check_type,
            "score": float(check.score),
            "detail": check.detail,
            "created_at": check.created_at,
        }
        for check, version in rows
    ]


def delete_document_version(
    session: Session,
    tenant_id: str,
    doc_id: str,
    version: int,
    *,
    storage: StorageService | None = None,
) -> DocumentVersion:
    """Version-level reclaim (J4): chunks + points + objects, physically.

    The current latest version cannot be deleted (409) — soft-delete the
    whole document instead. No trash table: MVP2 treats a deleted version as
    gone (re-upload the file to get it back).
    """
    storage = storage or get_storage()
    doc = _tenant_live_doc(session, tenant_id, doc_id)
    row = session.scalars(
        select(DocumentVersion).where(
            DocumentVersion.doc_id == doc.id,
            DocumentVersion.version == version,
        )
    ).first()
    if row is None:
        raise NotFoundError(f"version {version} not found for document {doc.id}")
    if row.is_latest or row.version == doc.current_version:
        raise AppError(
            f"version {version} is the current latest and cannot be deleted",
            code=ERR_CONFLICT,
            status_code=409,
            details={"doc_id": doc.id, "version": version},
        )

    try:
        deleted_chunks = (
            session.scalar(
                select(func.count())
                .select_from(Chunk)
                .where(Chunk.doc_version_id == row.id)
            )
            or 0
        )
        # reclaim this version's job trail too — ingestion_jobs.doc_version_id
        # is a FK, and a reclaimed version has no trash table to keep it (J4).
        job_ids = session.scalars(
            select(IngestionJob.id).where(IngestionJob.doc_version_id == row.id)
        ).all()
        for jid in job_ids:
            session.execute(sa_delete(JobStep).where(JobStep.job_id == jid))
        session.execute(
            sa_delete(IngestionJob).where(IngestionJob.doc_version_id == row.id)
        )
        session.execute(sa_delete(Chunk).where(Chunk.doc_version_id == row.id))
        session.flush()
        storage.delete_points_by_filter(
            qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="doc_version_id",
                        match=qmodels.MatchValue(value=row.id),
                    )
                ]
            )
        )
        storage.delete_raw_document(row.file_path)
        parsed_bucket = settings.minio.bucket_parsed
        storage.objects.delete_object(
            parsed_bucket, parsed_object_key(row.id).split("/", 1)[1]
        )
        session.delete(row)
        session.commit()
    except AppError:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        logger.error(f"version delete failed, rolled back: {type(exc).__name__}: {exc}")
        raise AppError(
            f"version deletion failed: {type(exc).__name__}",
            code=ERR_UNAVAILABLE,
            status_code=503,
            details={"doc_id": doc.id, "version": version},
        ) from exc

    logger.info(
        f"version deleted: doc={doc.id} v{version} chunks={deleted_chunks} "
        f"(points + objects reclaimed)"
    )
    return row


def list_version_chunks(
    session: Session,
    tenant_id: str,
    doc_id: str,
    version: int,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Chunk], int]:
    """Chunks of an **arbitrary** version — history preview (J2)."""
    row = get_document_version(session, tenant_id, doc_id, version)
    scope = Chunk.doc_version_id == row.id
    total = session.scalar(select(func.count()).select_from(Chunk).where(scope))
    rows = session.scalars(
        select(Chunk)
        .where(scope)
        .order_by(Chunk.chunk_index)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), int(total or 0)


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


# --------------------------------------------------------------------------- #
# F3 · reprocess + cancel
# --------------------------------------------------------------------------- #


def reprocess_document(
    session: Session,
    tenant_id: str,
    doc_id: str,
    *,
    user_id: str | None = None,
) -> UploadOutcome:
    """Create a fresh ``reprocess`` job for the latest version and dispatch it.

    Reuses the latest version's stored raw file — no re-upload needed. The
    pipeline is idempotent end-to-end (F2), so a duplicate reprocess is safe.
    """
    doc = get_document_or_404(session, tenant_id, doc_id)
    version = session.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.doc_id == doc.id, DocumentVersion.is_latest.is_(True))
        .order_by(DocumentVersion.version.desc())
        .limit(1)
    ).first()
    if version is None:
        raise NotFoundError(f"document {doc_id} has no version to reprocess")

    job = IngestionJob(
        tenant_id=tenant_id,
        doc_id=doc.id,
        doc_version_id=version.id,
        job_type="reprocess",
        status="pending",
        created_by=user_id,
    )
    session.add(job)
    session.commit()

    celery_task_id = _dispatch_ingestion(str(version.id))
    if celery_task_id:
        job.celery_task_id = celery_task_id
        session.commit()
    logger.info(
        f"reprocess dispatched: doc={doc.id} v{version.version} job={job.id} "
        f"task={celery_task_id or 'n/a'}"
    )
    return UploadOutcome(
        doc_id=doc.id,
        version=version.version,
        job_id=job.id,
        status=doc.status,
        duplicate=False,
        file_path=version.file_path,
        content_hash=version.content_hash,
    )


_CANCELABLE = ("pending", "running")


def cancel_job(session: Session, tenant_id: str, job_id: str) -> IngestionJob:
    """Mark a pending/running job ``cancelled`` (MVP cooperative cancel, F3).

    The worker recognizes the flag before each step (see
    :func:`app.workers.base.record_step`); steps already finished stay.
    Cancelling a terminal job is a 409.
    """
    job = session.get(IngestionJob, job_id)
    if job is None or job.tenant_id != tenant_id:
        raise NotFoundError(f"job {job_id} not found")
    if job.status not in _CANCELABLE:
        raise AppError(
            f"job {job_id} is {job.status} and cannot be cancelled",
            code="ERR_CONFLICT",
            status_code=409,
            details={"job_id": job_id, "status": job.status},
        )
    job.status = "cancelled"
    session.commit()
    logger.info(f"job cancelled: {job_id} (was {job.status})")
    return job
