"""Celery application (F1): queues, routing extension point, worker defaults.

Broker is Redis; job state stays in MySQL (``ingestion_jobs``/``job_steps``),
so no result backend is configured. Queues exist from day one (``parse``,
``embed``, ``default``) — F2 routes pipeline stages onto them, and a single
worker consumes all three in the MVP deployment.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "ragims",
    broker=settings.redis.url,
    backend=None,  # job state lives in MySQL (ingestion_jobs), not Redis
    include=["app.workers.pipeline", "app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # One delivery, one execution: job state is authoritative in MySQL and
    # re-running a stage is safe by design (E-stage idempotency).
    task_acks_late=False,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    # MVP routing: stages land on dedicated queues; F2 uses these names.
    task_queues={
        "parse": {"exchange": "parse", "routing_key": "parse"},
        "embed": {"exchange": "embed", "routing_key": "embed"},
        "default": {"exchange": "default", "routing_key": "default"},
    },
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",
    # Extension point: task name -> queue. New stages register here.
    task_routes={
        "ragims.parse_document": {"queue": "parse", "routing_key": "parse"},
        "ragims.embed_document": {"queue": "embed", "routing_key": "embed"},
        "ragims.ingest_document": {"queue": "default", "routing_key": "default"},
    },
)
