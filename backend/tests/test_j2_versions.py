"""J2 version-query API tests (offline: HTTP layer, stubbed service functions).

Live-stack behaviour (multi-version rows, tenant isolation, real pagination)
is verified by the J-probe / J6 integration.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_j2_versions.py -v -p no:cacheprovider
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.core.errors import NotFoundError
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

NOW = datetime(2026, 11, 4, 7, 0, 0)
DOC_ID = "00000000-0000-0000-0000-000000000006"


def _version(n: int, **kw: object) -> SimpleNamespace:
    base = {
        "id": f"v{n}" + "0" * 34,
        "version": n,
        "content_hash": "h" * 64,
        "file_path": f"raw-docs/t/{DOC_ID}/{n}/a.txt",
        "file_size": 100 + n,
        "parse_status": "parsed",
        "chunk_count": n * 10,
        "embedding_model": "text-embedding-3-small",
        "is_latest": n == 2,
        "created_at": NOW,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _chunk(i: int) -> SimpleNamespace:
    return SimpleNamespace(
        chunk_index=i,
        text=f"chunk {i}",
        token_count=10,
        page=None,
        section=None,
    )


def test_versions_list_desc_and_fields() -> None:
    rows = [_version(2), _version(1)]
    with patch("app.api.documents.list_document_versions") as lv:
        lv.return_value = (rows, 2)
        resp = client.get(f"/api/documents/{DOC_ID}/versions")
    assert resp.status_code == 200, resp.json()
    data = resp.json()["data"]
    assert data["total"] == 2
    assert [v["version"] for v in data["items"]] == [2, 1]
    first = data["items"][0]
    assert first["is_latest"] is True
    assert first["embedding_model"] == "text-embedding-3-small"
    assert "chunk_count" in first and "file_path" in first
    assert lv.call_args.args[1]  # tenant_id positional from get_current_user


def test_version_detail_by_ordinal() -> None:
    with patch("app.api.documents.get_document_version") as gv:
        gv.return_value = _version(1)
        resp = client.get(f"/api/documents/{DOC_ID}/versions/1")
    assert resp.status_code == 200, resp.json()
    body = resp.json()["data"]
    assert body["version"] == 1 and body["is_latest"] is False
    assert gv.call_args.args[1:] == ("00000000-0000-0000-0000-000000000001", DOC_ID, 1)


def test_version_detail_404_when_missing() -> None:
    with patch("app.api.documents.get_document_version") as gv:
        gv.side_effect = NotFoundError("version 9 not found")
        resp = client.get(f"/api/documents/{DOC_ID}/versions/9")
    assert resp.status_code == 404
    assert resp.json()["code"] == "ERR_NOT_FOUND"


def test_version_chunks_paged() -> None:
    with patch("app.api.documents.list_version_chunks") as lc:
        lc.return_value = ([_chunk(0), _chunk(1)], 2)
        resp = client.get(f"/api/documents/{DOC_ID}/versions/1/chunks")
    assert resp.status_code == 200, resp.json()
    data = resp.json()["data"]
    assert data["total"] == 2
    assert [c["chunk_index"] for c in data["items"]] == [0, 1]
    assert set(data["items"][0]) == {
        "chunk_index",
        "text",
        "token_count",
        "page",
        "section",
    }
    assert lc.call_args.args[1:] == ("00000000-0000-0000-0000-000000000001", DOC_ID, 1)
