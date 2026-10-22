"""Parsing pipeline service (D2 step 4-5).

``parse_and_store`` is the unit of work stage F's Celery task will call::

    download raw file (MinIO) → dispatch by file_type (registry)
    → success: parsed result → parsed-text/{doc_version_id}.json,
       document_versions.parse_status='parsed'
    → failure: parse_status='failed' + a failed job_steps row whose
       ``error_message`` carries a traceback summary (F surfaces it in the UI)

The service keeps parser invocations side-effect-free and owns every write,
so ``parse_bytes`` stays unit-testable (see tests/test_d2_parsers.py).
"""

from __future__ import annotations

import json
import traceback

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.ingestion_job import IngestionJob
from app.models.job_step import JobStep
from app.parsers.base import ParsedDocument
from app.parsers.registry import get_parser
from app.services.storage import get_storage

#: Cap for the error summary persisted into ``job_steps.error_message``.
_ERROR_SUMMARY_CHARS = 2000

_PARSE_STEP_ORDER = 1
_PARSE_STEP_NAME = "parse"


def parsed_object_key(doc_version_id: str) -> str:
    """``parsed-text/{doc_version_id}.json`` (D2 step 4 convention)."""
    return f"parsed-text/{doc_version_id}.json"


def _error_summary(exc: Exception) -> str:
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    return "".join(tb)[-_ERROR_SUMMARY_CHARS:]


def _load_version(session: Session, doc_version_id: str) -> DocumentVersion:
    version = session.get(DocumentVersion, doc_version_id)
    if version is None:
        raise NotFoundError(f"document version {doc_version_id} not found")
    return version


def _latest_job(session: Session, doc_version_id: str) -> IngestionJob | None:
    return session.scalars(
        select(IngestionJob)
        .where(IngestionJob.doc_version_id == doc_version_id)
        .order_by(IngestionJob.created_at.desc())
        .limit(1)
    ).first()


def parse_and_store(session: Session, doc_version_id: str) -> ParsedDocument:
    """Parse the version's raw file and persist the result; raises on failure.

    Failure path (D2 step 5): ``parse_status='failed'`` + a failed
    ``job_steps`` row with the traceback summary, then the original exception
    propagates (stage F decides the task-level retry semantics).
    """
    version = _load_version(session, doc_version_id)
    doc = session.get(Document, version.doc_id)
    if doc is None:  # pragma: no cover - FK guarantees existence
        raise NotFoundError(f"document {version.doc_id} not found")

    storage = get_storage()
    raw = storage.read_raw_document(version.file_path)

    try:
        parsed = get_parser(doc.file_type).parse_bytes(raw)
    except Exception as exc:
        _mark_failed(session, version, exc)
        raise

    payload = json.dumps(
        {
            "text": parsed.text,
            "blocks": [
                {
                    "text": b.text,
                    "page": b.page,
                    "block_type": b.block_type,
                }
                for b in parsed.blocks
            ],
            "metadata": parsed.metadata,
            "doc_version_id": doc_version_id,
            "file_type": doc.file_type,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    key = parsed_object_key(doc_version_id)
    bucket, object_name = key.split("/", 1)
    storage.objects.ensure_bucket(bucket)
    storage.objects.upload_file(bucket, object_name, payload)

    version.parse_status = "parsed"
    session.commit()
    logger.info(
        f"parsed version {doc_version_id} ({doc.file_type}, {len(parsed.blocks)} "
        f"blocks) -> {key}"
    )
    return parsed


def _mark_failed(session: Session, version: DocumentVersion, exc: Exception) -> None:
    """Best-effort failure write-out; never masks the original error."""
    summary = _error_summary(exc)
    logger.error(f"parsing failed for version {version.id}: {type(exc).__name__}")
    try:
        version.parse_status = "failed"
        job = _latest_job(session, version.id)
        if job is not None:
            session.add(
                JobStep(
                    job_id=job.id,
                    step_order=_PARSE_STEP_ORDER,
                    step_name=_PARSE_STEP_NAME,
                    status="failed",
                    error_message=summary,
                )
            )
        session.commit()
    except Exception as write_exc:  # noqa: BLE001 — don't mask the parse error
        session.rollback()
        logger.error(f"failed to persist parse failure state: {write_exc!r}")
