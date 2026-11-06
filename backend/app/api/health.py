"""Infrastructure health endpoints (plain JSON — NOT the ApiResponse envelope,
so LB / docker / orchestrator probes can consume them directly).

* ``GET /healthz`` — liveness: process is up, no external dependency touched.
* ``GET /readyz``  — readiness: probes MySQL / Redis / Qdrant; any failure
  responds 503 so deployment tooling can gate traffic.

Probes run as sync functions: FastAPI executes them in the threadpool, so the
event loop is never blocked by a slow dependency.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings

router = APIRouter(tags=["health"])

# Per-probe socket timeout (seconds): fail fast instead of hanging the probe.
# int because QdrantClient's ``timeout`` parameter is typed ``int | None``.
_PROBE_TIMEOUT = 5


@router.get("/healthz", summary="Liveness probe (no external dependencies)")
def healthz() -> dict[str, str]:
    return {
        "status": "ok",
        "app": settings.app.name,
        "version": settings.app.version,
    }


def _probe_mysql() -> str:
    from sqlalchemy import text

    from app.core.db import engine

    with engine.connect() as conn:
        version = conn.execute(text("SELECT VERSION()")).scalar_one()
    return f"MySQL {version} reachable"


def _probe_redis() -> str:
    import redis

    client = redis.from_url(
        settings.redis.url,
        socket_connect_timeout=_PROBE_TIMEOUT,
        socket_timeout=_PROBE_TIMEOUT,
    )
    if not client.ping():
        raise ConnectionError("PING returned False")
    return "Redis PONG"


def _probe_qdrant() -> str:
    from app.clients.qdrant_client import build_client

    client = build_client(timeout=_PROBE_TIMEOUT)
    client.get_collections()  # cheapest authenticated request
    return f"Qdrant reachable at {settings.qdrant.url}"


#: name -> probe; extend here when /readyz should cover more dependencies.
CHECKS: list[tuple[str, Callable[[], str]]] = [
    ("mysql", _probe_mysql),
    ("redis", _probe_redis),
    ("qdrant", _probe_qdrant),
]


@router.get(
    "/readyz",
    summary="Readiness probe (MySQL / Redis / Qdrant; 503 when any is down)",
)
def readyz() -> JSONResponse:
    checks: dict[str, dict[str, Any]] = {}
    all_ok = True
    for name, probe in CHECKS:
        started = time.perf_counter()
        try:
            detail = probe()
            checks[name] = {"ok": True, "detail": detail}
        except Exception as exc:  # noqa: BLE001 — any failure must surface as 503
            all_ok = False
            checks[name] = {
                "ok": False,
                "detail": f"{type(exc).__name__}: {exc}",
            }
        checks[name]["elapsed_ms"] = round((time.perf_counter() - started) * 1000)

    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={
            "status": "ok" if all_ok else "unavailable",
            "checks": checks,
        },
    )


@router.get(
    "/health/detail",
    summary="Full ops status: dependency probes + queue depth + 24h failure rate",
)
def health_detail() -> JSONResponse:
    """One-stop ops view (M3): dependency checks plus business health gauges.

    ``status`` is ``ok`` when every dependency answers AND no alert threshold
    trips; ``degraded`` otherwise (always HTTP 200 — the payload carries the
    verdict, cron/schedulers key off the JSON, not the code).
    """
    checks: dict[str, dict[str, Any]] = {}
    for name, probe in CHECKS:
        started = time.perf_counter()
        try:
            checks[name] = {"ok": True, "detail": probe()}
        except Exception as exc:  # noqa: BLE001
            checks[name] = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
        checks[name]["elapsed_ms"] = round((time.perf_counter() - started) * 1000)

    alerts: list[dict[str, Any]] = []
    from datetime import datetime, timedelta

    from sqlalchemy import func, select

    from app.core.db import SessionLocal
    from app.models import Document, IngestionJob

    queue_depth = 0
    failed_24h = 0
    settled_24h = 0
    documents_total = 0
    try:
        with SessionLocal() as session:
            documents_total = int(
                session.scalar(select(func.count()).select_from(Document)) or 0
            )
            by_status = session.execute(
                select(IngestionJob.status, func.count()).group_by(IngestionJob.status)
            ).all()
            status_counts = {s: int(n) for s, n in by_status}
            queue_depth = sum(
                status_counts.get(s, 0) for s in ("pending", "running", "retrying")
            )
            since = datetime.utcnow() - timedelta(hours=24)
            failed_24h = int(
                session.scalar(
                    select(func.count())
                    .select_from(IngestionJob)
                    .where(IngestionJob.status == "failed")
                    .where(IngestionJob.updated_at >= since)
                )
                or 0
            )
            settled_24h = int(
                session.scalar(
                    select(func.count())
                    .select_from(IngestionJob)
                    .where(IngestionJob.status.in_(("succeeded", "failed")))
                    .where(IngestionJob.updated_at >= since)
                )
                or 0
            )
        if queue_depth > 50:
            alerts.append(
                {
                    "code": "QUEUE_BACKLOG",
                    "detail": f"queue depth {queue_depth} > 50",
                }
            )
        if settled_24h >= 5 and failed_24h / settled_24h > 0.3:
            rate = round(failed_24h / settled_24h, 3)
            alerts.append(
                {
                    "code": "HIGH_FAILURE_RATE",
                    "detail": f"24h failure rate {rate} ({failed_24h}/{settled_24h}) > 0.3",
                }
            )
    except Exception as exc:  # noqa: BLE001
        alerts.append(
            {"code": "DB_UNAVAILABLE", "detail": f"{type(exc).__name__}: {exc}"}
        )

    deps_ok = all(c["ok"] for c in checks.values())
    status = "ok" if deps_ok and not alerts else "degraded"
    return JSONResponse(
        status_code=200,
        content={
            "status": status,
            "checks": checks,
            "gauges": {
                "documents_total": documents_total,
                "queue_depth": queue_depth,
                "jobs_failed_24h": failed_24h,
                "jobs_settled_24h": settled_24h,
            },
            "alerts": alerts,
        },
    )
