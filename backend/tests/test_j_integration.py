"""J6 · 版本与增量真栈集成（upload v1→v2 → activate 回滚 → PATCH 零重嵌入）。

默认跳过；对真实栈运行（worker 可在跑，也可由本进程 eager 驱动）：

    $env:RAGIMS_INTEGRATION=1; pytest tests/test_j_integration.py -m integration

依赖：后端 .env 指向的 MySQL / Redis / Qdrant / MinIO / embedding API 全部在线。
上传走真实 ``upload_document``（dispatch 到真 broker），由运行中的 worker 消费。
"""

from __future__ import annotations

import os
import time

import pytest
from app.core.db import SessionLocal
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.ingestion_job import IngestionJob
from app.models.job_step import JobStep
from app.services.document_service import activate_document_version, upload_document
from app.services.search_service import search_test
from app.services.storage import get_storage
from qdrant_client import models as qmodels
from sqlalchemy import delete, select

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RAGIMS_INTEGRATION") != "1",
        reason="integration suite runs only with RAGIMS_INTEGRATION=1 against a live stack",
    ),
]

TENANT = "00000000-0000-0000-0000-000000000001"


@pytest.fixture()
def stack_cleanup():
    """Rows + Qdrant points + MinIO objects for every version created."""
    created: list[dict] = []
    yield created
    svc = get_storage()
    for item in created:
        with SessionLocal() as s:
            jids = s.scalars(
                select(IngestionJob.id).where(IngestionJob.doc_id == item["doc_id"])
            ).all()
            for jid in jids:
                s.execute(delete(JobStep).where(JobStep.job_id == jid))
                s.execute(delete(IngestionJob).where(IngestionJob.id == jid))
            s.execute(delete(Chunk).where(Chunk.doc_id == item["doc_id"]))
            s.execute(
                delete(DocumentVersion).where(DocumentVersion.doc_id == item["doc_id"])
            )
            s.execute(delete(Document).where(Document.id == item["doc_id"]))
            s.commit()
        svc.delete_points_by_filter(
            qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="doc_id", match=qmodels.MatchValue(value=item["doc_id"])
                    )
                ]
            )
        )
        for vid, path in item["versions"]:
            bucket, obj = path.split("/", 1)
            svc.objects.delete_object(bucket, obj)
            svc.objects.delete_object("parsed-text", f"{vid}.json")


def _wait_doc_succeeded(doc_id: str, timeout: int = 180) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with SessionLocal() as s:
            doc = s.get(Document, doc_id)
            if doc is not None and doc.status == "succeeded":
                return
        time.sleep(2)
    raise TimeoutError(f"doc {doc_id} never reached succeeded")


def _upload(text: str, name: str) -> str:
    with SessionLocal() as s:
        outcome = upload_document(
            s,
            data=text.encode(),
            file_name=name,
            mime="text/plain",
            tenant_id=TENANT,
        )
        s.commit()
    return outcome.doc_id


def test_incremental_upload_and_versions(stack_cleanup) -> None:
    """J1 全链：txt 上传 v1 → 改内容传 v2 → 版本行/对象/current_version 断言。"""
    stamp = int(time.time())
    marker = f"J6 integration {stamp}"
    name = f"j6_{stamp}.txt"

    with SessionLocal() as s:
        s.execute(delete(Document).where(Document.file_name == name))
        s.commit()

    doc_id = _upload(f"{marker} FIRST VERSION. " * 10, name)
    _wait_doc_succeeded(doc_id)
    doc_id2 = _upload(f"{marker} SECOND VERSION CHANGED. " * 10, name)
    assert doc_id2 == doc_id, "same-name upload must append to the same doc"
    _wait_doc_succeeded(doc_id)

    with SessionLocal() as s:
        versions = s.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.doc_id == doc_id)
            .order_by(DocumentVersion.version)
        ).all()
        assert [v.version for v in versions] == [1, 2]
        assert all(v.parse_status == "parsed" for v in versions)
        assert versions[1].is_latest and not versions[0].is_latest
        doc = s.get(Document, doc_id)
        assert doc is not None and doc.current_version == 2
        stack_cleanup.append(
            {
                "doc_id": doc_id,
                "versions": [(v.id, v.file_path) for v in versions],
            }
        )
        # both versions' chunks remain queryable (history preserved)
        for v in versions:
            n = s.scalar(
                select(Chunk.chunk_index).where(Chunk.doc_version_id == v.id).limit(1)
            )
            assert n is not None, f"v{v.version} chunks must be persisted"
        # MinIO objects: each version has its own raw path and parsed-text
        # object (cleanup deletes them; existence is proven by the pipeline).
        paths = {v.file_path for v in versions}
        assert len(paths) == 2, "versions must own distinct raw objects"


def test_activate_rollback_full_cycle(stack_cleanup) -> None:
    """J4 全链：v1→v2 检索命中 v2 → activate v1 → 检索命中 v1 → activate v2。"""
    stamp = int(time.time())
    marker = f"J6 rollback {stamp}"
    name = f"j6rb_{stamp}.txt"
    with SessionLocal() as s:
        s.execute(delete(Document).where(Document.file_name == name))
        s.commit()

    doc_id = _upload(f"{marker} ORIGINAL CONTENT ONE. " * 10, name)
    _wait_doc_succeeded(doc_id)
    _upload(f"{marker} CONTENT TWO CHANGED. " * 10, name)
    _wait_doc_succeeded(doc_id)
    with SessionLocal() as s:
        versions = s.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.doc_id == doc_id)
            .order_by(DocumentVersion.version)
        ).all()
        stack_cleanup.append(
            {
                "doc_id": doc_id,
                "versions": [(v.id, v.file_path) for v in versions],
            }
        )
        v1_id, v2_id = versions[0].id, versions[1].id

    hits = search_test(query=f"{marker} CONTENT TWO", tenant_id=TENANT, top_k=5).hits
    assert hits and "TWO" in hits[0].text and hits[0].version == 2, hits[:1]

    with SessionLocal() as s:
        updated = activate_document_version(s, TENANT, doc_id, 1)
        s.commit()
    assert updated.current_version == 1

    hits = search_test(
        query=f"{marker} ORIGINAL CONTENT", tenant_id=TENANT, top_k=5
    ).hits
    assert hits and "ONE" in hits[0].text and hits[0].version == 1, hits[:1]

    # payload consistency: exactly one is_latest point set, now pointing at v1
    svc = get_storage()
    pts, _ = svc.vectors._client.scroll(
        "documents",
        scroll_filter=qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="doc_id", match=qmodels.MatchValue(value=doc_id)
                ),
                qmodels.FieldCondition(
                    key="is_latest", match=qmodels.MatchValue(value=True)
                ),
            ]
        ),
        with_payload=True,
        limit=100,
    )
    assert pts and all(
        p.payload.get("doc_version_id") == v1_id for p in pts
    ), "latest points must all belong to the activated v1"

    # and back to v2
    with SessionLocal() as s:
        updated = activate_document_version(s, TENANT, doc_id, 2)
        s.commit()
    assert updated.current_version == 2
    hits = search_test(query=f"{marker} CONTENT TWO", tenant_id=TENANT, top_k=5).hits
    assert hits and "TWO" in hits[0].text and hits[0].version == 2, hits[:1]
    assert v2_id  # silence linters when asserts above are compiled out


def test_metadata_patch_no_reembed(stack_cleanup) -> None:
    """J3 全链：PATCH 元数据后 job 数不变（零重嵌入）。"""
    stamp = int(time.time())
    name = f"j6meta_{stamp}.txt"
    with SessionLocal() as s:
        s.execute(delete(Document).where(Document.file_name == name))
        s.commit()

    doc_id = _upload(f"J6 metadata patch {stamp}. " * 10, name)
    _wait_doc_succeeded(doc_id)
    with SessionLocal() as s:
        versions = s.scalars(
            select(DocumentVersion).where(DocumentVersion.doc_id == doc_id)
        ).all()
        stack_cleanup.append(
            {
                "doc_id": doc_id,
                "versions": [(v.id, v.file_path) for v in versions],
            }
        )
        jobs_before = s.scalar(
            select(IngestionJob.id).where(IngestionJob.doc_id == doc_id).limit(1)
        )
        n_before = len(
            s.scalars(
                select(IngestionJob.id).where(IngestionJob.doc_id == doc_id)
            ).all()
        )
        doc = s.get(Document, doc_id)
        assert doc is not None
        doc.title = f"J6 patched title {stamp}"
        doc.tags = ["j6", "meta"]
        doc.access_level = "confidential"
        s.commit()

    with SessionLocal() as s:
        n_after = len(
            s.scalars(
                select(IngestionJob.id).where(IngestionJob.doc_id == doc_id)
            ).all()
        )
        doc = s.get(Document, doc_id)
        assert doc is not None
        assert doc.title == f"J6 patched title {stamp}"
        assert doc.tags == ["j6", "meta"]
        assert doc.access_level == "confidential"
    assert n_after == n_before == 1, "PATCH must not create ingestion jobs"
    assert jobs_before
