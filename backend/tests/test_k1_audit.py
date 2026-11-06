"""K1 audit-log tests (offline: HTTP layer with stubbed service functions).

DB-backed semantics (real inserts, index, live probe) are verified by the
alembic migration + K6 integration.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_k1_audit.py -v -p no:cacheprovider
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

NOW = datetime(2026, 11, 5, 8, 0, 0)
DOC_ID = "00000000-0000-0000-0000-00000000000a"


def _row(**kw: object) -> SimpleNamespace:
    base = {
        "id": "0" * 36,
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "user_id": "00000000-0000-0000-0000-000000000002",
        "action": "doc.upload",
        "resource_type": "document",
        "resource_id": DOC_ID,
        "detail": {"file_name": "a.txt"},
        "created_at": NOW,
    }
    base.update(kw)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# write-path endpoints call record_audit with the right shape
# --------------------------------------------------------------------------- #


def test_patch_endpoint_records_audit() -> None:
    doc = _row(resource_id=DOC_ID)
    doc.action = "doc.meta_patch"
    with (
        patch("app.api.documents.update_document_meta") as svc,
        patch("app.api.documents.get_latest_version", return_value=None),
        patch("app.api.documents.record_audit") as audit,
    ):
        svc.return_value = SimpleNamespace(
            id=DOC_ID,
            title="t",
            file_name="a.txt",
            file_type="txt",
            status="succeeded",
            current_version=1,
            datasource_id="d" * 36,
            access_level="internal",
            tags=None,
            created_at=NOW,
            updated_at=NOW,
        )
        r = client.patch(f"/api/documents/{DOC_ID}", json={"title": "t2"})
    assert r.status_code == 200, r.text
    audit.assert_called_once()
    kw = audit.call_args.kwargs
    assert kw["action"] == "doc.meta_patch"
    assert kw["resource_id"] == DOC_ID
    assert kw["detail"] == {"fields": {"title": "t2"}}
    assert kw["tenant_id"] == "00000000-0000-0000-0000-000000000001"


def test_soft_delete_endpoint_records_audit() -> None:
    with (
        patch("app.api.documents.soft_delete_document") as svc,
        patch("app.api.documents.record_audit") as audit,
    ):
        svc.return_value = SimpleNamespace(id=DOC_ID, status="deleted")
        r = client.delete(f"/api/documents/{DOC_ID}")
    assert r.status_code == 200, r.text
    kw = audit.call_args.kwargs
    assert kw["action"] == "doc.soft_delete"
    assert kw["detail"] == {"status": "deleted"}


def test_activate_endpoint_records_audit() -> None:
    detail = SimpleNamespace(
        id=DOC_ID,
        title="t",
        file_name="a.txt",
        file_type="txt",
        status="succeeded",
        current_version=1,
        datasource_id="d" * 36,
        access_level="internal",
        tags=None,
        created_at=NOW,
        updated_at=NOW,
    )
    with (
        patch("app.api.documents.activate_document_version") as svc,
        patch("app.api.documents.get_latest_version", return_value=None),
        patch("app.api.documents.record_audit") as audit,
    ):
        svc.return_value = detail
        r = client.post(f"/api/documents/{DOC_ID}/versions/1/activate")
    assert r.status_code == 200, r.text
    kw = audit.call_args.kwargs
    assert kw["action"] == "doc.activate"
    assert kw["detail"] == {"activated_version": 1, "current_version": 1}


def test_upload_failure_records_nothing() -> None:
    from app.core.errors import AppError

    with (
        patch("app.api.documents.upload_document") as svc,
        patch("app.api.documents.record_audit") as audit,
    ):
        svc.side_effect = AppError("boom", code="ERR_INTERNAL", status_code=500)
        r = client.post(
            "/api/documents/upload",
            files={"file": ("a.txt", b"x", "text/plain")},
        )
    assert r.status_code == 500
    audit.assert_not_called()


# --------------------------------------------------------------------------- #
# GET /audit-logs
# --------------------------------------------------------------------------- #


def test_audit_logs_list_paged_and_filtered() -> None:
    rows = [
        _row(id="a" * 36, action="doc.upload", created_at=NOW),
        _row(id="b" * 36, action="doc.meta_patch", created_at=NOW),
    ]
    with patch("app.api.audit.list_audit_logs") as svc:
        svc.return_value = (rows, 2)
        r = client.get(
            "/api/audit-logs",
            params={"action": "doc.upload", "page": 1, "page_size": 1},
        )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["total"] == 2
    assert body["page_size"] == 1
    kw = svc.call_args.kwargs
    assert kw["action"] == "doc.upload"
    item = body["items"][0]
    assert item["action"] == "doc.upload"
    assert item["detail"] == {"file_name": "a.txt"}


def test_audit_logs_tenant_scoped() -> None:
    """The tenant filter comes from the identity, never from the request."""
    with patch("app.api.audit.list_audit_logs") as svc:
        svc.return_value = ([], 0)
        client.get("/api/audit-logs", params={"page": 1, "page_size": 5})
    args = svc.call_args.args
    assert args[1] == "00000000-0000-0000-0000-000000000001"  # stub tenant


# --------------------------------------------------------------------------- #
# record_audit never blocks the business operation
# --------------------------------------------------------------------------- #


def test_record_audit_swallows_db_failure() -> None:
    from app.services.audit_service import record_audit
    from sqlalchemy.orm import Session

    session = Session.__new__(Session)  # avoid DB: only the failure path runs
    calls: list[str] = []

    def boom(*_a: object, **_k: object) -> None:
        calls.append("commit")
        raise RuntimeError("db down")

    with (
        patch.object(Session, "add", lambda *a, **k: None),
        patch.object(Session, "commit", boom),
        patch.object(Session, "rollback", lambda *a, **k: calls.append("rollback")),
    ):
        record_audit(
            session,  # type: ignore[arg-type]
            tenant_id="t",
            user_id="u",
            action="doc.upload",
            resource_type="document",
            resource_id="r",
        )
    assert calls == ["commit", "rollback"]  # logged + rolled back, no raise
