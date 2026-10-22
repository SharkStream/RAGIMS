"""C2 query-API tests (offline: HTTP layer with stubbed service functions).

DB-backed behaviour (filters, ordering, pagination over real rows) is verified
by the live probe recorded in ``docs/tasks/c2-document-query-api.md``.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_c2_query.py -v -p no:cacheprovider
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.core.errors import NotFoundError
from app.main import app
from app.schemas.document import ChunkOut, DocumentDeleteResponse, DocumentOut
from fastapi.testclient import TestClient

client = TestClient(app)

NOW = datetime(2026, 10, 22, 3, 0, 0)


def _doc(i: int, **kw: object) -> dict:
    base = {
        "id": f"00000000-0000-0000-0000-{i:012d}",
        "title": f"Doc {i}",
        "file_name": f"doc{i}.pdf",
        "file_type": "pdf",
        "status": "processing",
        "current_version": 1,
        "datasource_id": "d" * 36,
        "created_at": NOW,
        "updated_at": NOW,
    }
    base.update(kw)
    return base


def _out(i: int, **kw: object) -> DocumentOut:
    return DocumentOut(**_doc(i, **kw))  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# GET /documents
# --------------------------------------------------------------------------- #


def test_list_documents_envelope_and_pagination() -> None:
    with patch("app.api.documents.list_documents") as fake:
        fake.return_value = ([_out(2), _out(1)], 5)
        resp = client.get("/api/documents", params={"page": 2, "page_size": 2})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 5 and data["page"] == 2 and data["page_size"] == 2
    assert [i["id"] for i in data["items"]] == [
        "00000000-0000-0000-0000-000000000002",
        "00000000-0000-0000-0000-000000000001",
    ]
    item = data["items"][0]
    assert item["created_at"] == "2026-10-22T03:00:00"  # ISO datetime
    kwargs = fake.call_args.kwargs
    assert kwargs["page"] == 2 and kwargs["page_size"] == 2
    assert fake.call_args.args[1]  # tenant_id positional, from get_current_user


def test_list_documents_forwards_filters() -> None:
    with patch("app.api.documents.list_documents") as fake:
        fake.return_value = ([], 0)
        client.get(
            "/api/documents",
            params={"status": "processing", "file_type": "pdf", "keyword": "rep"},
        )
    kwargs = fake.call_args.kwargs
    assert kwargs["status"] == "processing"
    assert kwargs["file_type"] == "pdf"
    assert kwargs["keyword"] == "rep"


def test_list_documents_rejects_bad_pagination_422() -> None:
    resp = client.get("/api/documents", params={"page": 0})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "ERR_VALIDATION"
    assert isinstance(body["data"], list)  # validation details


# --------------------------------------------------------------------------- #
# GET /documents/{id}
# --------------------------------------------------------------------------- #


def test_document_detail_with_latest_version() -> None:
    version = {
        "id": "v" * 36,
        "version": 1,
        "content_hash": "h" * 64,
        "file_path": "raw-docs/t/d/1/f.pdf",
        "file_size": 42,
        "parse_status": "pending",
        "chunk_count": 0,
        "is_latest": True,
        "created_at": NOW,
    }
    with (
        patch("app.api.documents.get_document_or_404") as g,
        patch("app.api.documents.get_latest_version") as lv,
    ):
        g.return_value = _out(7)
        lv.return_value = SimpleNamespace(**version)
        resp = client.get("/api/documents/00000000-0000-0000-0000-000000000007")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"].endswith("000000000007")
    assert data["latest_version"]["content_hash"] == "h" * 64
    assert data["latest_version"]["is_latest"] is True


def test_document_detail_404_envelope() -> None:
    with patch("app.api.documents.get_document_or_404") as g:
        g.side_effect = NotFoundError("document x not found")
        resp = client.get("/api/documents/" + "9" * 36)
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "ERR_NOT_FOUND" and body["data"] is None


# --------------------------------------------------------------------------- #
# GET /documents/{id}/chunks
# --------------------------------------------------------------------------- #


def test_chunks_endpoint_orders_and_paginates() -> None:
    rows = [
        type(
            "C",
            (),
            {
                "chunk_index": i,
                "text": f"t{i}",
                "token_count": 5,
                "page": 1,
                "section": None,
            },
        )
        for i in range(3)
    ]
    with patch("app.api.documents.list_document_chunks") as fake:
        fake.return_value = (rows, 3)
        resp = client.get(
            "/api/documents/" + "8" * 36 + "/chunks",
            params={"page": 1, "page_size": 2},
        )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 3 and len(data["items"]) == 3
    assert [i["chunk_index"] for i in data["items"]] == [0, 1, 2]
    assert set(data["items"][0]) == {
        "chunk_index",
        "text",
        "token_count",
        "page",
        "section",
    }


def test_chunk_out_schema_shape() -> None:
    out = ChunkOut(chunk_index=0, text="t", token_count=3, page=2, section="s")
    assert set(out.model_dump()) == {
        "chunk_index",
        "text",
        "token_count",
        "page",
        "section",
    }


# --------------------------------------------------------------------------- #
# DELETE /documents/{id}
# --------------------------------------------------------------------------- #


def test_soft_delete_envelope() -> None:
    with patch("app.api.documents.soft_delete_document") as fake:
        fake.return_value = _out(9, status="deleted")
        resp = client.delete("/api/documents/" + "a" * 36)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "deleted" and data["doc_id"].endswith("000000000009")
    assert set(data) == set(DocumentDeleteResponse.model_fields)


def test_soft_delete_404_envelope() -> None:
    with patch("app.api.documents.soft_delete_document") as fake:
        fake.side_effect = NotFoundError("document missing not found")
        resp = client.delete("/api/documents/" + "b" * 36)
    assert resp.status_code == 404
    assert resp.json()["code"] == "ERR_NOT_FOUND"
