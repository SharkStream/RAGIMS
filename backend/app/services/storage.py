"""Unified storage facade (B3 step 3).

Composes the MinIO object store and the Qdrant vector store behind two
structural protocols (:class:`ObjectStore`, :class:`VectorStore`) so workers
and services depend on semantics, not implementations — tests swap in fakes
by constructing ``StorageService(fake_objects, fake_vectors)``.

Also owns the raw-document object-key convention shared by C1/D2/E4::

    raw-docs/{tenant_id}/{doc_id}/{version}/{filename}
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Protocol, runtime_checkable

from qdrant_client.http import models as qmodels

from app.clients.minio_client import DEFAULT_PRESIGN_EXPIRES, MinioObjectStore
from app.clients.qdrant_client import COLLECTION_NAME, QdrantVectorStore
from app.core.config import settings


@runtime_checkable
class ObjectStore(Protocol):
    """Object-storage surface required by the pipeline (MinIO today)."""

    def ensure_bucket(self, bucket: str) -> None: ...

    def upload_file(
        self,
        bucket: str,
        object_name: str,
        data_or_path: bytes | bytearray | str | Path,
    ) -> None: ...

    def download_file(self, bucket: str, object_name: str) -> bytes: ...

    def generate_presigned_url(
        self,
        bucket: str,
        object_name: str,
        expires: timedelta = DEFAULT_PRESIGN_EXPIRES,
    ) -> str: ...

    def delete_object(self, bucket: str, object_name: str) -> None: ...

    def object_exists(self, bucket: str, object_name: str) -> bool: ...


@runtime_checkable
class VectorStore(Protocol):
    """Vector-storage surface required by the pipeline (Qdrant today)."""

    def ensure_collection(
        self,
        name: str = COLLECTION_NAME,
        dimension: int | None = None,
        distance: qmodels.Distance = qmodels.Distance.COSINE,
    ) -> str: ...

    def upsert_points(
        self,
        points: list[qmodels.PointStruct],
        collection: str = COLLECTION_NAME,
        wait: bool = True,
    ) -> None: ...

    def delete_by_filter(
        self,
        query_filter: qmodels.Filter,
        collection: str = COLLECTION_NAME,
    ) -> int: ...

    def search(
        self,
        query_vector: list[float],
        query_filter: qmodels.Filter | None = None,
        top_k: int = 5,
        collection: str = COLLECTION_NAME,
        with_payload: bool = True,
    ) -> list[qmodels.ScoredPoint]: ...


class StorageService:
    """Semantic entry point for workers/services (C1, D2, E2/E3, G2)."""

    def __init__(
        self,
        objects: ObjectStore | None = None,
        vectors: VectorStore | None = None,
    ) -> None:
        self.objects: ObjectStore = objects or MinioObjectStore()
        self.vectors: VectorStore = vectors or QdrantVectorStore()

    # -- raw documents (MinIO) ----------------------------------------------

    @staticmethod
    def raw_object_key(tenant_id: str, doc_id: str, version: int, filename: str) -> str:
        """Canonical raw-file object key (C1 upload / D2 parse / E4 cleanup)."""
        return f"{settings.minio.bucket_raw}/{tenant_id}/{doc_id}/{version}/{filename}"

    def store_raw_document(
        self,
        tenant_id: str,
        doc_id: str,
        version: int,
        filename: str,
        data_or_path: bytes | bytearray | str | Path,
    ) -> str:
        """Upload a raw document; return the object key stored under."""
        key = self.raw_object_key(tenant_id, doc_id, version, filename)
        bucket, object_name = key.split("/", 1)
        self.objects.upload_file(bucket, object_name, data_or_path)
        return key

    def read_raw_document(self, object_key: str) -> bytes:
        """Read a raw document by its ``bucket/object`` key."""
        bucket, object_name = object_key.split("/", 1)
        return self.objects.download_file(bucket, object_name)

    def raw_presigned_url(
        self, object_key: str, expires: timedelta = DEFAULT_PRESIGN_EXPIRES
    ) -> str:
        """Time-limited GET URL for a raw document (H2 previews)."""
        bucket, object_name = object_key.split("/", 1)
        return self.objects.generate_presigned_url(bucket, object_name, expires)

    def delete_raw_document(self, object_key: str) -> None:
        """Delete a raw document by its ``bucket/object`` key."""
        bucket, object_name = object_key.split("/", 1)
        self.objects.delete_object(bucket, object_name)

    def ensure_buckets(self) -> None:
        """Create the configured raw/parsed buckets if missing (idempotent)."""
        self.objects.ensure_bucket(settings.minio.bucket_raw)
        self.objects.ensure_bucket(settings.minio.bucket_parsed)

    # -- vectors (Qdrant) ----------------------------------------------------

    def ensure_vector_collection(
        self, dimension: int | None = None, name: str = COLLECTION_NAME
    ) -> str:
        """Idempotent collection creation; dimension defaults to settings."""
        return self.vectors.ensure_collection(name, dimension)

    def upsert_points(
        self,
        points: list[qmodels.PointStruct],
        collection: str = COLLECTION_NAME,
    ) -> None:
        """Idempotent point upsert (deterministic ids, see qdrant_client)."""
        self.vectors.upsert_points(points, collection)

    def delete_points_by_filter(
        self, query_filter: qmodels.Filter, collection: str = COLLECTION_NAME
    ) -> int:
        """Delete points matching a filter; return the pre-delete count."""
        return self.vectors.delete_by_filter(query_filter, collection)

    def search_vectors(
        self,
        query_vector: list[float],
        query_filter: qmodels.Filter | None = None,
        top_k: int = 5,
        collection: str = COLLECTION_NAME,
    ) -> list[qmodels.ScoredPoint]:
        """Top-k similarity search; caller composes tenant/version filters (G2)."""
        return self.vectors.search(
            query_vector,
            query_filter=query_filter,
            top_k=top_k,
            collection=collection,
        )


_storage: StorageService | None = None


def get_storage() -> StorageService:
    """Lazily-built default instance (offline construction, no sockets opened).

    Module-level singleton semantics via :func:`functools.lru_cache`-style
    memoization; tests construct their own ``StorageService(fakes...)``.
    """
    global _storage
    if _storage is None:
        _storage = StorageService()
    return _storage
