"""In-process metrics registry (M1) — hand-rolled Prometheus exposition.

Zero-dependency counters kept in memory (per-process, adequate for the
single-worker dev/default deployment; Prometheus scrapes aggregate over
restarts). Only HTTP-layer counters live here — DB-derived gauges are
computed fresh on every ``/api/metrics`` scrape (see ``app/api/metrics.py``).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from typing import Any

_LOCK = threading.Lock()

#: (method, route_template, status) -> count
HTTP_REQUESTS: dict[tuple[str, str, str], int] = {}

#: (method, route_template) -> [total_seconds, count]
HTTP_DURATION: dict[tuple[str, str], list[float]] = {}

_START = time.time()


def record_request(method: str, route: str, status: int, seconds: float) -> None:
    key = (method, route, str(status))
    dur_key = (method, route)
    with _LOCK:
        HTTP_REQUESTS[key] = HTTP_REQUESTS.get(key, 0) + 1
        bucket = HTTP_DURATION.setdefault(dur_key, [0.0, 0])
        bucket[0] += seconds
        bucket[1] += 1


def route_template(scope: Mapping[str, Any]) -> str:
    """Best-effort route template (low cardinality); falls back to the path."""
    route = scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return str(path)
    return str(scope.get("path", "unknown"))


def render_http_metrics() -> list[str]:
    """Prometheus text lines for the HTTP counters collected in-process."""
    lines = [
        "# HELP ragims_http_requests_total Total HTTP requests.",
        "# TYPE ragims_http_requests_total counter",
    ]
    with _LOCK:
        for (method, route, status), count in sorted(HTTP_REQUESTS.items()):
            lines.append(
                f'ragims_http_requests_total{{method="{method}",route="{route}",'
                f'status="{status}"}} {count}'
            )
    lines.append("# HELP ragims_http_request_duration_seconds_sum Cumulative latency.")
    lines.append("# TYPE ragims_http_request_duration_seconds_sum counter")
    with _LOCK:
        for (method, route), (total_seconds, n_requests) in sorted(
            HTTP_DURATION.items()
        ):
            lines.append(
                f'ragims_http_request_duration_seconds_sum{{method="{method}",'
                f'route="{route}"}} {total_seconds:.6f}'
            )
            lines.append(
                f'ragims_http_request_duration_seconds_count{{method="{method}",'
                f'route="{route}"}} {n_requests}'
            )
    with _LOCK:
        uptime = time.time() - _START
    lines.append("# HELP ragims_process_uptime_seconds Process uptime.")
    lines.append("# TYPE ragims_process_uptime_seconds gauge")
    lines.append(f"ragims_process_uptime_seconds {uptime:.0f}")
    return lines
