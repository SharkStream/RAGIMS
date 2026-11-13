"""N5 tracing + webhook tests (offline): no-op default, enabled path, POST.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_n5_tracing.py -v -p no:cacheprovider
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.core.tracing import _NullSpan, setup_tracing, trace_span

# --------------------------------------------------------------------------- #
# tracing: off by default → zero overhead, no imports
# --------------------------------------------------------------------------- #


def test_tracing_disabled_is_noop() -> None:
    old = settings.otel
    try:
        settings.otel = SimpleNamespace(
            enabled=False, endpoint="", service_name="ragims"
        )
        assert setup_tracing(None) is False
        span = trace_span("any", {"k": 1})
        assert isinstance(span, _NullSpan)
        with span as s:
            assert s is span
            s.set_attribute("x", 1)  # must not raise
            s.record_exception(RuntimeError("boom"))  # must not raise
    finally:
        settings.otel = old


def test_tracing_enabled_sets_provider_and_tools() -> None:
    old = settings.otel
    try:
        settings.otel = SimpleNamespace(
            enabled=True,
            endpoint="http://collector:4318/v1/traces",
            service_name="ragims-test",
        )
        # fresh state per test
        with (
            patch("app.core.tracing._tracing_on", False),
            patch("opentelemetry.sdk.trace.TracerProvider") as provider_cls,
            patch("opentelemetry.sdk.trace.export.BatchSpanProcessor"),
            patch(
                "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
            ),
            patch("opentelemetry.instrumentation.fastapi.FastAPIInstrumentor"),
            patch("opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor"),
            patch("opentelemetry.trace.set_tracer_provider"),
        ):
            app = MagicMock()
            assert setup_tracing(app) is True
            provider_cls.assert_called_once()
    finally:
        settings.otel = old


def test_tracing_failure_degrades_silently() -> None:
    """Missing bundle / bad endpoint must never break startup."""
    old = settings.otel
    try:
        settings.otel = SimpleNamespace(enabled=True, endpoint="bad", service_name="x")
        with patch(
            "opentelemetry.sdk.trace.TracerProvider",
            side_effect=RuntimeError("no bundle"),
        ):
            assert setup_tracing(None) is False
    finally:
        settings.otel = old


def test_chat_service_retrieval_is_spanned() -> None:
    """The chat retrieval path calls trace_span (N5 trace tree)."""
    import inspect

    from app.services import chat_service

    source = inspect.getsource(chat_service.build_chat_contexts)
    assert "trace_span" in source


# --------------------------------------------------------------------------- #
# alert_check webhook
# --------------------------------------------------------------------------- #


def _load_alert_module():
    import importlib.util
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "alert_check.py"
    spec = importlib.util.spec_from_file_location("alert_check_mod", path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_webhook_posts_json_when_alerts() -> None:
    mod = _load_alert_module()
    captured: dict = {}

    class FakeResp:
        status = 200

        def __enter__(self) -> FakeResp:
            return self

        def __exit__(self, *a) -> None:
            return None

    def fake_urlopen(req, timeout=0):  # noqa: ANN001, ARG001
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        return FakeResp()

    with patch("urllib.request.urlopen", fake_urlopen):
        assert mod._post_webhook("http://hook/x", {"status": "alert"}) is True
        mod._post_webhook(
            "http://hook/x", {"status": "alert", "alerts": [{"code": "Q"}]}
        )
    assert captured["url"] == "http://hook/x"
    assert captured["body"]["alerts"][0]["code"] == "Q"


def test_webhook_failure_is_non_fatal() -> None:
    mod = _load_alert_module()
    with patch("urllib.request.urlopen", side_effect=ConnectionError("down")):
        assert mod._post_webhook("http://hook/x", {"status": "alert"}) is False


def test_alert_check_exit_codes_and_webhook_flag() -> None:
    """healthy → 0 without webhook; --always forces the POST."""
    mod = _load_alert_module()
    with (
        patch.object(
            mod, "_probes", return_value=[{"name": "mysql", "ok": True, "detail": "ok"}]
        ),
        patch.object(
            mod,
            "_business_check",
            return_value={
                "gauges": {
                    "documents_total": 0,
                    "queue_depth": 0,
                    "jobs_failed_24h": 0,
                    "jobs_settled_24h": 0,
                    "failure_rate_24h": None,
                },
                "alerts": [],
            },
        ),
        patch.object(mod, "_post_webhook", return_value=True) as wh,
    ):
        assert mod.main(["--json"]) == 0
        wh.assert_not_called()
        assert mod.main(["--json", "--webhook", "http://h", "--always"]) == 0
        wh.assert_called_once()
