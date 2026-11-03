r"""Business-data cleanup: keep seed config, wipe everything else.

Keeps seed configuration (tenants / users / datasources / embedding_models);
wipes all business rows + Qdrant points + MinIO objects.

    $env:PYTHONPATH='D:\Projects\RAGIMS\backend'
    .\env\Scripts\python.exe -X utf8 scripts\cleanup.py
"""

from __future__ import annotations

from app.core.db import SessionLocal
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.ingestion_job import IngestionJob
from app.models.job_step import JobStep
from app.services.storage import get_storage
from sqlalchemy import delete, func, select


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def main() -> None:
    svc = get_storage()

    with SessionLocal() as s:
        print("before:",
              f"documents={count(s, Document)}",
              f"versions={count(s, DocumentVersion)}",
              f"chunks={count(s, Chunk)}",
              f"jobs={count(s, IngestionJob)}",
              f"steps={count(s, JobStep)}")

        # children first (FK-safe); TRUNCATE would need FK checks off anyway
        s.execute(delete(JobStep))
        s.execute(delete(IngestionJob))
        s.execute(delete(Chunk))
        s.execute(delete(DocumentVersion))
        s.execute(delete(Document))
        s.commit()

        print("after:",
              f"documents={count(s, Document)}",
              f"versions={count(s, DocumentVersion)}",
              f"chunks={count(s, Chunk)}",
              f"jobs={count(s, IngestionJob)}",
              f"steps={count(s, JobStep)}")

    # Qdrant: drop + recreate the collection (dimension from current settings)
    store = svc.vectors
    name = "documents"
    try:
        store._client.delete_collection(name)
        print(f"qdrant: collection '{name}' dropped")
    except Exception as exc:  # noqa: BLE001 — collection may not exist
        print(f"qdrant: drop skipped ({type(exc).__name__})")
    dim = svc.ensure_vector_collection()
    print(f"qdrant: collection '{name}' recreated (dim={dim})")

    # MinIO: wipe every object in both buckets
    removed = 0
    for bucket in ("raw-docs", "parsed-text"):
        objs = svc.objects._client.list_objects(bucket, recursive=True)
        for obj in list(objs):
            svc.objects.delete_object(bucket, obj.object_name)
            removed += 1
    print(f"minio: removed {removed} objects from raw-docs + parsed-text")
    print("\ncleanup done (seed configuration kept)")


if __name__ == "__main__":
    main()
