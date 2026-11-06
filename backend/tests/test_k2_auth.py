"""K2 authentication tests (offline: HTTP layer with stubbed DB lookups).

Live verification (real login against the seeded admin) runs in the K2 probe
and K6 integration.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_k2_auth.py -v -p no:cacheprovider
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.core import deps as deps_mod
from app.core.config import settings
from app.core.errors import AppError
from app.core.security import hash_password, issue_token, parse_token, verify_password
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

TENANT = "00000000-0000-0000-0000-000000000001"
UID = "00000000-0000-0000-0000-000000000002"


def _user(**kw: object) -> SimpleNamespace:
    base = {
        "id": UID,
        "tenant_id": TENANT,
        "username": "admin",
        "role": "admin",
        "status": "active",
        "password_hash": hash_password("secret123"),
    }
    base.update(kw)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# password hashing
# --------------------------------------------------------------------------- #


def test_password_hash_roundtrip() -> None:
    stored = hash_password("s3cret")
    assert stored.startswith("pbkdf2$")
    assert verify_password("s3cret", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("s3cret", None)
    assert not verify_password("s3cret", "garbage")


# --------------------------------------------------------------------------- #
# token mechanics
# --------------------------------------------------------------------------- #


def test_token_roundtrip_and_expiry() -> None:
    tok = issue_token(user_id=UID, tenant_id=TENANT, role="admin", username="admin")
    payload = parse_token(tok)
    assert payload["user_id"] == UID and payload["role"] == "admin"

    # tampered payload → 401
    body, sig = tok.split(".", 1)
    import app.core.security as sec

    try:
        sec.parse_token(f"{body[:-2]}xy.{sig}")
        raise AssertionError("tampered token must fail")
    except AppError as exc:
        assert exc.status_code == 401

    # expired → 401
    with patch.object(settings.security, "token_ttl_seconds", -10):
        expired = issue_token(user_id=UID, tenant_id=TENANT, role="admin", username="a")
    try:
        parse_token(expired)
        raise AssertionError("expired token must fail")
    except AppError as exc:
        assert exc.status_code == 401


def test_parse_token_rejects_garbage() -> None:
    for bad in ("", "abc", "a.b", "x." + "y"):
        try:
            parse_token(bad)
            raise AssertionError(f"expected 401 for {bad!r}")
        except AppError as exc:
            assert exc.status_code == 401


# --------------------------------------------------------------------------- #
# /auth/login
# --------------------------------------------------------------------------- #


def test_login_success_returns_token_and_user() -> None:
    user = _user()
    with (
        patch("app.api.auth.verify_password", return_value=True),
        patch("app.api.auth.record_audit"),
    ):
        # the login endpoint uses db.scalars(select(User)...).first()
        from sqlalchemy.orm import Session as SASession

        session = SASession.__new__(SASession)
        scalars = SimpleNamespace(first=lambda: user)
        with (
            patch.object(SASession, "scalars", lambda *a, **k: scalars),
            patch.object(SASession, "commit", lambda *a, **k: None),
        ):
            app.dependency_overrides[deps_mod.get_db] = lambda: session
            try:
                r = client.post(
                    "/api/auth/login", json={"username": "admin", "password": "x"}
                )
            finally:
                app.dependency_overrides.pop(deps_mod.get_db, None)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == "admin"
    assert data["user"]["tenant_id"] == TENANT
    assert parse_token(data["token"])["tenant_id"] == TENANT


def test_login_wrong_password_401_no_enumeration() -> None:
    user = _user()
    from sqlalchemy.orm import Session as SASession

    session = SASession.__new__(SASession)
    scalars = SimpleNamespace(first=lambda: user)
    with (
        patch.object(SASession, "scalars", lambda *a, **k: scalars),
        patch("app.api.auth.verify_password", return_value=False),
    ):
        app.dependency_overrides[deps_mod.get_db] = lambda: session
        try:
            r = client.post(
                "/api/auth/login", json={"username": "admin", "password": "bad"}
            )
        finally:
            app.dependency_overrides.pop(deps_mod.get_db, None)
    assert r.status_code == 401
    assert r.json()["code"] == "ERR_UNAUTHORIZED"


def test_login_disabled_user_401() -> None:
    user = _user(status="disabled")
    from sqlalchemy.orm import Session as SASession

    session = SASession.__new__(SASession)
    scalars = SimpleNamespace(first=lambda: user)
    with (
        patch.object(SASession, "scalars", lambda *a, **k: scalars),
        patch("app.api.auth.verify_password", return_value=True),
    ):
        app.dependency_overrides[deps_mod.get_db] = lambda: session
        try:
            r = client.post(
                "/api/auth/login", json={"username": "admin", "password": "x"}
            )
        finally:
            app.dependency_overrides.pop(deps_mod.get_db, None)
    assert r.status_code == 401


def test_login_unknown_user_401() -> None:
    from sqlalchemy.orm import Session as SASession

    session = SASession.__new__(SASession)
    scalars = SimpleNamespace(first=lambda: None)
    with patch.object(SASession, "scalars", lambda *a, **k: scalars):
        app.dependency_overrides[deps_mod.get_db] = lambda: session
        try:
            r = client.post(
                "/api/auth/login", json={"username": "ghost", "password": "x"}
            )
        finally:
            app.dependency_overrides.pop(deps_mod.get_db, None)
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# get_current_user via token / anonymous fallback / forced mode
# --------------------------------------------------------------------------- #


def test_me_with_valid_token_reads_role_from_db() -> None:
    tok = issue_token(user_id=UID, tenant_id=TENANT, role="admin", username="admin")
    user = _user(role="viewer")  # DB role wins over the token role
    from sqlalchemy.orm import Session as SASession

    session = SASession.__new__(SASession)
    with (
        patch.object(SASession, "get", lambda *a, **k: user),
        patch.object(SASession, "close", lambda *a, **k: None),
    ):
        app.dependency_overrides[deps_mod.get_db] = lambda: session
        try:
            r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
        finally:
            app.dependency_overrides.pop(deps_mod.get_db, None)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["role"] == "viewer"  # DB is the source of truth


def test_me_with_token_for_missing_user_401() -> None:
    tok = issue_token(user_id=UID, tenant_id=TENANT, role="admin", username="admin")
    from sqlalchemy.orm import Session as SASession

    session = SASession.__new__(SASession)
    with patch.object(SASession, "get", lambda *a, **k: None):
        app.dependency_overrides[deps_mod.get_db] = lambda: session
        try:
            r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
        finally:
            app.dependency_overrides.pop(deps_mod.get_db, None)
    assert r.status_code == 401


def test_anonymous_fallback_in_dev_mode() -> None:
    """auth_required=False + no header → seeded admin (pre-K2 compatibility)."""
    assert settings.security.auth_required is False
    r = client.get("/api/auth/me")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["tenant_id"] == TENANT


def test_forced_mode_rejects_missing_token() -> None:
    with patch.object(settings.security, "auth_required", True):
        r = client.get("/api/auth/me")
    assert r.status_code == 401
    assert r.json()["code"] == "ERR_UNAUTHORIZED"


def test_forced_mode_still_allows_valid_token() -> None:
    tok = issue_token(user_id=UID, tenant_id=TENANT, role="admin", username="admin")
    user = _user()
    from sqlalchemy.orm import Session as SASession

    session = SASession.__new__(SASession)
    with (
        patch.object(SASession, "get", lambda *a, **k: user),
        patch.object(SASession, "close", lambda *a, **k: None),
        patch.object(settings.security, "auth_required", True),
    ):
        app.dependency_overrides[deps_mod.get_db] = lambda: session
        try:
            r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
        finally:
            app.dependency_overrides.pop(deps_mod.get_db, None)
    assert r.status_code == 200, r.text
