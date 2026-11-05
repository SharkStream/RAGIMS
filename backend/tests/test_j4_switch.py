"""J4 version-switch tests (offline: HTTP layer with stubbed service functions).

DB+Qdrant semantics (pointer flip, payload flip, rollback-on-Qdrant-failure,
object reclaim) are verified by the live probe / J6 integration.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_j4_switch.py -v -p no:cacheprovider
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.core.errors import AppError, NotFoundError
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

NOW = datetime(2026, 11, 4, 9, 0, 0)
DOC_ID = "00000000-0000-0000-0000-000000000008"


def _doc(**kw: object) -> SimpleNamespace:
    base = {
        "id": DOC_ID,
        "title": "Doc 8",
        "file_name": "doc8.pdf",
        "file_type": "pdf",
        "status": "succeeded",
        "current_version": 1,
        "datasource_id": "d" * 36,
        "access_level": "internal",
        "tags": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _version(n: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"v{n}" + "0" * 34,
        version=n,
        content_hash="h" * 64,
        file_path=f"raw-docs/t/{DOC_ID}/{n}/a.txt",
        file_size=100 + n,
        parse_status="parsed",
        chunk_count=5,
        embedding_model="text-embedding-3-small",
        is_latest=n == 1,
        created_at=NOW,
    )


def test_activate_returns_detail_with_new_latest() -> None:
    doc = _doc(current_version=1)
    with (
        patch("app.api.documents.activate_document_version") as av,
        patch("app.api.documents.get_latest_version") as lv,
    ):
        av.return_value = doc
        lv.return_value = _version(1)
        resp = client.post(f"/api/documents/{DOC_ID}/versions/1/activate")
    assert resp.status_code == 200, resp.json()
    data = resp.json()["data"]
    assert data["current_version"] == 1
    assert data["latest_version"]["is_latest"] is True
    assert av.call_args.args[1:] == (
        "00000000-0000-0000-0000-000000000001",
        DOC_ID,
        1,
    )


def test_activate_missing_version_404() -> None:
    with patch("app.api.documents.activate_document_version") as av:
        av.side_effect = NotFoundError("version 9 not found")
        resp = client.post(f"/api/documents/{DOC_ID}/versions/9/activate")
    assert resp.status_code == 404
    assert resp.json()["code"] == "ERR_NOT_FOUND"


def test_activate_unparsed_version_409() -> None:
    with patch("app.api.documents.activate_document_version") as av:
        av.side_effect = AppError("not parsed", code="ERR_CONFLICT", status_code=409)
        resp = client.post(f"/api/documents/{DOC_ID}/versions/2/activate")
    assert resp.status_code == 409
    assert resp.json()["code"] == "ERR_CONFLICT"


def test_activate_qdrant_down_503() -> None:
    with patch("app.api.documents.activate_document_version") as av:
        av.side_effect = AppError("down", code="ERR_UNAVAILABLE", status_code=503)
        resp = client.post(f"/api/documents/{DOC_ID}/versions/1/activate")
    assert resp.status_code == 503
    assert resp.json()["code"] == "ERR_UNAVAILABLE"


def test_delete_version_ok() -> None:
    with patch("app.api.documents.delete_document_version") as dv:
        dv.return_value = _version(2)
        resp = client.delete(f"/api/documents/{DOC_ID}/versions/2")
    assert resp.status_code == 200, resp.json()
    data = resp.json()["data"]
    assert data == {"doc_id": DOC_ID, "version": 2, "status": "deleted"}


def test_delete_latest_version_409() -> None:
    with patch("app.api.documents.delete_document_version") as dv:
        dv.side_effect = AppError("latest", code="ERR_CONFLICT", status_code=409)
        resp = client.delete(f"/api/documents/{DOC_ID}/versions/1")
    assert resp.status_code == 409


def test_openapi_has_activate_and_version_delete() -> None:
    schema = client.get("/openapi.json").json()
    activate = schema["paths"].get(
        "/api/documents/{doc_id}/versions/{version}/activate", {}
    )
    delete = schema["paths"].get("/api/documents/{doc_id}/versions/{version}", {})
    assert "post" in activate
    assert "delete" in delete
