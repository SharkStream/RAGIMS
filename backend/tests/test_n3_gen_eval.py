"""N3 generation-evaluation tests (offline): judge parsing + runner + API.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_n3_gen_eval.py -v -p no:cacheprovider
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.main import app
from app.services.generation_eval import judge_generation

TENANT = "00000000-0000-0000-0000-000000000001"
ADMIN = "00000000-0000-0000-0000-000000000002"
NOW = "2026-11-13T10:00:00"


def _fake_client(responses: list[str]) -> MagicMock:
    client = MagicMock()
    client.complete_chat.side_effect = [(r, SimpleNamespace()) for r in responses]
    return client


def test_faithfulness_full_support() -> None:
    judge = _fake_client(
        [
            '{"claims": [{"claim": "a", "supported": true}, {"claim": "b", "supported": true}]}',
            '{"relevancy": 9, "refusal": false, "note": "直接回答"}',
        ]
    )
    j = judge_generation("q", "answer", ["ctx"], client=judge)
    assert j.faithfulness == 1.0
    assert j.relevancy == 0.9
    assert j.refusal is False


def test_faithfulness_half_support_is_hallucination_signal() -> None:
    judge = _fake_client(
        [
            '{"claims": [{"claim": "a", "supported": true}, {"claim": "b", "supported": false}]}',
            '{"relevancy": 5, "refusal": false, "note": "部分相关"}',
        ]
    )
    j = judge_generation("q", "answer", ["ctx"], client=judge)
    assert j.faithfulness == 0.5


def test_refusal_is_flagged_not_punished() -> None:
    judge = _fake_client(
        [
            '{"claims": []}',
            '{"relevancy": 8, "refusal": true, "note": "合理拒答"}',
        ]
    )
    j = judge_generation("q", "无法回答", ["ctx"], client=judge)
    assert j.refusal is True
    assert j.relevancy == 0.8  # honest refusal stays high relevancy


def test_unparseable_judge_degrades_to_zero() -> None:
    judge = _fake_client(["not json", "still not json", "still not json", "nope"])
    j = judge_generation("q", "answer", ["ctx"], client=judge)
    assert j.faithfulness == 0.0
    assert j.relevancy == 0.0


# --------------------------------------------------------------------------- #
# generation run via API (LLM + retrieval mocked)
# --------------------------------------------------------------------------- #


def _auth() -> None:
    from app.core import deps as deps_mod
    from app.core.deps import CurrentUser

    app.dependency_overrides[deps_mod.get_current_user] = lambda: CurrentUser(
        id=ADMIN, tenant_id=TENANT, username="admin", role="admin"
    )


def _reset() -> None:
    from app.core import deps as deps_mod

    for name in ("get_current_user", "get_db"):
        app.dependency_overrides.pop(getattr(deps_mod, name), None)


def test_generation_run_via_api() -> None:
    _auth()
    from app.core import deps as deps_mod

    s = MagicMock()
    app.dependency_overrides[deps_mod.get_db] = lambda: s
    captured: dict = {}

    def fake_create(session: object, **kw: object) -> SimpleNamespace:
        captured["kind"] = kw.get("kind")
        dataset = kw["dataset"]
        return SimpleNamespace(
            id="run-g",
            name=kw["name"],
            parent_run_id=kw.get("parent_run_id"),
            retrieval_mode=kw.get("retrieval_mode", "dense"),
            kind=kw.get("kind", "retrieval"),
            dataset=dataset,
            metrics={
                "kind": "generation",
                "queries": len(dataset),
                "faithfulness": 1.0,
                "answer_relevancy": 0.9,
                "refusal_rate": 0.0,
            },
            result=[{"query": dataset[0]["query"], "answer": "a"}],
            created_at=NOW,
        )

    try:
        with patch("app.api.evaluations.create_and_run_evaluation") as fake:
            fake.side_effect = fake_create
            with patch("app.api.evaluations.record_audit") as audit:
                from fastapi.testclient import TestClient

                r = TestClient(app).post(
                    "/api/evaluations",
                    json={
                        "name": "gen-eval",
                        "kind": "generation",
                        "dataset": [{"query": "q", "reference_answer": "ref"}],
                    },
                )
        assert r.status_code == 201, r.text
        body = r.json()["data"]
        assert body["kind"] == "generation"
        assert body["metrics"]["faithfulness"] == 1.0
        assert captured["kind"] == "generation"
        assert audit.call_args.kwargs["action"] == "eval.run"
    finally:
        _reset()


def test_retrieval_kind_still_requires_expected_ids() -> None:
    _auth()
    from app.core import deps as deps_mod
    from fastapi.testclient import TestClient

    c = TestClient(app)
    try:
        r = c.post(
            "/api/evaluations",
            json={"name": "x", "kind": "retrieval", "dataset": [{"query": "q"}]},
        )
        assert r.status_code == 422, r.text
        # generation kind: expected ids optional
        app.dependency_overrides[deps_mod.get_db] = lambda: MagicMock()
        with patch("app.api.evaluations.create_and_run_evaluation") as fake:
            fake.side_effect = lambda session, **kw: SimpleNamespace(
                id="r",
                name=kw["name"],
                parent_run_id=None,
                retrieval_mode="dense",
                kind="generation",
                dataset=kw["dataset"],
                metrics={},
                result=[],
                created_at=None,
            )
            with patch("app.api.evaluations.record_audit"):
                r2 = c.post(
                    "/api/evaluations",
                    json={
                        "name": "x",
                        "kind": "generation",
                        "dataset": [{"query": "q"}],
                    },
                )
        assert r2.status_code == 201, r2.text
    finally:
        _reset()


def test_generation_metrics_persisted_in_result_shape() -> None:
    """_run_generation_evaluation writes judge output per query."""
    from app.services.evaluation_service import _run_generation_evaluation

    run = SimpleNamespace(
        id="g1",
        tenant_id=TENANT,
        name="g",
        parent_run_id=None,
        retrieval_mode="dense",
        kind="generation",
        dataset=[{"query": "q", "reference_answer": None}],
        metrics=None,
        result=None,
        created_at=None,
    )
    with (
        patch(
            "app.services.chat_service.build_chat_contexts",
            return_value=[
                SimpleNamespace(
                    index=1,
                    doc_id="d",
                    version=1,
                    chunk_id=None,
                    page=None,
                    score=0.9,
                    text="t",
                )
            ],
        ),
        patch("app.services.chat_service.build_messages", return_value=[]),
        # one shared client: answer synthesis + faithfulness + relevancy
        patch(
            "app.clients.chat_client.get_chat_client",
            return_value=_fake_client(
                [
                    "答案文本",
                    '{"claims": [{"claim": "a", "supported": true}]}',
                    '{"relevancy": 10, "refusal": false, "note": "ok"}',
                ]
            ),
        ),
        patch(
            "app.services.generation_eval.get_chat_client",
            return_value=_fake_client(
                [
                    '{"claims": [{"claim": "a", "supported": true}]}',
                    '{"relevancy": 10, "refusal": false, "note": "ok"}',
                ]
            ),
        ),
    ):
        _run_generation_evaluation(MagicMock(), run, top_k=5)
    assert run.metrics["kind"] == "generation"
    assert run.metrics["faithfulness"] == 1.0
    assert json.dumps(run.result, ensure_ascii=False)
    assert run.result[0]["answer"] is not None
