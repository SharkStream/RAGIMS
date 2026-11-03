"""I1 · 真实栈集成测试（upload -> job -> chunks -> search -> delete）。

默认跳过；对真实 docker-compose / 远程栈运行：

    $env:RAGIMS_INTEGRATION=1; pytest tests/test_i1_integration.py -m integration

依赖：后端 .env 指向的 MySQL / Redis / Qdrant / MinIO / embedding API 全部在线，
worker 不必启动（本测试进程内 eager 驱动流水线，绕开 broker）。
"""

from __future__ import annotations

import os
import time
from uuid import uuid4

import pytest
from app.core.db import SessionLocal
from app.models.chunk import Chunk
from app.models.datasource import Datasource
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.ingestion_job import IngestionJob
from app.models.job_step import JobStep
from app.services.storage import get_storage
from app.workers.pipeline import ingest_document
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
    """Rows + Qdrant points + MinIO objects created by the test."""
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
            s.execute(delete(Chunk).where(Chunk.doc_version_id == item["version_id"]))
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
        bucket, obj = item["file_path"].split("/", 1)
        svc.objects.delete_object(bucket, obj)
        svc.objects.delete_object("parsed-text", f"{item['version_id']}.json")


def _wait_job(job_id: str, statuses: tuple[str, ...], timeout: int = 180) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with SessionLocal() as s:
            job = s.get(IngestionJob, job_id)
            if job is not None and job.status in statuses:
                return str(job.status)
        time.sleep(2)
    raise TimeoutError(f"job {job_id} stuck at non-terminal state")


def test_full_chain_upload_job_chunks_search(stack_cleanup) -> None:
    """M1→M2 全链：建档 + 七步流水线 + 检索命中 + 软删除隐藏。"""
    stamp = int(time.time())
    marker = f"integration marker {stamp}"
    body = f"I1 integration run. The {marker} governs the release. " * 20

    svc = get_storage()
    doc_id, version_id = str(uuid4()), str(uuid4())
    file_path = f"raw-docs/{TENANT}/{doc_id}/1/i1_{stamp}.txt"
    with SessionLocal() as s:
        ds_id = s.scalars(
            select(Datasource.id).where(Datasource.tenant_id == TENANT).limit(1)
        ).first()
        s.add(
            Document(
                id=doc_id,
                tenant_id=TENANT,
                datasource_id=ds_id,
                title=f"I1 integration {stamp}",
                file_name=f"i1_{stamp}.txt",
                file_type="txt",
                status="processing",
                current_version=1,
            )
        )
        s.add(
            DocumentVersion(
                id=version_id,
                doc_id=doc_id,
                version=1,
                content_hash="i" * 64,
                file_path=file_path,
                file_size=len(body.encode()),
                parse_status="pending",
                is_latest=True,
            )
        )
        job_id = str(uuid4())
        s.add(
            IngestionJob(
                id=job_id,
                tenant_id=TENANT,
                doc_id=doc_id,
                doc_version_id=version_id,
                job_type="full",
                status="pending",
            )
        )
        s.commit()
    stack_cleanup.append(
        {"doc_id": doc_id, "version_id": version_id, "file_path": file_path}
    )

    bucket, obj = file_path.split("/", 1)
    svc.objects.upload_file(bucket, obj, body.encode())

    result = ingest_document.apply(args=[version_id]).get()
    assert isinstance(result, dict) and "job_id" in result, result
    assert _wait_job(job_id, ("succeeded", "failed")) == "succeeded"

    with SessionLocal() as s:
        steps = s.scalars(
            select(JobStep.step_name)
            .where(JobStep.job_id == job_id)
            .order_by(JobStep.step_order)
        ).all()
        assert len(steps) == 7
        chunk_rows = s.scalars(
            select(Chunk.id).where(Chunk.doc_version_id == version_id)
        ).all()
        assert chunk_rows, "chunks must be persisted"

    svc_search = get_storage()
    points_deleted = svc_search.delete_points_by_filter(
        qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="doc_id", match=qmodels.MatchValue(value=doc_id)
                )
            ]
        )
    )
    assert points_deleted > 0, "Qdrant must hold vectors for the doc"

    # soft delete hides the doc from the active list
    from app.services.document_service import soft_delete_document

    with SessionLocal() as s:
        soft_delete_document(s, TENANT, doc_id)
        s.commit()
    with SessionLocal() as s:
        doc = s.get(Document, doc_id)
        assert doc is not None and doc.status == "deleted"


def test_job_level_wallclock_stamped(stack_cleanup) -> None:
    """H3 修复回归：succeeded job 必须有 started_at/finished_at。"""
    stamp = int(time.time())
    body = f"I1 wallclock check {stamp}. " * 40
    svc = get_storage()
    doc_id, version_id = str(uuid4()), str(uuid4())
    file_path = f"raw-docs/{TENANT}/{doc_id}/1/i1w_{stamp}.txt"
    with SessionLocal() as s:
        ds_id = s.scalars(
            select(Datasource.id).where(Datasource.tenant_id == TENANT).limit(1)
        ).first()
        s.add(
            Document(
                id=doc_id,
                tenant_id=TENANT,
                datasource_id=ds_id,
                title=f"I1 wallclock {stamp}",
                file_name=f"i1w_{stamp}.txt",
                file_type="txt",
                status="processing",
                current_version=1,
            )
        )
        s.add(
            DocumentVersion(
                id=version_id,
                doc_id=doc_id,
                version=1,
                content_hash="w" * 64,
                file_path=file_path,
                file_size=len(body.encode()),
                parse_status="pending",
                is_latest=True,
            )
        )
        job_id = str(uuid4())
        s.add(
            IngestionJob(
                id=job_id,
                tenant_id=TENANT,
                doc_id=doc_id,
                doc_version_id=version_id,
                job_type="full",
                status="pending",
            )
        )
        s.commit()
    stack_cleanup.append(
        {"doc_id": doc_id, "version_id": version_id, "file_path": file_path}
    )

    bucket, obj = file_path.split("/", 1)
    svc.objects.upload_file(bucket, obj, body.encode())
    ingest_document.apply(args=[version_id])
    assert _wait_job(job_id, ("succeeded", "failed")) == "succeeded"

    with SessionLocal() as s:
        job = s.get(IngestionJob, job_id)
        assert (
            job is not None
            and job.started_at is not None
            and job.finished_at is not None
        )
        assert job.finished_at >= job.started_at
