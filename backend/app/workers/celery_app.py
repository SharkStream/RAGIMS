"""Celery application factory (minimal placeholder — F1 owns the full setup).

C1 only requires a dispatch point for ``POST /documents/upload``; the task
bodies, queues, and retry policies arrive with stage F. Importing this module
does NOT connect to the broker — connections happen lazily on first publish.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "ragims",
    broker=settings.redis.url,
    backend=None,  # job state lives in MySQL (ingestion_jobs), not Redis
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # F1 will refine routing/retries; keep defaults conservative for now.
    task_acks_late=False,
    worker_prefetch_multiplier=1,
)
