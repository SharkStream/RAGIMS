"""Qdrant client wrapper.

Exposes a single idempotent ``ensure_collection()`` used by the ingestion
pipeline (reused in B3) and by ``scripts/init_qdrant.py`` for one-off setup.
"""

from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings

COLLECTION_NAME = "documents"


def build_client() -> QdrantClient:
    """Create a QdrantClient from settings (REST transport)."""
    if settings.qdrant.api_key:
        return QdrantClient(url=settings.qdrant.url, api_key=settings.qdrant.api_key)
    return QdrantClient(host=settings.qdrant.host, port=settings.qdrant.port)


def ensure_collection(
    client: QdrantClient | None = None,
    *,
    name: str = COLLECTION_NAME,
    dimension: int | None = None,
) -> str:
    """Create the collection if it does not exist; return its name.

    Dimension defaults to the configured embedding model dimension
    (OpenAI ``text-embedding-3-small`` -> 1536) with COSINE distance.
    Idempotent: repeated calls are a no-op once the collection exists.
    """
    dimension = dimension or settings.openai.embedding_dimension
    client = client or build_client()

    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=qmodels.VectorParams(
                size=dimension,
                distance=qmodels.Distance.COSINE,
            ),
        )
    return name
