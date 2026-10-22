"""Deprecated compatibility shim — implementation moved to :mod:`app.clients.qdrant_client`.

B3 renamed the module to ``qdrant_client.py`` and grew the full vector-store
facade. This shim keeps any external import path alive; prefer importing from
``app.clients.qdrant_client`` in new code.
"""

from __future__ import annotations

from app.clients.qdrant_client import (
    COLLECTION_NAME as COLLECTION_NAME,
)
from app.clients.qdrant_client import (
    QdrantVectorStore as QdrantVectorStore,
)
from app.clients.qdrant_client import (
    build_client as build_client,
)
from app.clients.qdrant_client import (
    chunk_point_id as chunk_point_id,
)

__all__ = ["COLLECTION_NAME", "QdrantVectorStore", "build_client", "chunk_point_id"]


def ensure_collection(
    client: QdrantVectorStore | None = None,
    *,
    name: str = COLLECTION_NAME,
    dimension: int | None = None,
) -> str:
    """Backwards-compatible module-level wrapper (A2 signature)."""
    store = client or QdrantVectorStore()
    return store.ensure_collection(name, dimension)
