"""F2 pipeline orchestration tests (offline — DI with fakes).

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_f2_pipeline.py -v -p no:cacheprovider
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.chunkers.base import Chunk as ChunkDTO
from app.workers import pipeline as pl
from app.workers.base import record_step


class FakeSession:
    """Minimal session: job lookup by doc_version_id, steps tracked."""

    def __init__(self) -> None:
        self.commits = 0
        self.job = SimpleNamespace(
            id="job-1",
            status="pending",
            error_message=None,
            doc_id="d-1",
            version=1,
            tenant_id="t-1",
            access_level="internal",
        )
        self.steps: list[SimpleNamespace] = []

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *a: object) -> None:
        pass

    def scalars(self, *a: object):
        return SimpleNamespace(first=lambda: self.job)

    def scalar(self, *a: object):
        # record_step asks for the current max step_order; steps added so far
        return len(self.steps)

    def get(self, model: object, pk: object):
        return self.job  # doc/version lookups reuse the stub

    def add(self, obj: object) -> None:
        self.steps.append(obj)

    def commit(self) -> None:
        self.commits += 1

    def expunge_all(self) -> None:
        pass


def make_factory(session: FakeSession):
    return lambda: session


def fake_embedder(dim: int = 4):
    class Emb:
        model_name = "fake-embed"

        def embed_with_usage(self, texts):
            return [[1.0] * dim for _ in texts], SimpleNamespace(token_count=7)

    return Emb()


def fake_storage(calls: list[str]):
    return SimpleNamespace(
        ensure_vector_collection=lambda dimension=None: calls.append("ensure"),
        upsert_points=lambda points: calls.append(f"upsert:{len(points)}"),
        delete_points_by_filter=lambda query_filter: calls.append("delete"),
    )


def stub_stages(monkeypatch, session: FakeSession, fail_parse: bool = False):
    """Patch parse/clean/chunk stages with deterministic fakes."""
    parsed = SimpleNamespace(blocks=[])
    cleaned = SimpleNamespace(blocks=[], metadata={})

    def fake_parse(sess, version_id):
        if fail_parse:
            raise ValueError("PDF is password-protected")
        return parsed

    monkeypatch.setattr(pl, "parse_and_store", fake_parse)
    monkeypatch.setattr(pl, "clean", lambda p: cleaned)

    dtos = [
        ChunkDTO(chunk_index=0, text="t0", token_count=2, chunk_hash="h0", page=1),
        ChunkDTO(chunk_index=1, text="t1", token_count=2, chunk_hash="h1", page=1),
    ]
    monkeypatch.setattr(
        pl, "FixedTokenChunker", lambda: SimpleNamespace(chunk=lambda c: dtos)
    )

    def fake_insert(sess, doc, version, dtos_list):
        return [
            SimpleNamespace(
                id=str(uuid4()),
                chunk_index=d.chunk_index,
                text=d.text,
                doc_version_id="v-1",
                chunk_hash=d.chunk_hash,
                page=d.page,
                token_count=d.token_count,
            )
            for d in dtos_list
        ]

    monkeypatch.setattr(pl, "insert_chunks", fake_insert)
    return parsed, cleaned, dtos


# --------------------------------------------------------------------------- #
# full chain (acceptance 1, 2)
# --------------------------------------------------------------------------- #


def test_full_chain_records_seven_steps_and_finishes(monkeypatch) -> None:
    session = FakeSession()
    stub_stages(monkeypatch, session)
    calls: list[str] = []
    monkeypatch.setattr(pl, "get_storage", lambda: fake_storage(calls))

    summary = pl.run_pipeline(
        "v-1",
        session_factory=make_factory(session),
        embedder=fake_embedder(),
    )
    names = [s.step_name for s in session.steps]
    assert names == [
        "parse",
        "clean",
        "chunk",
        "persist_chunks",
        "embed",
        "upsert",
        "write_back",
    ]
    assert all(s.status == "succeeded" for s in session.steps)
    assert all(
        s.started_at is not None and s.finished_at is not None for s in session.steps
    )
    assert session.job.status == "succeeded"  # finish_job ran
    assert summary == {"job_id": "job-1", "chunk_count": 2, "token_count": 7}
    assert any(c.startswith("upsert:2") for c in calls)


def test_step_outputs_are_recorded(monkeypatch) -> None:
    session = FakeSession()
    stub_stages(monkeypatch, session)
    calls: list[str] = []
    monkeypatch.setattr(pl, "get_storage", lambda: fake_storage(calls))
    pl.run_pipeline(
        "v-1", session_factory=make_factory(session), embedder=fake_embedder()
    )
    embed_step = next(s for s in session.steps if s.step_name == "embed")
    assert embed_step.output["result"] is not None  # serialized usage/vector summary
    upsert_step = next(s for s in session.steps if s.step_name == "upsert")
    assert upsert_step.output is not None  # every step carries output (acceptance 2)


# --------------------------------------------------------------------------- #
# failure propagation (acceptance 3)
# --------------------------------------------------------------------------- #


def test_parse_failure_fails_job_with_readable_error(monkeypatch) -> None:
    session = FakeSession()
    stub_stages(monkeypatch, session, fail_parse=True)
    with pytest.raises(ValueError, match="password-protected"):
        pl.run_pipeline(
            "v-1", session_factory=make_factory(session), embedder=fake_embedder()
        )
    parse_step = session.steps[0]
    assert parse_step.step_name == "parse"
    assert parse_step.status == "failed"
    assert "password-protected" in (parse_step.error_message or "")
    assert session.job.status == "failed"
    assert "password-protected" in (session.job.error_message or "")


def test_no_steps_after_failure(monkeypatch) -> None:
    session = FakeSession()
    stub_stages(monkeypatch, session, fail_parse=True)
    with pytest.raises(ValueError):
        pl.run_pipeline(
            "v-1", session_factory=make_factory(session), embedder=fake_embedder()
        )
    assert len(session.steps) == 1  # chain stopped at parse


# --------------------------------------------------------------------------- #
# celery retry policy (acceptance 4)
# --------------------------------------------------------------------------- #


def test_task_has_exponential_autoretry() -> None:
    task = pl.ingest_document
    assert task.autoretry_for == (Exception,)
    assert task.max_retries == 3
    assert task.retry_backoff == 2  # exponential base
    assert task.retry_jitter is True


def test_task_registered_under_contract_name() -> None:
    from app.workers.celery_app import celery_app

    registered = celery_app.tasks["ragims.ingest_document"]
    assert registered.name == "ragims.ingest_document"  # Proxy: compare by name


def test_record_step_order_increments_within_job() -> None:
    """Two sequential record_step calls must get increasing step_order."""
    session = FakeSession()
    with record_step("j", "a", lambda: 1, session_factory=make_factory(session)):
        pass
    with record_step("j", "b", lambda: 2, session_factory=make_factory(session)):
        pass
    assert [s.step_order for s in session.steps] == [1, 2]
