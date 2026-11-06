"""K6 · 权限与多租户真栈集成（登录 → ACL → 审计全链路）。

默认跳过；对真实栈运行：

    $env:RAGIMS_INTEGRATION=1; pytest tests/test_k_integration.py -m integration

依赖：后端 .env 指向的 MySQL / Qdrant / MinIO / embedding API 在线，且 admin
密码已 seed（scripts/seed.py，默认 admin123）。上传走真实 ``upload_document``
（dispatch 到真 broker），检索走真实 embedder + Qdrant。
"""

from __future__ import annotations

import os
import time
import uuid

import pytest
from app.core.db import SessionLocal
from app.core.security import hash_password, issue_token
from app.main import app
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.ingestion_job import IngestionJob
from app.models.job_step import JobStep
from app.models.user import User
from app.services.document_service import upload_document
from app.services.search_service import search_test
from app.services.storage import get_storage
from fastapi.testclient import TestClient
from qdrant_client import models as qmodels
from sqlalchemy import delete, select, text

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RAGIMS_INTEGRATION") != "1",
        reason="integration suite runs only with RAGIMS_INTEGRATION=1 against a live stack",
    ),
]

TENANT = "00000000-0000-0000-0000-000000000001"
client = TestClient(app)


def _make_viewer() -> tuple[str, str]:
    """Create a real viewer row; return (user_id, bearer token)."""
    uid = str(uuid.uuid4())
    with SessionLocal() as s:
        s.execute(
            text(
                "INSERT INTO users (id, tenant_id, username, role, status, "
                "password_hash, created_at, updated_at) "
                "VALUES (:id, :t, :u, 'viewer', 'active', :ph, NOW(3), NOW(3))"
            ),
            {
                "id": uid,
                "t": TENANT,
                "u": f"viewer_k6_{uid[:8]}",
                "ph": hash_password("v"),
            },
        )
        s.commit()
    tok = issue_token(user_id=uid, tenant_id=TENANT, role="viewer", username="k6viewer")
    return uid, tok


def _drop_viewer(uid: str) -> None:
    with SessionLocal() as s:
        s.execute(delete(User).where(User.id == uid))
        s.commit()


def _admin_token() -> str:
    r = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _cleanup(doc_id: str) -> None:
    svc = get_storage()
    with SessionLocal() as s:
        jids = s.scalars(
            select(IngestionJob.id).where(IngestionJob.doc_id == doc_id)
        ).all()
        for j in jids:
            s.execute(delete(JobStep).where(JobStep.job_id == j))
            s.execute(delete(IngestionJob).where(IngestionJob.id == j))
        vids = s.scalars(
            select(DocumentVersion.id).where(DocumentVersion.doc_id == doc_id)
        ).all()
        s.execute(delete(Chunk).where(Chunk.doc_version_id.in_(vids)))
        s.execute(delete(DocumentVersion).where(DocumentVersion.doc_id == doc_id))
        s.execute(delete(Document).where(Document.id == doc_id))
        s.commit()
    svc.delete_points_by_filter(
        qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="doc_id", match=qmodels.MatchValue(value=doc_id)
                )
            ]
        )
    )


def test_acl_flow_login_patch_search_audit() -> None:
    """登录 → 上传机密文档 → viewer 不可见 → 改回 → 可见 → 审计全有。"""
    marker = f"k6int{int(time.time())}"
    doc_id: str | None = None
    viewer_id, viewer_tok = _make_viewer()
    try:
        # 1. admin login via HTTP (real pbkdf2 + real user row)
        admin_h = {"Authorization": f"Bearer {_admin_token()}"}
        viewer_h = {"Authorization": f"Bearer {viewer_tok}"}

        # 2. real upload (dispatch to the live worker)
        with SessionLocal() as s:
            r = upload_document(
                s,
                data=f"{marker} confidential payroll".encode(),
                file_name=f"{marker}.txt",
                mime="text/plain",
                tenant_id=TENANT,
            )
            doc_id = r.doc_id
        for _ in range(90):
            d = client.get(f"/api/documents/{doc_id}").json()["data"]
            if d.get("status") == "succeeded":
                break
            time.sleep(1)
        assert d["status"] == "succeeded"

        # 3. PATCH level → confidential via HTTP (Qdrant sync path)
        p = client.patch(
            f"/api/documents/{doc_id}",
            json={"access_level": "confidential", "title": marker},
            headers=admin_h,
        )
        assert p.status_code == 200, p.text
        assert p.json()["data"]["access_level"] == "confidential"

        # 4. viewer cannot retrieve it; admin can
        hits_viewer = search_test(
            query=f"{marker} payroll", tenant_id=TENANT, top_k=5, role="viewer"
        ).hits
        hits_admin = search_test(
            query=f"{marker} payroll", tenant_id=TENANT, top_k=5, role="admin"
        ).hits
        assert all(h.doc_id != doc_id for h in hits_viewer)
        assert any(h.doc_id == doc_id for h in hits_admin)

        # 5. level back to internal → viewer sees it immediately
        p2 = client.patch(
            f"/api/documents/{doc_id}",
            json={"access_level": "internal"},
            headers=admin_h,
        )
        assert p2.status_code == 200
        hits_viewer2 = search_test(
            query=f"{marker} payroll", tenant_id=TENANT, top_k=5, role="viewer"
        ).hits
        assert any(h.doc_id == doc_id for h in hits_viewer2)

        # 6. viewer write paths are all 403
        assert (
            client.post(
                "/api/documents/upload",
                files={"file": ("x.txt", b"x", "text/plain")},
                headers=viewer_h,
            ).status_code
            == 403
        )
        assert (
            client.patch(
                f"/api/documents/{doc_id}", json={"title": "nope"}, headers=viewer_h
            ).status_code
            == 403
        )
        assert (
            client.delete(f"/api/documents/{doc_id}", headers=viewer_h).status_code
            == 403
        )

        # 7. audit trail: PATCH rows with correct actor/detail. (The upload
        # above goes through the service layer in-process, so it intentionally
        # leaves no audit row here — the HTTP-path upload row is covered by
        # the K6 probe and K1 tests.)
        logs = client.get(
            "/api/audit-logs",
            params={"resource_id": doc_id, "page_size": 20},
            headers=admin_h,
        ).json()["data"]
        actions = [i["action"] for i in logs["items"]]
        assert "doc.meta_patch" in actions
        patch_row = next(i for i in logs["items"] if i["action"] == "doc.meta_patch")
        assert patch_row["detail"]["fields"]["access_level"] == "internal"

        # 8. tampered token → 401
        tampered = "Bearer " + admin_h["Authorization"][7:-4] + "AAAA"
        assert (
            client.get("/api/auth/me", headers={"Authorization": tampered}).status_code
            == 401
        )
    finally:
        if doc_id is not None:
            _cleanup(doc_id)
        _drop_viewer(viewer_id)
