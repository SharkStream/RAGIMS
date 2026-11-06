"""M1 metrics tests (offline): registry math + exposition format + API shape.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_m1_metrics.py -v -p no:cacheprovider
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.core import metrics as metrics_mod
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def setup_function() -> None:
    """Isolate the module-level counters between tests."""
    metrics_mod.HTTP_REQUESTS.clear()
    metrics_mod.HTTP_DURATION.clear()


def test_record_request_accumulates_counts_and_latency() -> None:
    metrics_mod.record_request("GET", "/api/documents", 200, 0.1)
    metrics_mod.record_request("GET", "/api/documents", 200, 0.3)
    metrics_mod.record_request("POST", "/api/auth/login", 401, 0.2)
    assert metrics_mod.HTTP_REQUESTS[("GET", "/api/documents", "200")] == 2
    assert metrics_mod.HTTP_REQUESTS[("POST", "/api/auth/login", "401")] == 1
    assert metrics_mod.HTTP_DURATION[("GET", "/api/documents")] == [0.4, 2]


def test_render_exposition_format() -> None:
    metrics_mod.record_request("GET", "/api/documents", 200, 0.5)
    lines = metrics_mod.render_http_metrics()
    text = "\n".join(lines)
    assert "# TYPE ragims_http_requests_total counter" in text
    assert (
        'ragims_http_requests_total{method="GET",route="/api/documents",status="200"} 1'
        in text
    )
    assert (
        'ragims_http_request_duration_seconds_sum{method="GET",route="/api/documents"} 0.500000'
        in text
    )
    assert (
        'ragims_http_request_duration_seconds_count{method="GET",route="/api/documents"} 1'
        in text
    )
    assert "ragims_process_uptime_seconds" in text


def test_route_template_prefers_matched_route() -> None:
    route = SimpleNamespace(path="/api/documents/{doc_id}")
    assert metrics_mod.route_template({"route": route, "path": "/api/documents/x"}) == (
        "/api/documents/{doc_id}"
    )
    # no matched route → raw path fallback
    assert metrics_mod.route_template({"path": "/api/whatever"}) == "/api/whatever"


def test_middleware_counts_real_request() -> None:
    r = client.get("/api/health")
    assert r.status_code in (200, 404)  # health route exists at root or /api
    text = client.get("/api/metrics").text
    assert "ragims_http_requests_total" in text


def test_metrics_endpoint_exposes_db_gauges() -> None:
    """DB-derived gauges render with labels and types (mocked session)."""
    from app.core import deps as deps_mod

    s = MagicMock()
    s.scalar.return_value = 7  # all count(*) queries
    s.execute.return_value.all.return_value = [
        ("succeeded", 5),
        ("failed", 2),
    ]  # jobs/status + steps duration
    app.dependency_overrides[deps_mod.get_db] = lambda: s
    try:
        r = client.get("/api/metrics")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/plain")
        text = r.text
        assert 'ragims_jobs_total{status="succeeded"} 5' in text
        assert 'ragims_jobs_total{status="failed"} 2' in text
        assert "ragims_jobs_queue_depth" in text
        assert "ragims_embedding_tokens_total" in text
        assert "ragims_chunks_total 7" in text
    finally:
        app.dependency_overrides.pop(deps_mod.get_db, None)
