"""Application entrypoint — FastAPI app assembly (A3).

Bootstraps structured logging first so every subsequent import is covered, then
assembles the application: CORS (local frontend dev ports from Settings),
infrastructure health routes, and the unified global exception handlers.

Business routers mount here under ``settings.app.api_prefix`` as later tasks
(C1 upload, G1 jobs, ...) add them::

    from app.api.documents import router as documents_router
    app.include_router(documents_router, prefix=settings.app.api_prefix)
"""

import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.costs import router as costs_router
from app.api.datasources import router as datasources_router
from app.api.documents import router as documents_router
from app.api.evaluations import router as evaluations_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.metrics import router as metrics_router
from app.api.search import router as search_router
from app.api.settings import router as settings_router
from app.api.stats import router as stats_router
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.core.metrics import record_request, route_template

setup_logging(level=settings.app.log_level)

app = FastAPI(
    title=f"{settings.app.name} API",
    version=settings.app.version,
    description="RAG Ingestion Management System — metadata & ingestion APIs.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS: allow the local frontend dev ports (APP__CORS_ORIGINS in .env).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _metrics_middleware(request: Request, call_next):  # noqa: ANN201
    """M1: count requests + latency per (method, route-template, status)."""
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - started
    try:
        record_request(
            request.method,
            route_template(request.scope),
            response.status_code,
            elapsed,
        )
    except Exception:  # noqa: BLE001 — metrics must never break requests
        pass
    return response


# Infrastructure endpoints stay at the root so probes never move when the
# business API prefix changes.
app.include_router(health_router)
app.include_router(documents_router, prefix=settings.app.api_prefix)
app.include_router(auth_router, prefix=settings.app.api_prefix)
app.include_router(audit_router, prefix=settings.app.api_prefix)
app.include_router(datasources_router, prefix=settings.app.api_prefix)
app.include_router(evaluations_router, prefix=settings.app.api_prefix)
app.include_router(jobs_router, prefix=settings.app.api_prefix)
app.include_router(metrics_router, prefix=settings.app.api_prefix)
app.include_router(search_router, prefix=settings.app.api_prefix)
app.include_router(jobs_router, prefix=settings.app.api_prefix)
app.include_router(metrics_router, prefix=settings.app.api_prefix)
app.include_router(search_router, prefix=settings.app.api_prefix)
app.include_router(settings_router, prefix=settings.app.api_prefix)
app.include_router(stats_router, prefix=settings.app.api_prefix)
app.include_router(costs_router, prefix=settings.app.api_prefix)
# M3: the ops payload is ALSO reachable under the API prefix so the frontend
# (axios baseURL=/api) can consume it; the bare root paths stay for LB probes.
app.include_router(health_router, prefix=settings.app.api_prefix)

# Unified error envelope for every route registered above and below.
register_exception_handlers(app)
