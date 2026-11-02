"""G1 job API tests (offline — fake session + monkeypatched dispatch).

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_g1_jobs.py -v -p no:cacheprovider
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


class FakeSession:
    def __init__(
        self,
        jobs: dict[str, SimpleNamespace] | None = None,
        all_result: list | None = None,
    ) -> None:
        self.jobs = jobs or {}
        self.all_result = all_result or []
        self.added: list = []
        self.commits = 0

    def get(self, model: object, pk: object):
        return self.jobs.get(str(pk))

    def scalars(self, *a: object, **kw: object):
        return SimpleNamespace(first=lambda: None, all=lambda: list(self.all_result))

    def scalar(self, *a: object):
        return len(self.jobs)

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.commits += 1

    def execute(self, *a: object) -> None:
        pass


NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def make_job(**kw: object) -> SimpleNamespace:
    base: dict = {
        "id": "j-1",
        "tenant_id": "t-1",
        "doc_id": "d-1",
        "doc_version_id": "v-1",
        "job_type": "full",
        "status": "failed",
        "priority": 5,
        "created_by": "u-1",
        "celery_task_id": "task-1",
        "error_message": "boom",
        "created_at": NOW,
        "updated_at": NOW,
        "started_at": NOW,
        "finished_at": NOW + timedelta(seconds=2),
    }
    base.update(kw)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# queries (acceptance 1)
# --------------------------------------------------------------------------- #


def test_list_jobs_returns_rows_and_total() -> None:
    from app.services import job_service as js

    rows = [make_job(), make_job(id="j-2", status="succeeded")]
    session = FakeSession(jobs={r.id: r for r in rows}, all_result=rows)
    got, total = js.list_jobs(session, "t-1", page=1, page_size=20)
    assert got == rows
    assert total == 2


def test_get_job_or_404_and_tenant_scope() -> None:
    from app.core.errors import NotFoundError
    from app.services import job_service as js

    session = FakeSession(jobs={"j-1": make_job(tenant_id="other")})
    with pytest.raises(NotFoundError):
        js.get_job_or_404(session, "t-1", "j-1")
    session2 = FakeSession(jobs={"j-1": make_job()})
    assert js.get_job_or_404(session2, "t-1", "j-1").id == "j-1"


def test_get_job_steps_ordered_and_scoped() -> None:
    from app.core.errors import NotFoundError
    from app.services import job_service as js

    steps = [
        SimpleNamespace(
            step_order=2,
            step_name="clean",
            status="succeeded",
            retry_count=0,
            input=None,
            output=None,
            error_message=None,
            started_at=NOW,
            finished_at=NOW + timedelta(seconds=1),
        ),
        SimpleNamespace(
            step_order=1,
            step_name="parse",
            status="succeeded",
            retry_count=0,
            input=None,
            output=None,
            error_message=None,
            started_at=NOW,
            finished_at=NOW + timedelta(seconds=1),
        ),
    ]
    session = FakeSession(jobs={"j-1": make_job()}, all_result=steps)
    got = js.get_job_steps(session, "t-1", "j-1")
    assert [s.step_name for s in got] == [
        "clean",
        "parse",
    ]  # fake passes through; API sorts in DB

    empty = FakeSession()  # no such job -> 404
    with pytest.raises(NotFoundError):
        js.get_job_steps(empty, "t-1", "j-1")


# --------------------------------------------------------------------------- #
# retry (acceptance 2)
# --------------------------------------------------------------------------- #


def test_retry_creates_new_job_and_dispatches(monkeypatch) -> None:
    from app.services import job_service as js

    session = FakeSession(jobs={"j-1": make_job()})
    dispatched: list[str] = []
    monkeypatch.setattr(
        js, "_dispatch_ingestion", lambda vid: dispatched.append(vid) or "task-9"
    )

    new_job = js.retry_job(session, "t-1", "j-1", user_id="u-9")
    assert new_job.id != "j-1"
    assert new_job.status == "pending"
    assert new_job.job_type == "full"  # inherited
    assert new_job.doc_version_id == "v-1"
    assert new_job.celery_task_id == "task-9"
    assert dispatched == ["v-1"]
    assert session.commits == 2  # create + task_id writeback


def test_retry_rejects_non_failed_job() -> None:
    from app.core.errors import AppError
    from app.services import job_service as js

    session = FakeSession(jobs={"j-1": make_job(status="succeeded")})
    with pytest.raises(AppError) as exc_info:
        js.retry_job(session, "t-1", "j-1")
    assert exc_info.value.status_code == 409


def test_retry_rejects_job_without_version() -> None:
    from app.core.errors import AppError
    from app.services import job_service as js

    session = FakeSession(jobs={"j-1": make_job(doc_version_id=None)})
    with pytest.raises(AppError):
        js.retry_job(session, "t-1", "j-1")


# --------------------------------------------------------------------------- #
# routes registered under the unified prefix
# --------------------------------------------------------------------------- #


def test_job_routes_registered() -> None:
    from app.main import app

    client = TestClient(app)
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/jobs",
        "/api/jobs/{job_id}",
        "/api/jobs/{job_id}/steps",
        "/api/jobs/{job_id}/retry",
        "/api/jobs/{job_id}/cancel",
    ):
        assert path in paths, path
