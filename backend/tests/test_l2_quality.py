"""L2 quality-check tests (offline): pure checkers + DB behavior + API shape.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_l2_quality.py -v -p no:cacheprovider
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.main import app
from app.services.quality_service import (
    CHECK_TYPES,
    check_duplicate_ratio,
    check_empty_ratio,
    check_length_spread,
)
from fastapi.testclient import TestClient

client = TestClient(app)

TENANT = "00000000-0000-0000-0000-000000000001"
DOC = "00000000-0000-0000-0000-0000000000a1"
NOW = datetime(2026, 11, 6, 12, 0, 0)

BODY = "the quick brown fox jumps over the lazy dog " * 3  # ~135 chars


# --------------------------------------------------------------------------- #
# pure checkers
# --------------------------------------------------------------------------- #


def test_empty_ratio_scores_risk_share() -> None:
    result = check_empty_ratio([BODY, BODY, "tiny", "  "])
    assert result.check_type == "empty_ratio"
    assert result.score == 0.5  # 2 of 4 near-empty
    assert result.detail["empty"] == 2


def test_empty_ratio_full_body_is_clean() -> None:
    assert check_empty_ratio([BODY] * 5).score == 0.0


def test_duplicate_ratio_counts_repeats() -> None:
    result = check_duplicate_ratio([BODY, BODY, BODY, "different text entirely"])
    # 3 copies of the same normalized text → 3 rows are duplicates
    assert result.score == 0.75
    assert result.detail["unique"] == 2


def test_duplicate_ratio_normalizes_whitespace_and_case() -> None:
    assert check_duplicate_ratio(["A B  C", "a b c", "abc "]).score == 1.0


def test_length_spread_uniform_is_zero() -> None:
    texts = [BODY] * 4  # identical lengths
    result = check_length_spread(texts)
    assert result.score == 0.0


def test_length_spread_wild_mix_caps_at_one() -> None:
    texts = ["a", BODY * 10]
    result = check_length_spread(texts)
    assert result.score <= 1.0
    assert result.score > 0.5  # clearly unstable chunking


def test_checkers_cover_all_declared_types() -> None:
    assert set(CHECK_TYPES) == {
        "empty_ratio",
        "duplicate_ratio",
        "length_spread",
    }


# --------------------------------------------------------------------------- #
# read API
# --------------------------------------------------------------------------- #


def _auth(role: str = "admin") -> None:
    from app.core import deps as deps_mod
    from app.core.deps import CurrentUser

    app.dependency_overrides[deps_mod.get_current_user] = lambda: CurrentUser(
        id="00000000-0000-0000-0000-000000000002",
        tenant_id=TENANT,
        username="admin",
        role=role,
    )


def _quality_rows() -> list[tuple[SimpleNamespace, int]]:
    def row(check_type: str, score: float, version: int) -> tuple[SimpleNamespace, int]:
        return (
            SimpleNamespace(
                doc_version_id=f"dv-{version}",
                check_type=check_type,
                score=score,
                detail={"chunks": 10},
                created_at=NOW,
            ),
            version,
        )

    return [
        row("duplicate_ratio", 0.1, 2),
        row("empty_ratio", 0.0, 2),
        row("length_spread", 0.4, 2),
        row("empty_ratio", 0.3, 1),
    ]


def test_quality_api_grouped_and_ordered() -> None:
    _auth()
    s = MagicMock()
    s.execute.return_value.all.return_value = _quality_rows()
    from app.core import deps as deps_mod

    app.dependency_overrides[deps_mod.get_db] = lambda: s
    try:
        with patch(
            "app.services.document_service.get_document_or_404",
            return_value=MagicMock(id=DOC),
        ):
            r = client.get(f"/api/documents/{DOC}/quality")
        assert r.status_code == 200, r.text
        items = r.json()["data"]
        # newest version first, then check_type alphabetical
        assert [i["version"] for i in items] == [2, 2, 2, 1]
        assert items[0]["check_type"] == "duplicate_ratio"
        assert items[0]["score"] == 0.1
        assert "password" not in str(items)  # paranoia: no secrets leak
    finally:
        app.dependency_overrides.pop(deps_mod.get_db, None)
        from app.core import deps as deps_mod2

        app.dependency_overrides.pop(deps_mod2.get_current_user, None)


def test_quality_api_viewer_can_read() -> None:
    _auth("viewer")
    s = MagicMock()
    s.execute.return_value.all.return_value = []
    from app.core import deps as deps_mod

    app.dependency_overrides[deps_mod.get_db] = lambda: s
    try:
        with patch(
            "app.services.document_service.get_document_or_404",
            return_value=MagicMock(id=DOC),
        ):
            r = client.get(f"/api/documents/{DOC}/quality")
        assert r.status_code == 200, r.text
        assert r.json()["data"] == []
    finally:
        app.dependency_overrides.pop(deps_mod.get_db, None)
        from app.core import deps as deps_mod2

        app.dependency_overrides.pop(deps_mod2.get_current_user, None)


# --------------------------------------------------------------------------- #
# worker integration seam
# --------------------------------------------------------------------------- #


def test_best_effort_swallows_checker_crash() -> None:
    from app.services import quality_service

    with patch.object(
        quality_service, "run_quality_checks", side_effect=RuntimeError("boom")
    ):
        quality_service.best_effort_quality_checks(
            MagicMock(), "dv-1"
        )  # must not raise


def test_run_quality_checks_replaces_previous_rows() -> None:
    """Idempotent re-run: old rows deleted before new ones are added."""
    from app.services import quality_service

    s = MagicMock()
    s.scalars.return_value = [BODY, BODY]  # current chunk texts
    s.get.return_value = SimpleNamespace(id="dv-1")  # version exists
    quality_service.run_quality_checks(s, "dv-1")
    s.execute.assert_called_once()  # exactly one delete
    assert s.add_all.call_count == 1
    rows = s.add_all.call_args.args[0]
    assert len(rows) == 3  # one row per checker
    assert {r.check_type for r in rows} == set(CHECK_TYPES)
