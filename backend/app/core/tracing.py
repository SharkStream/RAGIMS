"""OpenTelemetry tracing (N5) — optional, off by default.

``OTEL__ENABLED=false`` (default): :func:`setup_tracing` is a **no-op** and
none of the opentelemetry packages are imported — zero overhead, and the
requirements-otel.txt bundle never needs to be installed.

``OTEL__ENABLED=true`` (requires ``pip install -r requirements-otel.txt``):
FastAPI / SQLAlchemy / Celery auto-instrumentation + OTLP export to
``OTEL__ENDPOINT`` (e.g. a Jaeger collector at http://localhost:4318/v1/traces).
Custom spans are exposed via :func:`trace_span` (no-op context manager when
disabled).
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_tracing_on = False


def setup_tracing(app: Any = None) -> bool:
    """Initialize OTel instrumentation when enabled; return the active state.

    Safe to call repeatedly; failures (bundle not installed, bad endpoint)
    log a warning and leave the app fully functional without tracing.
    """
    global _tracing_on
    if not settings.otel.enabled or _tracing_on:
        return _tracing_on
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(
            resource=Resource.create({"service.name": settings.otel.service_name})
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel.endpoint))
        )
        trace.set_tracer_provider(provider)

        if app is not None:
            FastAPIInstrumentor.instrument_app(app)
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

            SQLAlchemyInstrumentor().instrument()
        except Exception as exc:  # noqa: BLE001 — optional layer
            logger.warning(f"[otel] sqlalchemy instrumentation skipped: {exc}")

        _tracing_on = True
        logger.info(f"[otel] tracing enabled → {settings.otel.endpoint}")
    except Exception as exc:  # noqa: BLE001 — tracing must never break the app
        logger.warning(f"[otel] tracing not enabled: {type(exc).__name__}: {exc}")
    return _tracing_on


def trace_span(name: str, attributes: dict[str, Any] | None = None) -> Any:
    """Context-manager span (no-op when tracing is off)."""
    if not _tracing_on:
        return _NullSpan()
    try:
        from opentelemetry import trace

        tracer = trace.get_tracer(__name__)
        return tracer.start_as_current_span(name, attributes=attributes or {})
    except Exception:  # noqa: BLE001
        return _NullSpan()


class _NullSpan:
    """No-op replacement for a span context manager (tracing off)."""

    def __enter__(self) -> _NullSpan:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def set_attribute(self, key: str, value: Any) -> None:
        return None

    def record_exception(self, exc: BaseException) -> None:
        return None


def celery_instrument() -> bool:
    """Best-effort Celery instrumentation (worker side, N5)."""
    if not settings.otel.enabled:
        return False
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        CeleryInstrumentor().instrument()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[otel] celery instrumentation skipped: {exc}")
        return False
