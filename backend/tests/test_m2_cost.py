"""M2 cost statistics tests (offline): endpoint contract over mocked session.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_m2_cost.py -v -p no:cacheprovider
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.main import app
from fastapi.testclient import TestClient

TENANT = "00000000-0000-0000-0000-000000000001"
ADMIN = "00000000-0000-0000-0000-000000000002"


def _auth() -> None:
    from app.core import deps as deps_mod
    from app.core.deps import CurrentUser

    app.dependency_overrides[deps_mod.get_current_user] = lambda: CurrentUser(
        id=ADMIN, tenant_id=TENANT, username="admin", role="admin"
    )


def _reset() -> None:
    from app.core import deps as deps_mod

    app.dependency_overrides.pop(deps_mod.get_current_user, None)
    app.dependency_overrides.pop(deps_mod.get_db, None)


def test_costs_api_shape_and_aggregates() -> None:
    _auth()
    s = MagicMock()
    s.scalar.return_value = 1234  # total tokens
    # scalar reused for embed_calls too? No — count uses scalar as well.
    s.execute.return_value.all.return_value = [
        ("2026-11-06", 1000, 2),
        ("2026-11-05", 234, 1),
    ]
    from app.core import deps as deps_mod

    app.dependency_overrides[deps_mod.get_db] = lambda: s
    try:
        r = TestClient(app).get("/api/stats/costs", params={"days": 30})
        assert r.status_code == 200, r.text
        body = r.json()["data"]
        assert body["total_tokens"] == 1234
        assert [d["day"] for d in body["days"]] == ["2026-11-06", "2026-11-05"]
        assert body["days"][0] == {
            "day": "2026-11-06",
            "tokens": 1000,
            "embed_calls": 2,
        }
    finally:
        _reset()


def test_costs_api_empty_returns_zero() -> None:
    _auth()
    from app.core import deps as deps_mod

    s = MagicMock()
    s.scalar.return_value = None  # no rows anywhere
    s.execute.return_value.all.return_value = []
    app.dependency_overrides[deps_mod.get_db] = lambda: s
    try:
        r = TestClient(app).get("/api/stats/costs")
        assert r.status_code == 200, r.text
        body = r.json()["data"]
        assert body == {"total_tokens": 0, "embed_calls": 0, "days": []}
    finally:
        _reset()


def test_costs_api_days_param_validated() -> None:
    _auth()
    from fastapi.testclient import TestClient

    c = TestClient(app)
    try:
        assert c.get("/api/stats/costs", params={"days": 0}).status_code == 422
        assert c.get("/api/stats/costs", params={"days": 400}).status_code == 422
    finally:
        _reset()


def test_embed_output_carries_structured_tokens() -> None:
    """Pipeline embed step returns a JSON-safe summary (M2 data source)."""
    import inspect

    from app.workers import pipeline

    source = inspect.getsource(pipeline)
    assert '"token_count": usage.token_count' in source
    assert "embed_summary" in source
