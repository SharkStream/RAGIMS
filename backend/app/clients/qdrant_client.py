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
        *,
        with_sparse: bool = False,
    ) -> str:
        """Create the collection if it does not exist; return its name.

        Idempotent: repeated calls are a no-op once the collection exists —
        an existing single-dense collection is left as-is (use
        ``scripts/migrate_hybrid.py`` to upgrade it to multi-vector).

        ``with_sparse=True`` (N2) creates a **multi-vector** collection: a
        named dense vector plus a named ``sparse`` vector index for hybrid
        (RRF) retrieval. Dimension defaults to the configured embedding
        model dimension (settings.openai.embedding_dimension, e.g. 1024).
        """
        dimension = dimension or settings.openai.embedding_dimension
        dense_params = qmodels.VectorParams(size=dimension, distance=distance)
        if not self._client.collection_exists(name):
            if with_sparse:
                self._client.create_collection(
                    collection_name=name,
                    vectors_config={"dense": dense_params},
                    sparse_vectors_config={"sparse": qmodels.SparseVectorParams()},
                )
            else:
                self._client.create_collection(
                    collection_name=name,
                    vectors_config=dense_params,
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

    def set_payload_by_filter(
        self,
        payload: dict,
        query_filter: qmodels.Filter,
        collection: str = COLLECTION_NAME,
    ) -> None:
        """Overwrite payload keys on every point matching ``query_filter`` (J4).

        Used by version activation to flip ``is_latest`` without touching
        vectors: two calls (demote current latest, promote target version).
        Not atomic across calls — the caller orders demote-before-promote so
        the two versions never both match ``is_latest=true``.
        """
        self._client.set_payload(
            collection_name=collection,
            payload=payload,
            points=query_filter,
            wait=True,
        )

    def scroll_points(
        self,
        query_filter: qmodels.Filter,
        collection: str = COLLECTION_NAME,
        limit: int = 1000,
        with_payload: bool = True,
    ) -> list[qmodels.Record]:
        """List points matching ``query_filter`` (reconcile scans, J4)."""
        points, _offset = self._client.scroll(
            collection_name=collection,
            scroll_filter=query_filter,
            limit=limit,
            with_payload=with_payload,
            with_vectors=False,
        )
        return list(points)

    def search(
        self,
        query_vector: list[float],
        query_filter: qmodels.Filter | None = None,
        top_k: int = 5,
        collection: str = COLLECTION_NAME,
        with_payload: bool = True,
        sparse_vector: qmodels.SparseVector | None = None,
    ) -> list[qmodels.ScoredPoint]:
        """Cosine top-k search; ``query_filter`` is AND-ed on every result.

        G2 (检索测试接口) enforces tenant + ``is_latest`` + ``is_deleted=false``
        filtering by passing a composed :class:`qmodels.Filter` here.

        ``sparse_vector`` given (N2 hybrid): runs a **two-prefetch RRF fusion**
        query — dense and lexical candidates are fetched separately and fused
        by reciprocal rank, still under the same mandatory filter.

        Uses the ``query_points`` API (``client.search`` was removed in newer
        qdrant-client releases).
        """
        if sparse_vector is not None:
            response = self._client.query_points(
                collection_name=collection,
                prefetch=[
                    qmodels.Prefetch(
                        query=query_vector,
                        using="dense",
                        limit=top_k * 2,
                        filter=query_filter,
                    ),
                    qmodels.Prefetch(
                        query=sparse_vector,
                        using="sparse",
                        limit=top_k * 2,
                        filter=query_filter,
                    ),
                ],
                query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
                limit=top_k,
                with_payload=with_payload,
            )
            return response.points
        try:
            # Multi-vector collections (N2 migration) need the vector name.
            response = self._client.query_points(
                collection_name=collection,
                query=query_vector,
                using="dense",
                query_filter=query_filter,
                limit=top_k,
                with_payload=with_payload,
            )
        except Exception:  # noqa: BLE001 — legacy single-vector collection
            # fallback: unnamed dense query (pre-N2 collection shape)
            response = self._client.query_points(
                collection_name=collection,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=with_payload,
            )
        return response.points
