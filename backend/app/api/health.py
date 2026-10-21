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
    from app.clients.qdrant import build_client

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
