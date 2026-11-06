"""K4 retrieval-ACL + access_level sync tests (offline).

* ``search_test``: the role whitelist rides the mandatory Qdrant filter; a
  request ``access_level`` can only narrow it (empty intersection → empty
  result without touching Qdrant).
* ``update_document_meta``: a level change flips the payload on ALL of the
  document's points (J4 semantics: flush → payload → commit; 503 + rollback
  when Qdrant is down).

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_k4_acl.py -v -p no:cacheprovider
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from app.core.errors import AppError
from app.schemas.document import DocumentPatchRequest
from app.services import document_service as dsvc
from app.services.search_service import (
    _mandatory_filter,
    _role_allowed_levels,
    search_test,
)
from qdrant_client import models as qmodels

TENANT = "00000000-0000-0000-0000-000000000001"


def _captured_levels(query_filter: qmodels.Filter) -> list[str] | None:
    for cond in query_filter.must:
        if getattr(cond, "key", None) == "access_level":
            return list(cond.match.any or [])
    return None


def _fake_search_storage(capture: dict) -> MagicMock:
    storage = MagicMock()
    storage.vectors.search.side_effect = (
        lambda vector, query_filter, top_k: capture.update(f=query_filter) or []
    )
    return storage


# --------------------------------------------------------------------------- #
# whitelist mechanics
# --------------------------------------------------------------------------- #


def test_role_whitelists() -> None:
    assert _role_allowed_levels("viewer") == ("public", "internal")
    assert set(_role_allowed_levels("admin")) == {"public", "internal", "confidential"}
    assert set(_role_allowed_levels("editor")) == {"public", "internal", "confidential"}
    assert _role_allowed_levels("ghost") == ("public", "internal")  # least privilege


def test_mandatory_filter_with_levels() -> None:
    f = _mandatory_filter(TENANT, allowed_levels=("public", "internal"))
    keys = [c.key for c in f.must]
    assert keys == ["tenant_id", "is_latest", "is_deleted", "access_level"]
    assert _captured_levels(f) == ["public", "internal"]
    assert _captured_levels(_mandatory_filter(TENANT)) is None  # pre-K4 shape


# --------------------------------------------------------------------------- #
# search_test ACL
# --------------------------------------------------------------------------- #


def _run_search(role: str, filters: dict | None, storage: MagicMock) -> None:
    with (
        patch("app.services.search_service.SessionLocal") as sl,
        patch("app.services.search_service.get_default_embedder") as gde,
    ):
        sl.return_value.__enter__.return_value = SimpleNamespace()
        gde.return_value.embed_batch.return_value = [[0.0] * 4]
        search_test(
            query="q",
            tenant_id=TENANT,
            top_k=5,
            filters=filters,
            role=role,
            storage=storage,
        )


def test_viewer_search_filters_confidential_out() -> None:
    capture: dict = {}
    _run_search("viewer", None, _fake_search_storage(capture))
    assert sorted(_captured_levels(capture["f"])) == ["internal", "public"]


def test_request_level_narrows_but_never_widens() -> None:
    capture: dict = {}
    _run_search("viewer", {"access_level": "internal"}, _fake_search_storage(capture))
    assert _captured_levels(capture["f"]) == ["internal"]

    capture2: dict = {}
    _run_search(
        "admin", {"access_level": "confidential"}, _fake_search_storage(capture2)
    )
    assert _captured_levels(capture2["f"]) == ["confidential"]


def test_empty_intersection_returns_no_hits_without_qdrant() -> None:
    storage = _fake_search_storage({})
    result = search_test(
        query="q",
        tenant_id=TENANT,
        top_k=5,
        filters={"access_level": "confidential"},
        role="viewer",
        storage=storage,
    )
    assert result.hits == []
    storage.vectors.search.assert_not_called()


# --------------------------------------------------------------------------- #
# update_document_meta level sync
# --------------------------------------------------------------------------- #


def _patched_doc(level: str = "internal") -> SimpleNamespace:
    return SimpleNamespace(
        id="0" * 36,
        tenant_id=TENANT,
        status="succeeded",
        access_level=level,
        title="old",
        tags=None,
    )


def test_level_change_syncs_qdrant_payload() -> None:
    doc = _patched_doc("internal")
    session = MagicMock()
    session.get.return_value = doc
    storage = MagicMock()

    body = DocumentPatchRequest(access_level="confidential", title="new")
    dsvc.update_document_meta(session, TENANT, doc.id, body, storage=storage)

    args = storage.set_payload_by_filter.call_args
    assert args.args[0] == {"access_level": "confidential"}
    f = args.args[1]
    keys = {c.key for c in f.must}
    assert keys == {"tenant_id", "doc_id"}  # ALL versions of this doc
    session.flush.assert_called_once()
    session.commit.assert_called_once()


def test_level_unchanged_skips_qdrant() -> None:
    doc = _patched_doc("internal")
    session = MagicMock()
    session.get.return_value = doc
    storage = MagicMock()

    body = DocumentPatchRequest(access_level="internal", title="new")
    dsvc.update_document_meta(session, TENANT, doc.id, body, storage=storage)

    storage.set_payload_by_filter.assert_not_called()
    session.commit.assert_called_once()


def test_qdrant_down_rolls_back_with_503() -> None:
    doc = _patched_doc("internal")
    session = MagicMock()
    session.get.return_value = doc
    storage = MagicMock()
    storage.set_payload_by_filter.side_effect = RuntimeError("qdrant down")

    body = DocumentPatchRequest(access_level="confidential")
    with pytest.raises(AppError) as exc:
        dsvc.update_document_meta(session, TENANT, doc.id, body, storage=storage)
    assert exc.value.status_code == 503
    session.rollback.assert_called_once()
    session.commit.assert_not_called()
