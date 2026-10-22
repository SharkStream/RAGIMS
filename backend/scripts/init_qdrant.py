"""One-off Qdrant collection initialization.

Creates the ``documents`` collection (dimension from the default embedding
model, COSINE distance) without starting the API.

Usage::

    python scripts/init_qdrant.py

Requires a configured environment (OPENAI__API_KEY, QDRANT__*) — see
``backend/.env.example``.
"""

from __future__ import annotations

from app.clients.qdrant_client import QdrantVectorStore
from app.core.config import settings
from app.core.logging import setup_logging

setup_logging(level=settings.app.log_level)


def main() -> None:
    name = QdrantVectorStore().ensure_collection()
    print(
        f"Qdrant collection '{name}' ready "
        f"(dimension={settings.openai.embedding_dimension}, distance=COSINE)"
    )


if __name__ == "__main__":
    main()
