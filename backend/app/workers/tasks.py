"""Celery task definitions (placeholder — F1 wires the real pipeline).

``ingest_document`` is the dispatch target of C1's upload endpoint. The body
is intentionally empty until stage F; jobs stay ``pending`` in MySQL and the
worker no-ops, which keeps the upload API contract stable from day one.
"""

from __future__ import annotations

from app.core.logging import logger
from app.workers.celery_app import celery_app


@celery_app.task(name="ragims.ingest_document", bind=True, max_retries=0)
def ingest_document(self, doc_version_id: str) -> str:  # noqa: ANN001
    """Placeholder ingestion pipeline (F1 replaces the body)."""
    logger.info(f"[celery] ingest_document placeholder hit: {doc_version_id}")
    return doc_version_id
