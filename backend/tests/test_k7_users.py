"""K7 user-management tests (offline: dependency-overridden admin identity).

Live verification (create → login → demote → 403 → disable → 401) runs in the
K7 probe.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_k7_users.py -v -p no:cacheprovider
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core import deps as deps_mod
from app.core.deps import CurrentUser
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

TENANT = "00000000-0000-0000-0000-000000000001"
OTHER_TENANT = "00000000-0000-0000-0000-000000000099"
ADMIN_ID = "00000000-0000-0000-0000-000000000002"
TARGET_ID = "00000000-0000-0000-0000-00000000000f"
NOW = datetime(2026, 11, 6, 10, 0, 0)


def _as(role: str = "admin") -> None:
    app.dependency_overrides[deps_mod.get_current_user] = lambda: CurrentUser(
        id=ADMIN_ID, tenant_id=TENANT, username="admin", role=role
    )


def _reset() -> None:
    app.dependency_overrides.pop(deps_mod.get_current_user, None)


def _target(**kw: object) -> SimpleNamespace:
    base = {
        "id": TARGET_ID,
        "tenant_id": TENANT,
        "username": "bob",
        "email": None,
        "role": "viewer",
        "status": "active",
        "created_at": NOW,
        "updated_at": NOW,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _session_with(target: SimpleNamespace | None) -> MagicMock:
    s = MagicMock()
    s.get.return_value = target
    s.scalar.return_value = 1
    s.scalars.return_value.one_or_none.return_value = None  # dup check
    return s


# --------------------------------------------------------------------------- #
# POST /auth/users
# --------------------------------------------------------------------------- #


def test_admin_creates_user_with_audit() -> None:
    _as("admin")
    s = _session_with(_target(username="bob"))
    app.dependency_overrides[deps_mod.get_db] = lambda: s
    try:
        with (
            patch("app.api.auth.hash_password", return_value="h" * 64),
            patch("app.api.auth.record_audit") as audit,
        ):
            r = client.post(
                "/api/auth/users",
                json={"username": "bob", "password": "Passw0rd1", "role": "editor"},
            )
        assert r.status_code == 201, r.text
        assert r.json()["data"]["username"] == "bob"
        assert r.json()["data"]["role"] == "editor"
        kw = audit.call_args.kwargs
        assert kw["action"] == "auth.user_created"
        assert kw["detail"] == {"username": "bob", "role": "editor"}
    finally:
        app.dependency_overrides.pop(deps_mod.get_db, None)
        _reset()


def test_weak_password_422() -> None:
    _as("admin")
    try:
        for weak in ("short1", "allletters", "12345678", ""):
            r = client.post("/api/auth/users", json={"username": "b", "password": weak})
            assert r.status_code == 422, f"{weak!r} → {r.status_code}"
    finally:
        _reset()


def test_duplicate_username_409() -> None:
    _as("admin")
    s = MagicMock()
    s.scalars.return_value.one_or_none.return_value = _target(username="bob")
    app.dependency_overrides[deps_mod.get_db] = lambda: s
    try:
        r = client.post(
            "/api/auth/users", json={"username": "bob", "password": "Passw0rd1"}
        )
        assert r.status_code == 409, r.text
        assert r.json()["code"] == "ERR_CONFLICT"
    finally:
        app.dependency_overrides.pop(deps_mod.get_db, None)
        _reset()


def test_non_admin_create_403() -> None:
    for role in ("viewer", "editor"):
        _as(role)
        try:
            r = client.post(
                "/api/auth/users", json={"username": "x", "password": "Passw0rd1"}
            )
            assert r.status_code == 403, f"{role} → {r.status_code}"
            assert r.json()["code"] == "ERR_FORBIDDEN"
        finally:
            _reset()


# --------------------------------------------------------------------------- #
# GET /auth/users
# --------------------------------------------------------------------------- #


def test_list_users_scoped_and_hashless() -> None:
    _as("admin")
    s = MagicMock()
    s.scalar.return_value = 1
    s.scalars.return_value.all.return_value = [_target(password_hash="h" * 64)]
    app.dependency_overrides[deps_mod.get_db] = lambda: s
    try:
        r = client.get("/api/auth/users")
        assert r.status_code == 200, r.text
        item = r.json()["data"]["items"][0]
        assert "password_hash" not in item
        assert item["tenant_id"] == TENANT
    finally:
        app.dependency_overrides.pop(deps_mod.get_db, None)
        _reset()


def test_list_users_403_for_editor() -> None:
    _as("editor")
    try:
        assert client.get("/api/auth/users").status_code == 403
    finally:
        _reset()


# --------------------------------------------------------------------------- #
# PATCH /auth/users/{id}
# --------------------------------------------------------------------------- #


def test_patch_role_audits_from_to() -> None:
    _as("admin")
    target = _target(role="viewer")
    app.dependency_overrides[deps_mod.get_db] = lambda: _session_with(target)
    try:
        with patch("app.api.auth.record_audit") as audit:
            r = client.patch(f"/api/auth/users/{TARGET_ID}", json={"role": "editor"})
        assert r.status_code == 200, r.text
        kw = audit.call_args.kwargs
        assert kw["action"] == "auth.role_changed"
        assert kw["detail"]["from"] == "viewer" and kw["detail"]["to"] == "editor"
    finally:
        app.dependency_overrides.pop(deps_mod.get_db, None)
        _reset()


def test_disable_audits_and_allows_reenable() -> None:
    _as("admin")
    target = _target()
    app.dependency_overrides[deps_mod.get_db] = lambda: _session_with(target)
    try:
        with patch("app.api.auth.record_audit") as audit:
            assert (
                client.patch(
                    f"/api/auth/users/{TARGET_ID}", json={"status": "disabled"}
                ).status_code
                == 200
            )
            assert audit.call_args.kwargs["action"] == "auth.user_disabled"
            assert (
                client.patch(
                    f"/api/auth/users/{TARGET_ID}", json={"status": "active"}
                ).status_code
                == 200
            )
            assert audit.call_args.kwargs["action"] == "auth.user_enabled"
    finally:
        app.dependency_overrides.pop(deps_mod.get_db, None)
        _reset()


def test_password_reset_audits_without_storing_plaintext() -> None:
    _as("admin")
    target = _target()
    app.dependency_overrides[deps_mod.get_db] = lambda: _session_with(target)
    try:
        with (
            patch("app.api.auth.hash_password", return_value="newhash") as hp,
            patch("app.api.auth.record_audit") as audit,
        ):
            r = client.patch(
                f"/api/auth/users/{TARGET_ID}", json={"password": "NewPass99"}
            )
        assert r.status_code == 200, r.text
        hp.assert_called_once_with("NewPass99")
        assert audit.call_args.kwargs["action"] == "auth.password_reset"
        assert "NewPass99" not in str(audit.call_args.kwargs["detail"])
    finally:
        app.dependency_overrides.pop(deps_mod.get_db, None)
        _reset()


def test_cross_tenant_patch_is_404() -> None:
    _as("admin")
    outsider = _target(tenant_id=OTHER_TENANT)
    app.dependency_overrides[deps_mod.get_db] = lambda: _session_with(outsider)
    try:
        r = client.patch(f"/api/auth/users/{TARGET_ID}", json={"role": "editor"})
        assert r.status_code == 404, r.text
    finally:
        app.dependency_overrides.pop(deps_mod.get_db, None)
        _reset()


def test_admin_cannot_modify_self() -> None:
    _as("admin")
    s = MagicMock()
    app.dependency_overrides[deps_mod.get_db] = lambda: s
    try:
        for body in (
            {"role": "viewer"},
            {"status": "disabled"},
            {"password": "NewPass99"},
        ):
            r = client.patch(f"/api/auth/users/{ADMIN_ID}", json=body)
            assert r.status_code == 409, f"{body} → {r.status_code}"
            # the target row must never even be loaded
            s.get.assert_not_called()
    finally:
        app.dependency_overrides.pop(deps_mod.get_db, None)
        _reset()


def test_empty_patch_400() -> None:
    _as("admin")
    app.dependency_overrides[deps_mod.get_db] = lambda: MagicMock()
    try:
        r = client.patch(f"/api/auth/users/{TARGET_ID}", json={})
        assert r.status_code == 400, r.text
    finally:
        app.dependency_overrides.pop(deps_mod.get_db, None)
        _reset()


def test_invalid_role_value_422() -> None:
    _as("admin")
    r = client.patch(f"/api/auth/users/{TARGET_ID}", json={"role": "superuser"})
    assert r.status_code == 422, r.text
