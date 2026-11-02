"""G3 stats tests (offline — fake session with scripted scalars).

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_g3_stats.py -v -p no:cacheprovider
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class ScriptedSession:
    """scalar() pops from a scripted list (collect_stats issues 6 counts)."""

    def __init__(self, values: list[int]) -> None:
        self.values = list(values)

    def scalar(self, *a: object):
        return self.values.pop(0) if self.values else 0

    def scalars(self, *a: object, **kw: object):  # unused by collect_stats
        raise AssertionError("collect_stats must not use scalars()")

    def execute(self, *a: object) -> None:
        pass


def make_stats(values: list[int]):
    from app.services.stats_service import collect_stats

    return collect_stats(ScriptedSession(values), "t-1")


def test_stats_fields_and_success_rate() -> None:
    # docs, chunks, total_jobs, succeeded, failed, today
    r = make_stats([12, 345, 40, 30, 6, 5])
    assert r.total_documents == 12
    assert r.total_chunks == 345
    assert r.total_jobs == 40
    assert r.succeeded_jobs == 30
    assert r.failed_jobs == 6
    assert r.processed_today == 5
    assert r.success_rate == pytest.approx(30 / 36)


def test_success_rate_none_without_terminal_jobs() -> None:
    r = make_stats([3, 10, 2, 0, 0, 1])
    assert r.success_rate is None
    assert r.total_jobs == 2


def test_zero_tenant_returns_all_zeros() -> None:
    r = make_stats([])
    assert r.total_documents == 0
    assert r.total_chunks == 0
    assert r.total_jobs == 0
    assert r.success_rate is None


def test_stats_route_registered() -> None:
    from app.main import app

    client = TestClient(app)
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/stats" in paths
