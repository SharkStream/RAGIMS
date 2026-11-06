"""Wipe all business data, keeping the ``admin`` user (ops utility).

Cleans, in dependency order:

* MySQL: quality_checks / chunks / job_steps / ingestion_jobs /
  document_versions / documents / evaluation_runs / audit_logs, then every
  user except ``username = 'admin'``.
  Bootstrap rows (tenants / datasources / embedding_models) are KEPT — the
  admin account and the default model wiring depend on them.
* Qdrant: the ``documents`` collection is dropped and recreated (dimension
  from settings) so no ghost vectors survive.
* MinIO: every object in the raw / parsed buckets is removed.

Usage (from ``backend/``)::

    env/Scripts/python.exe scripts/cleanup.py --dry-run   # counts only
    env/Scripts/python.exe scripts/cleanup.py             # asks for typing YES
    env/Scripts/python.exe scripts/cleanup.py --yes       # no prompt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clients.minio_client import MinioObjectStore  # noqa: E402
from app.clients.qdrant_client import QdrantVectorStore  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.models import (  # noqa: E402
    AuditLog,
    Chunk,
    Document,
    DocumentVersion,
    EvaluationRun,
    IngestionJob,
    JobStep,
    QualityCheck,
    User,
)
from sqlalchemy import delete, func, select  # noqa: E402

setup_logging(level=settings.app.log_level)

KEEP_USERNAME = "admin"

#: Deletion order (children before parents; FKs are RESTRICT).
MYSQL_ORDER: list[tuple[str, type]] = [
    ("quality_checks", QualityCheck),
    ("chunks", Chunk),
    ("job_steps", JobStep),
    ("ingestion_jobs", IngestionJob),
    ("document_versions", DocumentVersion),
    ("documents", Document),
    ("evaluation_runs", EvaluationRun),
    ("audit_logs", AuditLog),
]


def _counts() -> dict[str, int]:
    """Row counts for every table that will be touched, plus leftover users."""
    counts: dict[str, int] = {}
    with SessionLocal() as session:
        for name, model in MYSQL_ORDER:
            counts[name] = int(
                session.scalar(select(func.count()).select_from(model)) or 0
            )
        counts["users(removed)"] = int(
            session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.username != KEEP_USERNAME)
            )
            or 0
        )
    return counts


def _wipe_mysql() -> dict[str, int]:
    """Delete business rows in FK order + non-admin users, single commit."""
    removed: dict[str, int] = {}
    with SessionLocal() as session:
        for name, model in MYSQL_ORDER:
            result = session.execute(delete(model))
            removed[name] = int(result.rowcount or 0)
        result = session.execute(delete(User).where(User.username != KEEP_USERNAME))
        removed["users(removed)"] = int(result.rowcount or 0)
        session.commit()
    return removed


def _wipe_qdrant() -> str:
    """Drop + recreate the collection (dimension from settings)."""
    store = QdrantVectorStore()
    name = store.ensure_collection()  # no-op if missing
    store._client.delete_collection(name)
    name = store.ensure_collection()
    return name


def _wipe_minio() -> dict[str, int]:
    """Remove every object from the raw / parsed buckets."""
    objects = MinioObjectStore()
    removed: dict[str, int] = {}
    for bucket in (settings.minio.bucket_raw, settings.minio.bucket_parsed):
        names = [
            o.object_name for o in objects._client.list_objects(bucket, recursive=True)
        ]
        for name in names:
            objects._client.remove_object(bucket, name)
        removed[bucket] = len(names)
    return removed


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Wipe business data (keep admin).")
    parser.add_argument("--dry-run", action="store_true", help="print counts only")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation")
    args = parser.parse_args(argv)

    counts = _counts()
    print(
        "== 将清除以下数据（保留 tenants/datasources/embedding_models 与 admin 用户）=="
    )
    for name, n in counts.items():
        print(f"  {name:22s} {n} 行")
    print("  qdrant                documents collection 重建（清空全部向量点）")
    print("  minio                 raw/parsed 两桶对象全删")

    if args.dry_run:
        print("[dry-run] 未做任何修改")
        return 0
    if not args.yes:
        answer = input("确认清空？输入 YES 继续：").strip()
        if answer != "YES":
            print("已取消")
            return 2

    removed = _wipe_mysql()
    for name, n in removed.items():
        print(f"- mysql {name:22s} 删除 {n} 行")

    collection = _wipe_qdrant()
    print(f"- qdrant collection '{collection}' 已重建（向量点清零）")

    objects = _wipe_minio()
    for bucket, n in objects.items():
        print(f"- minio {bucket}: 删除 {n} 个对象")

    # 健全性检查：admin 仍在、文档归零
    with SessionLocal() as session:
        admin = session.scalars(
            select(User).where(User.username == KEEP_USERNAME)
        ).one_or_none()
        docs_left = int(session.scalar(select(func.count()).select_from(Document)) or 0)
    print(f"- 校验：admin 保留={admin is not None}，documents 剩余={docs_left}")
    print("CLEANUP DONE ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
