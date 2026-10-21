"""A3 FastAPI skeleton acceptance tests.

No external service is required: /readyz probes are monkeypatched, and the
database layer is exercised through fakes. Run from ``backend/``::

    .venv/Scripts/python -m pytest tests/test_a3_skeleton.py -v
"""

from __future__ import annotations

from typing import Any

import pytest
from app.api import health
from app.core import deps
from app.core.errors import (
    ERR_DUPLICATE,
    ERR_INTERNAL,
    ERR_NOT_FOUND,
    ERR_OK,
    ERR_VALIDATION,
    AppError,
)
from app.core.exception_handlers import register_exception_handlers
from app.schemas.common import ApiResponse, PageResult, fail, ok
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    from app.main import app

    return TestClient(app)


# --------------------------------------------------------------------------- #
# Liveness / docs
# --------------------------------------------------------------------------- #


def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_docs_and_openapi(client: TestClient) -> None:
    from app.core.config import settings

    assert client.get("/docs").status_code == 200
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert resp.json()["info"]["title"] == f"{settings.app.name} API"
    assert resp.json()["info"]["version"] == settings.app.version


# --------------------------------------------------------------------------- #
# Readiness (probes mocked — no external services in unit tests)
# --------------------------------------------------------------------------- #


def test_readyz_all_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        health,
        "CHECKS",
        [("mysql", lambda: "MySQL fake"), ("redis", lambda: "Redis fake")],
    )
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["mysql"]["ok"] is True
    assert "elapsed_ms" in body["checks"]["redis"]


def test_readyz_any_failure_returns_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom() -> str:
        raise ConnectionError("redis down")

    monkeypatch.setattr(
        health,
        "CHECKS",
        [("mysql", lambda: "MySQL fake"), ("redis", boom)],
    )
    resp = client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["mysql"]["ok"] is True
    assert body["checks"]["redis"]["ok"] is False
    assert "redis down" in body["checks"]["redis"]["detail"]


# --------------------------------------------------------------------------- #
# Unified envelope + pagination
# --------------------------------------------------------------------------- #


def test_api_response_envelope() -> None:
    resp = ok({"id": "d1"}, message="created")
    assert resp.code == ERR_OK
    dumped = resp.model_dump()
    assert dumped == {"code": "OK", "message": "created", "data": {"id": "d1"}}

    err = fail(ERR_DUPLICATE, "content hash exists")
    assert err.model_dump()["code"] == ERR_DUPLICATE


def test_page_result() -> None:
    page = PageResult[str].of(["a", "b"], total=7, page=2, page_size=2)
    assert page.model_dump() == {
        "items": ["a", "b"],
        "total": 7,
        "page": 2,
        "page_size": 2,
    }


def test_generic_models_serialize_in_routes(client: TestClient) -> None:
    """ApiResponse[T] / PageResult[T] compose when used as a return type."""
    sub = FastAPI()

    @sub.get("/echo")
    def echo() -> ApiResponse[PageResult[str]]:
        return ok(PageResult[str].of(["x"], total=1, page=1, page_size=10))

    register_exception_handlers(sub)
    tc = TestClient(sub)
    body: dict[str, Any] = tc.get("/echo").json()
    assert body["code"] == ERR_OK
    assert body["data"]["items"] == ["x"]


# --------------------------------------------------------------------------- #
# Global exception handlers
# --------------------------------------------------------------------------- #


def _app_with(exc_route: Any) -> TestClient:
    """Fresh app with the same handler wiring as main.py plus one route."""
    sub = FastAPI()

    @sub.get("/boom")
    def boom() -> None:
        exc_route()

    register_exception_handlers(sub)
    return TestClient(sub)


def test_app_error_uses_its_code_and_status() -> None:
    def raise_it() -> None:
        raise AppError("doc missing", code=ERR_NOT_FOUND, status_code=404)

    resp = _app_with(raise_it).get("/boom")
    assert resp.status_code == 404
    assert resp.json()["code"] == ERR_NOT_FOUND
    assert resp.json()["message"] == "doc missing"


def test_http_exception_is_enveloped() -> None:
    def raise_it() -> None:
        raise HTTPException(status_code=404, detail="nope")

    resp = _app_with(raise_it).get("/boom")
    assert resp.status_code == 404
    assert resp.json()["code"] == ERR_NOT_FOUND


def test_request_validation_is_enveloped() -> None:
    sub = FastAPI()

    @sub.get("/items")
    def items(page: int) -> None:  # pragma: no cover - only hit with bad input
        return None

    register_exception_handlers(sub)
    resp = TestClient(sub).get("/items", params={"page": "not-a-number"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == ERR_VALIDATION
    assert body["data"]  # per-field details list is present


def test_unexpected_error_returns_500_envelope() -> None:
    def raise_it() -> None:
        raise RuntimeError("kaboom")

    # Starlette's ServerErrorMiddleware sends the 500 response *and* re-raises
    # the exception (so servers can log it); TestClient surfaces it unless told
    # otherwise. raise_server_exceptions=False asserts the envelope as clients see it.
    sub = FastAPI()

    @sub.get("/boom")
    def boom() -> None:
        raise_it()

    register_exception_handlers(sub)
    resp = TestClient(sub, raise_server_exceptions=False).get("/boom")
    assert resp.status_code == 500
    assert resp.json()["code"] == ERR_INTERNAL


# --------------------------------------------------------------------------- #
# Global dependencies
# --------------------------------------------------------------------------- #


def test_get_db_closes_session_in_finally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[bool] = []

    class FakeSession:
        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(deps, "SessionLocal", FakeSession)

    gen = deps.get_db()
    session = next(gen)
    assert isinstance(session, FakeSession)
    gen.close()  # simulates request teardown -> finally branch runs
    assert closed == [True]


def test_get_db_closes_on_error_too(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[bool] = []

    class FakeSession:
        def close(self) -> None:
            closed.append(True)

        def execute(self, *_: Any) -> None:
            raise RuntimeError("query failed")

    monkeypatch.setattr(deps, "SessionLocal", FakeSession)

    gen = deps.get_db()
    session = next(gen)
    with pytest.raises(RuntimeError):
        session.execute("SELECT 1")
    gen.close()
    assert closed == [True]


def test_get_current_user_returns_preset_ids() -> None:
    user = deps.get_current_user()
    assert user.tenant_id == deps.DEFAULT_TENANT_ID
    assert user.id == deps.DEFAULT_USER_ID
