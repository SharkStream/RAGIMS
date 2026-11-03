"""F1 task-base tests (offline — fake session factory).

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_f1_task_base.py -v -p no:cacheprovider
"""

from __future__ import annotations

import pytest
from app.models.document import Document
from app.models.ingestion_job import IngestionJob
from app.workers.base import finish_job, record_step


class FakeJobStep:
    def __init__(self, **kw: object) -> None:
        self.__dict__.update(kw)
        self.status = "pending"


class FakeJob:
    def __init__(self, doc_id: str | None = None) -> None:
        self.status = "pending"
        self.doc_id = doc_id
        self.error_message = None
        self.started_at = None
        self.finished_at = None


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.job = FakeJob()
        self.doc: FakeDocument | None = None
        self.steps: list[FakeJobStep] = []

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *a: object) -> None:
        pass

    def scalar(self, *a: object) -> None:
        return None  # no prior steps -> order starts at 1

    def add(self, step: FakeJobStep) -> None:
        self.steps.append(step)

    def get(self, model: object, pk: object) -> object:
        if model is Document:
            return self.doc
        return self.job

    def commit(self) -> None:
        self.commits += 1


class FakeDocument:
    def __init__(self, status: str = "processing") -> None:
        self.status = status


def make_factory(session: FakeSession):
    return lambda: session


def test_record_step_success_records_succeeded_with_output() -> None:
    session = FakeSession()
    with record_step(
        "job-1", "parse", lambda: {"chunks": 3}, session_factory=make_factory(session)
    ) as result:
        assert result == {"chunks": 3}
    step = session.steps[0]
    assert step.step_name == "parse"
    assert step.step_order == 1
    assert step.status == "succeeded"
    assert step.output == {"chunks": 3}
    assert step.error_message is None
    assert (
        session.job.status == "running"
    )  # set while running; finish_job marks succeeded
    assert session.commits >= 2


def test_record_step_failure_records_failed_and_reraises() -> None:
    session = FakeSession()

    def boom() -> None:
        raise RuntimeError("qdrant down")

    with pytest.raises(RuntimeError, match="qdrant down"):
        with record_step("job-1", "embed", boom, session_factory=make_factory(session)):
            pass
    step = session.steps[0]
    assert step.status == "failed"
    assert "RuntimeError" in (step.error_message or "")
    assert session.job.status == "failed"
    assert "qdrant down" in (session.job.error_message or "")


def test_record_step_increments_order_per_existing_steps() -> None:
    session = FakeSession()

    def scalar_highest(*a: object) -> int:
        return 4  # simulate an existing step at order 4

    session.scalar = scalar_highest  # type: ignore[method-assign]
    with record_step(
        "job-1", "embed", lambda: None, session_factory=make_factory(session)
    ):
        pass
    assert session.steps[0].step_order == 5


def test_record_step_serializes_non_dict_result() -> None:
    session = FakeSession()
    with record_step(
        "job-1", "noop", lambda: 42, session_factory=make_factory(session)
    ):
        pass
    assert session.steps[0].output == {"result": "42"}


def test_celery_routes_declare_stage_queues() -> None:
    from app.workers.celery_app import celery_app

    routes = celery_app.conf.task_routes
    assert routes["ragims.parse_document"]["queue"] == "parse"
    assert routes["ragims.embed_document"]["queue"] == "embed"
    assert routes["ragims.ingest_document"]["queue"] == "default"
    assert set(celery_app.conf.task_queues) == {"parse", "embed", "default"}


def test_placeholder_task_registered() -> None:
    import app.workers.tasks  # noqa: F401 — include= loads it in real workers
    from app.workers.celery_app import celery_app

    assert celery_app.tasks["ragims.ingest_document"] is not None


# --------------------------------------------------------------------------- #
# document terminal-state sync (doc26 fix): a settled job decides doc.status
# --------------------------------------------------------------------------- #


def test_finish_job_marks_document_succeeded() -> None:
    session = FakeSession()
    session.job = FakeJob(doc_id="doc-1")
    session.doc = FakeDocument("processing")
    finish_job("job-1", session_factory=make_factory(session))
    assert session.job.status == "succeeded"
    assert session.doc.status == "succeeded"


def test_failed_step_marks_document_failed() -> None:
    session = FakeSession()
    session.job = FakeJob(doc_id="doc-1")
    session.doc = FakeDocument("processing")
    with (
        pytest.raises(RuntimeError),
        record_step(
            "job-1",
            "boom",
            lambda: (_ for _ in ()).throw(RuntimeError("x")),
            session_factory=make_factory(session),
        ),
    ):
        pass
    assert session.job.status == "failed"
    assert session.doc.status == "failed"


def test_soft_deleted_document_never_resurrected() -> None:
    session = FakeSession()
    session.job = FakeJob(doc_id="doc-1")
    session.doc = FakeDocument("deleted")
    finish_job("job-1", session_factory=make_factory(session))
    assert session.doc.status == "deleted"


def test_cancelled_job_leaves_document_processing() -> None:
    session = FakeSession()
    session.job = FakeJob(doc_id="doc-1")
    session.doc = FakeDocument("processing")
    session.get(IngestionJob, "job-1").status = "cancelled"
    finish_job("job-1", session_factory=make_factory(session))
    assert session.doc.status == "processing"
