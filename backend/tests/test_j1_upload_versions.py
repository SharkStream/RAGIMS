"""J1 upload three-way resolution tests (offline — patched collaborators).

The DB semantics (row lock, generated-column unique key, gap-lock deadlock
retry) are verified against the live stack (J1 probe + J6 integration); these
tests pin the routing and outcome shapes without a database.
"""

from __future__ import annotations

from unittest.mock import patch

from app.services import document_service as ds
from app.services.document_service import upload_document
from app.utils.hashing import sha256_hex


class _Obj:
    def __init__(self, **kw: object) -> None:
        self.__dict__.update(kw)


def _fake_session() -> object:
    return object()  # collaborators are patched; never touched directly


_TENANT = "00000000-0000-0000-0000-000000000001"


def _patch_no_storage() -> dict[str, object]:
    return {}


def test_upload_creates_new_document_when_no_head() -> None:
    outcome = ds.UploadOutcome(
        doc_id="d1",
        version=1,
        job_id="j1",
        status="processing",
        duplicate=False,
        file_path="raw-docs/t/d1/1/a.txt",
        content_hash="h1",
    )
    with (
        patch.object(ds, "_find_version_head", return_value=None),
        patch.object(
            ds,
            "_create_document",
            return_value=outcome,
        ) as create,
        patch.object(ds, "get_storage", return_value=object()),
    ):
        result = upload_document(
            _fake_session(),  # type: ignore[arg-type]
            data=b"x",
            file_name="a.txt",
            mime="text/plain",
            tenant_id=_TENANT,
        )
    assert result is outcome and result.version == 1 and result.duplicate is False
    create.assert_called_once()
    assert create.call_args.kwargs["content_hash"]


def test_upload_same_hash_returns_duplicate() -> None:
    head = _Obj(id="d1", current_version=2, status="succeeded", tenant_id=_TENANT)
    latest = _Obj(
        id="v2",
        version=2,
        content_hash=sha256_hex(b"same"),
        is_latest=True,
        file_path="p2",
    )
    outcome = ds.UploadOutcome(
        doc_id="d1",
        version=2,
        job_id="j2",
        status="succeeded",
        duplicate=True,
        file_path="p2",
        content_hash="h2",
    )
    with (
        patch.object(ds, "_find_version_head", return_value=head),
        patch.object(ds, "_latest_version_of", return_value=latest),
        patch.object(ds, "_latest_job_of", return_value=None),
        patch.object(ds, "_duplicate_outcome", return_value=outcome) as dup,
        patch.object(ds, "get_storage", return_value=object()),
    ):
        result = upload_document(
            _fake_session(),  # type: ignore[arg-type]
            data=b"same",
            file_name="a.txt",
            mime="text/plain",
            tenant_id=_TENANT,
        )
    assert result.duplicate is True and result.version == 2
    dup.assert_called_once()


def test_upload_different_hash_appends_version() -> None:
    head = _Obj(id="d1", current_version=2, status="succeeded", tenant_id=_TENANT)
    latest = _Obj(
        id="v2", version=2, content_hash="h-old", is_latest=True, file_path="p2"
    )
    outcome = ds.UploadOutcome(
        doc_id="d1",
        version=3,
        job_id="j3",
        status="processing",
        duplicate=False,
        file_path="p3",
        content_hash="h-new",
    )
    with (
        patch.object(ds, "_find_version_head", return_value=head),
        patch.object(ds, "_latest_version_of", return_value=latest),
        patch.object(ds, "_append_version", return_value=outcome) as append,
        patch.object(ds, "get_storage", return_value=object()),
    ):
        result = upload_document(
            _fake_session(),  # type: ignore[arg-type]
            data=b"new",
            file_name="a.txt",
            mime="text/plain",
            tenant_id=_TENANT,
        )
    assert result.duplicate is False and result.version == 3
    append.assert_called_once()
    kwargs = append.call_args.kwargs
    assert kwargs["head"] is head and kwargs["latest"] is latest


def test_append_version_demotes_old_latest_and_bumps_head() -> None:
    """Pure-shape check of the append branch via a fake session (no DB)."""
    calls: dict[str, object] = {}
    head = _Obj(id="d1", tenant_id=_TENANT, current_version=2, status="succeeded")
    latest = _Obj(id="v2", version=2, is_latest=True)
    created_version = _Obj(id=None)

    class FakeSession:
        def add(self, obj: object) -> None:
            calls["added"] = obj
            created_version.id = "v3"

        def flush(self) -> None:
            calls["flushed"] = True

        def commit(self) -> None:
            calls["committed"] = True

    storage = _Obj(objects=_Obj(upload_file=lambda b, o, d: calls.setdefault("obj", o)))
    with (
        patch.object(ds, "_dispatch_ingestion", return_value=None),
        patch.object(ds, "get_storage", return_value=storage),
    ):
        outcome = ds._append_version(
            FakeSession(),  # type: ignore[arg-type]
            head=head,  # type: ignore[arg-type]
            latest=latest,  # type: ignore[arg-type]
            ext="txt",
            data=b"body",
            file_name="a.txt",
            content_hash="h3",
            user_id=None,
            storage=storage,  # type: ignore[arg-type]
        )

    assert latest.is_latest is False
    assert head.current_version == 3 and head.status == "processing"
    assert outcome.version == 3 and outcome.duplicate is False
    assert "/d1/3/a.txt" in outcome.file_path
    assert calls["committed"] is True
    assert isinstance(created_version, _Obj)
