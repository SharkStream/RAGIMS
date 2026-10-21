"""Application entrypoint — FastAPI app assembly (A3).

Bootstraps structured logging first so every subsequent import is covered, then
assembles the application: CORS (local frontend dev ports from Settings),
infrastructure health routes, and the unified global exception handlers.

Business routers mount here under ``settings.app.api_prefix`` as later tasks
(C1 upload, G1 jobs, ...) add them::

    from app.api.documents import router as documents_router
    app.include_router(documents_router, prefix=settings.app.api_prefix)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import setup_logging

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

# Infrastructure endpoints stay at the root so probes never move when the
# business API prefix changes.
app.include_router(health_router)

# Unified error envelope for every route registered above and below.
register_exception_handlers(app)
