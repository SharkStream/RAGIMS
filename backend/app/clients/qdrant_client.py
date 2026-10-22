"""Qdrant vector-store wrapper (B3 step 2).

Builds on the A2 ``ensure_collection`` probe and adds the write/search
operations the ingestion pipeline (D4/E2/E3) needs:

* :func:`chunk_point_id` — deterministic point ids from
  ``(doc_version_id, chunk_index)`` via UUID5. Re-uploading the same version
  therefore **upserts** the same points (idempotent E2 writes) instead of
  creating duplicates; ``delete_by_filter`` can always roll back a version.
* :class:`QdrantVectorStore` — thin facade with an injectable
  :class:`qdrant_client.QdrantClient` for tests.
"""

from __future__ import annotations

from uuid import UUID, uuid5

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings

COLLECTION_NAME = "documents"

#: Fixed namespace for chunk point ids (B3 step 2). Changing it invalidates
#: every stored mapping — treat as stable after the first migration.
_POINT_NAMESPACE: UUID = uuid5(
    UUID("00000000-0000-0000-0000-000000000000"), "ragims.chunk-point"
)

#: Default HNSW-ish tuning is left to Qdrant server defaults (MVP).
DEFAULT_DISTANCE = qmodels.Distance.COSINE


def build_client(timeout: int | None = None) -> QdrantClient:
    """Create a QdrantClient from settings (REST transport).

    ``timeout`` caps request time in seconds — pass a small value for probes
    (e.g. the /readyz readiness check); omit it for normal pipeline use.
    """
    if settings.qdrant.api_key:
        return QdrantClient(
            url=settings.qdrant.url, api_key=settings.qdrant.api_key, timeout=timeout
        )
    return QdrantClient(
        host=settings.qdrant.host, port=settings.qdrant.port, timeout=timeout
    )


def chunk_point_id(doc_version_id: str, chunk_index: int) -> str:
    """Deterministic point id for ``(doc_version_id, chunk_index)``.

    Same input always yields the same UUID string — this is what makes upsert
    and version rollback idempotent.
    """
    return str(uuid5(_POINT_NAMESPACE, f"{doc_version_id}:{chunk_index}"))


class QdrantVectorStore:
    """Vector storage facade used by :class:`~app.services.storage.StorageService`."""

    def __init__(self, client: QdrantClient | None = None) -> None:
        self._client = client or build_client()

    # -- collections --------------------------------------------------------

    def ensure_collection(
        self,
        name: str = COLLECTION_NAME,
        dimension: int | None = None,
        distance: qmodels.Distance = DEFAULT_DISTANCE,
    ) -> str:
        """Create the collection if it does not exist; return its name.

        Idempotent: repeated calls are a no-op once the collection exists.
        Dimension defaults to the configured embedding model dimension
        (settings.openai.embedding_dimension, e.g. 1024).
        """
        dimension = dimension or settings.openai.embedding_dimension
        if not self._client.collection_exists(name):
            self._client.create_collection(
                collection_name=name,
                vectors_config=qmodels.VectorParams(size=dimension, distance=distance),
            )
        return name

    # -- points -------------------------------------------------------------

    def upsert_points(
        self,
        points: list[qmodels.PointStruct],
        collection: str = COLLECTION_NAME,
        wait: bool = True,
    ) -> None:
        """Insert or update points by id (deterministic ids → idempotent)."""
        self._client.upsert(collection_name=collection, points=points, wait=wait)

    def delete_by_filter(
        self,
        query_filter: qmodels.Filter,
        collection: str = COLLECTION_NAME,
    ) -> int:
        """Delete all points matching ``query_filter``; return deleted count.

        The count is measured **before** the delete (Qdrant's update result
        exposes operation ids, not row counts) — used by E4 reconciliation
        scripts and version rollback.
        """
        count = self._client.count(
            collection_name=collection,
            count_filter=query_filter,
            exact=True,
        ).count
        self._client.delete(
            collection_name=collection,
            points_selector=query_filter,
            wait=True,
        )
        return count

    def search(
        self,
        query_vector: list[float],
        query_filter: qmodels.Filter | None = None,
        top_k: int = 5,
        collection: str = COLLECTION_NAME,
        with_payload: bool = True,
    ) -> list[qmodels.ScoredPoint]:
        """Cosine top-k search; ``query_filter`` is AND-ed on every result.

        G2 (检索测试接口) enforces tenant + ``is_latest`` + ``is_deleted=false``
        filtering by passing a composed :class:`qmodels.Filter` here.

        Uses the ``query_points`` API (``client.search`` was removed in newer
        qdrant-client releases).
        """
        response = self._client.query_points(
            collection_name=collection,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=with_payload,
        )
        return response.points
