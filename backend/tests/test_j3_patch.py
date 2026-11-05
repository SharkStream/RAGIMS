"""J3 metadata-PATCH tests (offline: HTTP layer with stubbed service functions).

DB-backed semantics (real row updates, tags JSON column, datasource FK) are
verified by the live probe / J6 integration.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_j3_patch.py -v -p no:cacheprovider
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.core.errors import AppError, NotFoundError
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

NOW = datetime(2026, 11, 4, 8, 0, 0)
DOC_ID = "00000000-0000-0000-0000-000000000007"


def _detail(**kw: object) -> dict:
    base = {
        "id": DOC_ID,
        "title": "patched title",
        "file_name": "doc7.pdf",
        "file_type": "pdf",
        "status": "succeeded",
        "current_version": 2,
        "datasource_id": "d" * 36,
        "access_level": "confidential",
        "tags": ["alpha"],
        "created_at": NOW,
        "updated_at": NOW,
    }
    base.update(kw)
    return base


def _stub(detail: dict) -> SimpleNamespace:
    """Return a SimpleNamespace the detail-shape builder can read."""
    return SimpleNamespace(**detail)


def test_patch_title_returns_updated_detail() -> None:
    with (
        patch("app.api.documents.update_document_meta") as um,
        patch("app.api.documents.get_latest_version") as lv,
    ):
        um.return_value = _stub(_detail(title="patched title"))
        lv.return_value = None
        resp = client.patch(f"/api/documents/{DOC_ID}", json={"title": "patched title"})
    assert resp.status_code == 200, resp.json()
    data = resp.json()["data"]
    assert data["title"] == "patched title"
    assert data["latest_version"] is None
    body = um.call_args.args[3]
    assert body.title == "patched title" and body.tags is None


def test_patch_empty_body_422() -> None:
    resp = client.patch(f"/api/documents/{DOC_ID}", json={})
    assert resp.status_code == 422
    assert resp.json()["code"] == "ERR_VALIDATION"


def test_patch_unknown_field_422() -> None:
    resp = client.patch(f"/api/documents/{DOC_ID}", json={"file_name": "x.pdf"})
    assert resp.status_code == 422
    assert resp.json()["code"] == "ERR_VALIDATION"


def test_patch_bad_access_level_422() -> None:
    resp = client.patch(f"/api/documents/{DOC_ID}", json={"access_level": "topsecret"})
    assert resp.status_code == 422


def test_patch_deleted_doc_409() -> None:
    with patch("app.api.documents.update_document_meta") as um:
        um.side_effect = AppError("deleted", code="ERR_CONFLICT", status_code=409)
        resp = client.patch(f"/api/documents/{DOC_ID}", json={"title": "t"})
    assert resp.status_code == 409
    assert resp.json()["code"] == "ERR_CONFLICT"


def test_patch_cross_tenant_404() -> None:
    with patch("app.api.documents.update_document_meta") as um:
        um.side_effect = NotFoundError("document not found")
        resp = client.patch(f"/api/documents/{DOC_ID}", json={"title": "t"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "ERR_NOT_FOUND"


def test_patch_request_accepts_tags_list() -> None:
    from app.schemas.document import DocumentPatchRequest

    req = DocumentPatchRequest(tags=["a", "b"])
    fields = {
        k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None
    }
    assert fields == {"tags": ["a", "b"]}


def test_openapi_has_patch_route() -> None:
    schema = client.get("/openapi.json").json()
    path = schema["paths"].get("/api/documents/{doc_id}", {})
    assert "patch" in path
    body = path["patch"]["requestBody"]["content"]["application/json"]["schema"]
    assert body["$ref"].endswith("DocumentPatchRequest")
