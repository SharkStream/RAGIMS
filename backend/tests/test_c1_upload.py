"""C1 upload tests (offline: pure logic + HTTP layer with a stubbed service).

DB/MinIO/Celery orchestration is verified against the live stack by the C1
runbook probe (see ``docs/tasks/c1-upload-api.md`` — B2/B3 pattern).

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_c1_upload.py -v -p no:cacheprovider
"""

from __future__ import annotations

from unittest.mock import patch

from app.core.errors import AppError
from app.main import app
from app.schemas.document import DocumentUploadResponse
from app.services.document_service import UploadOutcome, validate_upload
from fastapi.testclient import TestClient

client = TestClient(app)

# --------------------------------------------------------------------------- #
# hashing
# --------------------------------------------------------------------------- #


def test_sha256_hex_known_vectors() -> None:
    from app.utils.hashing import sha256_hex

    assert (
        sha256_hex(b"")
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert (
        sha256_hex(b"abc")
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert len(sha256_hex(b"x" * 1024)) == 64


# --------------------------------------------------------------------------- #
# validate_upload
# --------------------------------------------------------------------------- #


def test_validate_accepts_pdf_docx_txt() -> None:
    assert validate_upload("a.pdf", "application/pdf", 10) == "pdf"
    assert (
        validate_upload(
            "a.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            10,
        )
        == "docx"
    )
    assert validate_upload("a.txt", "text/plain", 10) == "txt"
    # tolerant MIME cases
    assert validate_upload("a.docx", "application/zip", 10) == "docx"
    assert validate_upload("a.txt", "application/octet-stream", 10) == "txt"
    assert validate_upload("a.pdf", "application/octet-stream", 10) == "pdf"


def test_validate_rejects_bad_extension_with_415() -> None:
    try:
        validate_upload("evil.exe", "application/octet-stream", 10)
    except AppError as exc:
        assert exc.code == "ERR_FILE_TYPE_NOT_ALLOWED" and exc.status_code == 415
    else:  # pragma: no cover
        raise AssertionError("expected AppError")


def test_validate_rejects_mime_mismatch_with_415() -> None:
    try:
        validate_upload("a.pdf", "text/html", 10)
    except AppError as exc:
        assert exc.code == "ERR_FILE_TYPE_NOT_ALLOWED" and exc.status_code == 415


def test_validate_rejects_oversize_with_413() -> None:
    try:
        validate_upload("a.pdf", "application/pdf", 11, max_bytes=10)
    except AppError as exc:
        assert exc.code == "ERR_FILE_TOO_LARGE" and exc.status_code == 413


def test_validate_rejects_empty_file_with_413() -> None:
    try:
        validate_upload("a.pdf", "application/pdf", 0)
    except AppError as exc:
        assert exc.code == "ERR_FILE_TOO_LARGE" and exc.status_code == 413


# --------------------------------------------------------------------------- #
# schema
# --------------------------------------------------------------------------- #


def test_document_upload_response_shape() -> None:
    payload = DocumentUploadResponse(
        doc_id="d",
        version=1,
        job_id="j",
        status="processing",
        duplicate=False,
        file_path="raw-docs/x",
        content_hash="h" * 64,
    )
    data = payload.model_dump()
    assert set(data) == {
        "doc_id",
        "version",
        "job_id",
        "status",
        "duplicate",
        "file_path",
        "content_hash",
    }
    assert data["duplicate"] is False


# --------------------------------------------------------------------------- #
# HTTP layer (service stubbed)
# --------------------------------------------------------------------------- #


def _fake_outcome(**overrides: object) -> UploadOutcome:
    base = {
        "doc_id": "11111111-1111-1111-1111-111111111111",
        "version": 1,
        "job_id": "22222222-2222-2222-2222-222222222222",
        "status": "processing",
        "duplicate": False,
        "file_path": "raw-docs/t/d/1/f.pdf",
        "content_hash": "a" * 64,
    }
    base.update(overrides)
    return UploadOutcome(**base)  # type: ignore[arg-type]


def test_upload_route_happy_path_envelope() -> None:
    with patch("app.api.documents.upload_document") as fake:
        fake.return_value = _fake_outcome()
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == "OK"
    assert body["data"]["doc_id"].startswith("1111")
    assert body["data"]["duplicate"] is False
    kwargs = fake.call_args.kwargs
    assert kwargs["file_name"] == "doc.pdf" and kwargs["mime"] == "application/pdf"
    assert kwargs["data"] == b"%PDF-1.4"
    assert kwargs["tenant_id"]  # injected from get_current_user stub


def test_upload_route_duplicate_flag_passthrough() -> None:
    with patch("app.api.documents.upload_document") as fake:
        fake.return_value = _fake_outcome(duplicate=True, status="processing")
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
        )
    assert resp.status_code == 201
    assert resp.json()["data"]["duplicate"] is True


def test_upload_route_maps_app_error_envelope() -> None:
    with patch("app.api.documents.upload_document") as fake:
        fake.side_effect = AppError(
            "unsupported file type: exe",
            code="ERR_FILE_TYPE_NOT_ALLOWED",
            status_code=415,
        )
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("evil.exe", b"MZ", "application/octet-stream")},
        )
    assert resp.status_code == 415
    body = resp.json()
    assert body["code"] == "ERR_FILE_TYPE_NOT_ALLOWED"
    assert body["data"] is None
