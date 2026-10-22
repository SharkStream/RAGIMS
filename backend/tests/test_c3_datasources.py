"""C3 datasource API tests (offline: HTTP layer with stubbed service).

The live acceptance (seeded default present, upload auto-association, 409 on
duplicate name) runs in the probe recorded in ``docs/tasks/c3-datasource-api.md``.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_c3_datasources.py -v -p no:cacheprovider
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.core.errors import DuplicateError
from app.main import app
from app.schemas.datasource import DatasourceCreate, DatasourceOut
from fastapi.testclient import TestClient

client = TestClient(app)
NOW = datetime(2026, 10, 22, 3, 0, 0)


def _ds(i: int, **kw: object) -> DatasourceOut:
    base = {
        "id": f"00000000-0000-0000-0000-{i:012d}",
        "name": f"ds{i}",
        "type": "local",
        "sync_mode": "manual",
        "status": "active",
        "created_at": NOW,
    }
    base.update(kw)
    return DatasourceOut(**base)  # type: ignore[arg-type]


def test_datasource_create_schema_defaults_local() -> None:
    body = DatasourceCreate(name="team-drive")
    assert body.type == "local" and body.config is None


def test_list_datasources_envelope() -> None:
    rows = [
        SimpleNamespace(**_ds(2).model_dump()),
        SimpleNamespace(**_ds(1).model_dump()),
    ]
    with patch("app.api.datasources.list_datasources") as fake:
        fake.return_value = rows
        resp = client.get("/api/datasources")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [d["name"] for d in data] == ["ds2", "ds1"]
    assert set(data[0]) == set(DatasourceOut.model_fields)


def test_create_datasource_happy_path() -> None:
    created = SimpleNamespace(
        id="c" * 36,
        name="team-drive",
        type="local",
        sync_mode="manual",
        status="active",
        created_at=NOW,
    )
    with patch("app.api.datasources.create_local_datasource") as fake:
        fake.return_value = created
        resp = client.post(
            "/api/datasources", json={"name": "team-drive", "type": "local"}
        )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["name"] == "team-drive" and data["type"] == "local"
    assert data["status"] == "active"
    args = fake.call_args.args
    assert args[1] and args[2] == "team-drive"  # tenant_id, name


def test_create_rejects_non_local_with_501() -> None:
    resp = client.post("/api/datasources", json={"name": "s3-src", "type": "s3"})
    assert resp.status_code == 501
    body = resp.json()
    assert body["code"] == "ERR_NOT_IMPLEMENTED"
    assert body["data"]["supported"] == ["local"]


def test_create_duplicate_name_maps_409() -> None:
    with patch("app.api.datasources.create_local_datasource") as fake:
        fake.side_effect = DuplicateError("datasource name 'default' already exists")
        resp = client.post(
            "/api/datasources", json={"name": "default", "type": "local"}
        )
    assert resp.status_code == 409
    assert resp.json()["code"] == "ERR_DUPLICATE"


def test_create_rejects_bad_body_with_422() -> None:
    resp = client.post("/api/datasources", json={"type": "local"})  # name missing
    assert resp.status_code == 422
    assert resp.json()["code"] == "ERR_VALIDATION"
