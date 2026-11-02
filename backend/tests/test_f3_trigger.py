"""F3 trigger tests (offline — fake session + monkeypatched dispatch).

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_f3_trigger.py -v -p no:cacheprovider
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.workers.base import PipelineCancelledError, record_step


class FakeSession:
    def __init__(self, jobs: dict[str, SimpleNamespace] | None = None) -> None:
        self.jobs = jobs or {}
        self.added: list = []
        self.commits = 0
        self.steps: list = []

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *a: object) -> None:
        pass

    def get(self, model: object, pk: object):
        return self.jobs.get(str(pk))

    def scalars(self, *a: object):
        return SimpleNamespace(first=lambda: None, all=lambda: [])

    def add(self, obj: object) -> None:
        self.added.append(obj)
        self.steps.append(obj)

    def commit(self) -> None:
        self.commits += 1

    def scalar(self, *a: object):
        return len(self.steps)

    def execute(self, *a: object) -> None:
        pass


# --------------------------------------------------------------------------- #
# reprocess (acceptance 1)
# --------------------------------------------------------------------------- #


def test_reprocess_creates_job_and_dispatches(monkeypatch) -> None:
    from app.services import document_service as ds

    doc = SimpleNamespace(id="d-1", tenant_id="t-1", status="processing")
    version = SimpleNamespace(
        id="v-1",
        version=1,
        is_latest=True,
        file_path="raw-docs/x",
        content_hash="h" * 64,
    )
    session = FakeSession(jobs={"d-1": doc})
    session.scalars = lambda *a, **kw: SimpleNamespace(
        first=lambda: version, all=lambda: []
    )

    dispatched: list[str] = []
    monkeypatch.setattr(
        ds, "_dispatch_ingestion", lambda vid: dispatched.append(vid) or "task-123"
    )

    outcome = ds.reprocess_document(session, "t-1", "d-1", user_id="u-1")
    assert outcome.job_id != ""
    assert dispatched == ["v-1"]
    job = session.added[0]
    assert job.job_type == "reprocess"
    assert job.status == "pending"
    assert job.doc_version_id == "v-1"
    assert job.celery_task_id == "task-123"  # written back after dispatch


def test_reprocess_404_for_unknown_doc() -> None:
    from app.core.errors import NotFoundError
    from app.services import document_service as ds

    session = FakeSession()  # no jobs -> get_document_or_404 raises
    with pytest.raises(NotFoundError):
        ds.reprocess_document(session, "t-1", "missing")


# --------------------------------------------------------------------------- #
# cancel (acceptance 2)
# --------------------------------------------------------------------------- #


def test_cancel_marks_pending_job() -> None:
    from app.services import document_service as ds

    job = SimpleNamespace(id="j-1", tenant_id="t-1", status="pending", doc_id="d-1")
    session = FakeSession(jobs={"j-1": job})
    out = ds.cancel_job(session, "t-1", "j-1")
    assert out.status == "cancelled"
    assert session.commits == 1


def test_cancel_rejects_terminal_job() -> None:
    from app.core.errors import AppError
    from app.services import document_service as ds

    job = SimpleNamespace(id="j-1", tenant_id="t-1", status="succeeded", doc_id="d-1")
    session = FakeSession(jobs={"j-1": job})
    with pytest.raises(AppError) as exc_info:
        ds.cancel_job(session, "t-1", "j-1")
    assert exc_info.value.status_code == 409


def test_cancel_404_for_foreign_tenant() -> None:
    from app.core.errors import NotFoundError
    from app.services import document_service as ds

    job = SimpleNamespace(id="j-1", tenant_id="other", status="pending", doc_id="d-1")
    session = FakeSession(jobs={"j-1": job})
    with pytest.raises(NotFoundError):
        ds.cancel_job(session, "t-1", "j-1")


# --------------------------------------------------------------------------- #
# worker recognizes the flag (acceptance 2)
# --------------------------------------------------------------------------- #


def test_record_step_raises_before_cancelled_step() -> None:
    job = SimpleNamespace(id="j-1", status="cancelled", error_message=None)
    session = FakeSession(jobs={"j-1": job})
    with pytest.raises(PipelineCancelledError, match="cancelled before step parse"):
        with record_step("j-1", "parse", lambda: {}, session_factory=lambda: session):
            pass
    assert session.steps == []  # no step row: job untouched
    assert job.status == "cancelled"


def test_running_job_is_not_blocked() -> None:
    job = SimpleNamespace(id="j-1", status="running", error_message=None)
    session = FakeSession(jobs={"j-1": job})
    with record_step(
        "j-1", "parse", lambda: {"ok": 1}, session_factory=lambda: session
    ):
        pass
    assert session.steps[0].status == "succeeded"


def test_cancelled_error_is_not_autoremoved(monkeypatch) -> None:
    """ingest_document swallows PipelineCancelledError -> no Celery retry."""
    from app.workers import pipeline as pl

    def boom(version_id: str) -> dict:
        raise PipelineCancelledError("job j-1 cancelled before step parse")

    monkeypatch.setattr(pl, "run_pipeline", boom)
    # apply() executes eagerly in-process (no broker) and returns SUCCESS
    # because the task body swallows the cancellation.
    result = pl.ingest_document.apply(args=["v-1"])
    assert result.get() == {"status": "cancelled"}
    assert result.state == "SUCCESS"
