"""K3 role-based access tests (offline: dependency-overridden identities).

403 matrix: ``viewer`` is rejected on every write path with ``ERR_FORBIDDEN``;
read paths stay open. ``editor``/``admin`` pass through to the (stubbed)
service layer.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_k3_roles.py -v -p no:cacheprovider
"""

from __future__ import annotations

from unittest.mock import patch

from app.core import deps as deps_mod
from app.core.deps import CurrentUser
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

TENANT = "00000000-0000-0000-0000-000000000001"
DOC_ID = "00000000-0000-0000-0000-00000000000b"
JOB_ID = "00000000-0000-0000-0000-00000000000c"


def _as(role: str) -> None:
    app.dependency_overrides[deps_mod.get_current_user] = lambda: CurrentUser(
        id="00000000-0000-0000-0000-000000000002",
        tenant_id=TENANT,
        username="tester",
        role=role,
    )


def _reset() -> None:
    app.dependency_overrides.pop(deps_mod.get_current_user, None)


WRITE_CALLS: list[tuple[str, str]] = [
    ("post", "/api/documents/upload"),
    ("patch", f"/api/documents/{DOC_ID}"),
    ("post", f"/api/documents/{DOC_ID}/versions/1/activate"),
    ("delete", f"/api/documents/{DOC_ID}/versions/2"),
    ("delete", f"/api/documents/{DOC_ID}"),
    ("post", f"/api/documents/{DOC_ID}/reprocess"),
    ("post", f"/api/documents/{DOC_ID}/jobs/{JOB_ID}/cancel"),
    ("post", f"/api/jobs/{JOB_ID}/retry"),
    ("post", f"/api/jobs/{JOB_ID}/cancel"),
]


def test_viewer_rejected_on_all_write_paths() -> None:
    _as("viewer")
    try:
        for method, url in WRITE_CALLS:
            r = _call(method, url)
            assert r.status_code == 403, f"{method} {url} → {r.status_code}"
            assert r.json()["code"] == "ERR_FORBIDDEN"
    finally:
        _reset()


def _call(method: str, url: str):
    """Fire the request; uploads get a file, PATCH gets a JSON body."""
    if method == "post" and url.endswith("/upload"):
        return client.post(url, files={"file": ("a.txt", b"x", "text/plain")})
    if method == "patch":
        return client.patch(url, json={"title": "t"})
    if method == "delete":
        return client.delete(url)
    return client.post(url)


def test_admin_and_editor_pass_gate_on_write_paths() -> None:
    """The gate lets writers through; downstream services are stubbed out."""
    for role in ("admin", "editor"):
        _as(role)
        try:
            with (
                patch("app.api.documents.upload_document") as up,
                patch("app.api.documents.update_document_meta") as upd,
                patch("app.api.documents.get_latest_version", return_value=None),
                patch("app.api.documents.activate_document_version") as act,
                patch("app.api.documents.delete_document_version") as dv,
                patch("app.api.documents.soft_delete_document") as sd,
                patch("app.api.documents.reprocess_document") as rp,
                patch("app.api.documents.record_audit"),
                patch("app.api.documents.cancel_job") as cj,
                patch("app.api.jobs.retry_job") as rj,
                patch("app.api.jobs.cancel_job") as jc2,
            ):
                detail = {
                    "id": DOC_ID,
                    "title": "t",
                    "file_name": "a.txt",
                    "file_type": "txt",
                    "status": "succeeded",
                    "current_version": 1,
                    "datasource_id": "d" * 36,
                    "access_level": "internal",
                    "tags": None,
                }
                from datetime import datetime

                now = datetime(2026, 11, 5, 9, 0, 0)
                detail_full = {
                    **detail,
                    "id": DOC_ID,
                    "status": "succeeded",
                    "created_at": now,
                    "updated_at": now,
                }
                up.return_value = type("D", (), detail_full)()
                upd.return_value = up.return_value
                act.return_value = up.return_value
                sd.return_value = up.return_value
                rp.return_value = up.return_value
                up.return_value.doc_id = DOC_ID
                up.return_value.version = 1
                up.return_value.job_id = JOB_ID
                up.return_value.duplicate = False
                up.return_value.file_path = "raw/x"
                up.return_value.content_hash = "h" * 64
                dv.return_value = type("V", (), {"id": "v", "version": 2})()
                cj.return_value = type(
                    "J", (), {"id": JOB_ID, "status": "cancelled", "doc_id": DOC_ID}
                )()
                rj.return_value = type("J", (), {"id": JOB_ID, "status": "pending"})()
                jc2.return_value = cj.return_value

                assert client.post(
                    "/api/documents/upload",
                    files={"file": ("a.txt", b"x", "text/plain")},
                ).status_code in (200, 201)
                assert (
                    client.patch(
                        f"/api/documents/{DOC_ID}", json={"title": "t"}
                    ).status_code
                    == 200
                )
                assert (
                    client.post(
                        f"/api/documents/{DOC_ID}/versions/1/activate"
                    ).status_code
                    == 200
                )
                assert client.post(
                    f"/api/documents/{DOC_ID}/reprocess"
                ).status_code in (200, 201)
        finally:
            _reset()


def test_read_paths_stay_open_for_viewer() -> None:
    _as("viewer")
    try:
        with (
            patch("app.api.documents.list_documents", return_value=([], 0)),
            patch("app.api.audit.list_audit_logs", return_value=([], 0)),
            patch("app.api.jobs.list_jobs", return_value=([], 0)),
        ):
            # The three stub-backed list endpoints must be 200, never 403.
            assert client.get("/api/documents").status_code == 200
            assert client.get("/api/jobs").status_code == 200
            assert client.get("/api/audit-logs").status_code == 200
        # Detail endpoints: identity gate passes (viewer), 404 comes from the
        # (unstubbed) tenant lookup — anything but 403 proves the gate is open.
        for url in (
            f"/api/documents/{DOC_ID}",
            f"/api/documents/{DOC_ID}/versions",
            f"/api/documents/{DOC_ID}/chunks",
        ):
            assert client.get(url).status_code != 403
    finally:
        _reset()


def test_role_helpers() -> None:
    from app.core.permissions import (
        ACCESS_LEVELS_BY_ROLE,
        role_can_read_access_level,
        role_can_write,
    )

    assert role_can_write("admin") and role_can_write("editor")
    assert not role_can_write("viewer")
    assert role_can_read_access_level("viewer", "internal")
    assert not role_can_read_access_level("viewer", "confidential")
    assert set(ACCESS_LEVELS_BY_ROLE) == {"admin", "editor", "viewer"}
