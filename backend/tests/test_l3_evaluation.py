"""L3 evaluation-engine tests (offline): metric math + runner + API contract.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_l3_evaluation.py -v -p no:cacheprovider
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.main import app
from app.services.evaluation_service import (
    create_and_run_evaluation,
    run_evaluation,
    single_query_metrics,
)

TENANT = "00000000-0000-0000-0000-000000000001"
ADMIN = "00000000-0000-0000-0000-000000000002"
NOW = "2026-11-06T12:00:00"

# --------------------------------------------------------------------------- #
# metric math (hand-computed fixtures)
# --------------------------------------------------------------------------- #


def test_perfect_hit_ranks_first() -> None:
    m = single_query_metrics(["A", "X", "Y"], {"A"}, top_k=5)
    assert m["recall@k"] == 1.0
    assert m["reciprocal_rank"] == 1.0
    assert m["ndcg@k"] == 1.0
    assert m["first_hit_rank"] == 1.0


def test_miss_is_all_zero() -> None:
    m = single_query_metrics(["X", "Y", "Z"], {"A"}, top_k=5)
    assert m["recall@k"] == 0.0
    assert m["reciprocal_rank"] == 0.0
    assert m["ndcg@k"] == 0.0
    assert m["first_hit_rank"] == 0.0


def test_second_rank_hit_half_rr_and_ndcg() -> None:
    # expected={A}, hits=[X, A]: DCG=1/log2(2+1)≈0.6309, IDCG=1 → ndcg≈0.6309
    m = single_query_metrics(["X", "A"], {"A"}, top_k=5)
    assert m["reciprocal_rank"] == 0.5
    assert abs(m["ndcg@k"] - 0.6309) < 1e-3
    assert m["first_hit_rank"] == 2.0


def test_recall_fraction_of_expected() -> None:
    # 1 of 2 expected docs retrieved in top-k
    m = single_query_metrics(["A", "X"], {"A", "B"}, top_k=5)
    assert m["recall@k"] == 0.5


def test_top_k_truncation_limits_credit() -> None:
    # relevant doc at rank 6 must NOT count with k=5
    m = single_query_metrics(["X", "Y", "Z", "W", "V", "A"], {"A"}, top_k=5)
    assert m["first_hit_rank"] == 0.0
    assert m["recall@k"] == 0.0


# --------------------------------------------------------------------------- #
# runner (search_test mocked)
# --------------------------------------------------------------------------- #


def _hit(doc_id: str) -> SimpleNamespace:
    return SimpleNamespace(doc_id=doc_id)


def test_run_evaluation_aggregates_and_persists() -> None:
    dataset = [
        {"query": "payroll policy", "expected_doc_ids": ["A"]},
        {"query": "vacation rules", "expected_doc_ids": ["B"]},
    ]
    run = SimpleNamespace(
        id="run-1",
        tenant_id=TENANT,
        name="hr-suite",
        dataset=dataset,
        metrics=None,
        result=None,
    )
    responses = {
        "payroll policy": [_hit("A"), _hit("X")],
        "vacation rules": [_hit("X"), _hit("Y")],
    }

    def fake_search(query: str, **kw: object) -> SimpleNamespace:
        assert kw["tenant_id"] == TENANT
        assert kw["role"] == "admin"  # benchmark ignores viewer whitelist
        return SimpleNamespace(hits=responses[query])

    with patch("app.services.evaluation_service.search_test", side_effect=fake_search):
        run_evaluation(SimpleNamespace(), run, top_k=5)

    assert run.metrics["queries"] == 2
    assert run.metrics["hit_rate"] == 0.5  # only the first query hits
    assert run.metrics["recall@k"] == 0.5
    assert run.metrics["mrr"] == 0.5  # 1.0 + 0.0 → /2
    assert len(run.result) == 2
    assert run.result[0]["first_hit_rank"] == 1.0


def test_create_and_run_persists_row() -> None:
    s = MagicMock()
    with patch("app.services.evaluation_service.run_evaluation") as runner:
        run = create_and_run_evaluation(
            s,
            tenant_id=TENANT,
            user_id=ADMIN,
            name="nightly",
            dataset=[{"query": "q", "expected_doc_ids": ["A"]}],
            top_k=5,
        )
        runner.assert_called_once()
    s.add.assert_called_once()
    s.flush.assert_called_once()
    s.commit.assert_called_once()
    assert run.tenant_id == TENANT


def test_create_and_run_keeps_parent_lineage() -> None:
    """Rerun lineage (L4.1): parent_run_id lands on the new row, name unchanged."""
    s = MagicMock()
    with patch("app.services.evaluation_service.run_evaluation"):
        create_and_run_evaluation(
            s,
            tenant_id=TENANT,
            user_id=ADMIN,
            name="nightly",  # same name as the parent — no -rerun suffix
            dataset=[{"query": "q", "expected_doc_ids": ["A"]}],
            top_k=5,
            parent_run_id="run-parent-1",
        )
    row = s.add.call_args.args[0]
    assert row.parent_run_id == "run-parent-1"
    assert row.name == "nightly"


def test_create_api_rejects_parent_from_other_tenant() -> None:
    _auth()
    from app.core import deps as deps_mod

    s = MagicMock()
    s.get.return_value = SimpleNamespace(  # cross-tenant parent
        id="run-x", tenant_id="00000000-0000-0000-0000-000000000099"
    )
    app.dependency_overrides[deps_mod.get_db] = lambda: s
    from fastapi.testclient import TestClient

    c = TestClient(app)
    try:
        r = c.post(
            "/api/evaluations",
            json={
                "name": "x",
                "dataset": [{"query": "q", "expected_doc_ids": ["A"]}],
                "parent_run_id": "run-x",
            },
        )
        assert r.status_code == 404, r.text
    finally:
        _reset()


# --------------------------------------------------------------------------- #
# API contract
# --------------------------------------------------------------------------- #


def _auth(role: str = "admin") -> None:
    from app.core import deps as deps_mod
    from app.core.deps import CurrentUser

    app.dependency_overrides[deps_mod.get_current_user] = lambda: CurrentUser(
        id=ADMIN, tenant_id=TENANT, username="admin", role=role
    )


def _reset() -> None:
    from app.core import deps as deps_mod

    app.dependency_overrides.pop(deps_mod.get_current_user, None)
    app.dependency_overrides.pop(deps_mod.get_db, None)


def test_create_evaluation_api_runs_and_audits() -> None:
    _auth()
    s = MagicMock()

    def fake_create(session: object, **kw: object) -> SimpleNamespace:
        return SimpleNamespace(
            id="run-9",
            name=kw["name"],
            parent_run_id=kw.get("parent_run_id"),
            dataset=kw["dataset"],
            metrics={"recall@k": 1.0, "mrr": 1.0, "ndcg@k": 1.0, "hit_rate": 1.0},
            result=[{"query": "q", "recall@k": 1.0}],
            created_at=NOW,
        )

    from app.core import deps as deps_mod

    app.dependency_overrides[deps_mod.get_db] = lambda: s
    try:
        with (
            patch(
                "app.api.evaluations.create_and_run_evaluation",
                side_effect=fake_create,
            ),
            patch("app.api.evaluations.record_audit") as audit,
        ):
            r = client_post()
        assert r.status_code == 201, r.text
        body = r.json()["data"]
        assert body["metrics"]["recall@k"] == 1.0
        kw = audit.call_args.kwargs
        assert kw["action"] == "eval.run"
        assert kw["detail"]["queries"] == 1
    finally:
        _reset()


def client_post() -> object:
    from fastapi.testclient import TestClient

    return TestClient(app).post(
        "/api/evaluations",
        json={
            "name": "nightly",
            "top_k": 5,
            "dataset": [{"query": "payroll", "expected_doc_ids": ["A"]}],
        },
    )


def test_dataset_validation_rejects_blank_and_bad() -> None:
    _auth()
    from fastapi.testclient import TestClient

    c = TestClient(app)
    try:
        r = c.post("/api/evaluations", json={"name": "x", "dataset": []})
        assert r.status_code == 422
        r = c.post(
            "/api/evaluations",
            json={"name": "x", "dataset": [{"query": "", "expected_doc_ids": ["A"]}]},
        )
        assert r.status_code == 422
        r = c.post(
            "/api/evaluations",
            json={"name": "x", "dataset": [{"query": "q", "expected_doc_ids": []}]},
        )
        assert r.status_code == 422
    finally:
        _reset()


def test_evaluation_history_404_for_other_tenant() -> None:
    _auth()
    from app.core import deps as deps_mod

    s = MagicMock()
    s.get.return_value = SimpleNamespace(  # cross-tenant row
        id="run-7", tenant_id="00000000-0000-0000-0000-000000000099"
    )
    app.dependency_overrides[deps_mod.get_db] = lambda: s
    from fastapi.testclient import TestClient

    c = TestClient(app)
    try:
        r = c.get("/api/evaluations/run-7")
        assert r.status_code == 404, r.text
    finally:
        _reset()


def _mutable_run() -> SimpleNamespace:
    return SimpleNamespace(
        id="run-5",
        tenant_id=TENANT,
        name="nightly",
        parent_run_id=None,
        dataset=[{"query": "q1", "expected_doc_ids": ["A"]}],
        metrics={"recall@k": 0.5},
        result=[
            {
                "query": "q1",
                "expected_doc_ids": ["A"],
                "hit_doc_ids": ["B"],
                "first_hit_rank": 0.0,
            },
        ],
        created_at=NOW,
    )


def test_review_result_attaches_verdict_and_audits() -> None:
    _auth()
    from app.core import deps as deps_mod

    run = _mutable_run()
    s = MagicMock()
    s.get.return_value = run
    app.dependency_overrides[deps_mod.get_db] = lambda: s
    from fastapi.testclient import TestClient

    c = TestClient(app)
    try:
        with patch("app.api.evaluations.record_audit") as audit:
            r = c.patch(
                "/api/evaluations/run-5/results/0",
                json={"verdict": "missed", "note": "should hit A"},
            )
        assert r.status_code == 200, r.text
        assert run.result[0]["review"] == {
            "verdict": "missed",
            "note": "should hit A",
        }
        kw = audit.call_args.kwargs
        assert kw["action"] == "eval.review"
        assert kw["detail"]["verdict"] == "missed"
    finally:
        _reset()


def test_review_result_out_of_range_400() -> None:
    _auth()
    from app.core import deps as deps_mod

    run = _mutable_run()
    s = MagicMock()
    s.get.return_value = run
    app.dependency_overrides[deps_mod.get_db] = lambda: s
    from fastapi.testclient import TestClient

    c = TestClient(app)
    try:
        r = c.patch("/api/evaluations/run-5/results/9", json={"verdict": "correct"})
        assert r.status_code == 400, r.text
        r = c.patch("/api/evaluations/run-5/results/0", json={"verdict": "bogus"})
        assert r.status_code == 422, r.text
    finally:
        _reset()
