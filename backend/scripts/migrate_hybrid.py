"""Migrate the dense-only Qdrant collection to multi-vector (N2 hybrid).

Old collection: unnamed dense vector ``[f1..fn]``.
New collection: named ``dense`` + named ``sparse`` (lexical) vectors.

**Zero embedding cost**: every existing point's dense vector is read back from
Qdrant (``with_vectors=True``), the sparse vector is recomputed from the
point's stored ``text`` payload, and both are re-upserted with the payload
untouched. Deterministic point ids keep the mapping identical.

Usage (from ``backend/``)::

    env/Scripts/python.exe scripts/migrate_hybrid.py --dry-run   # count only
    env/Scripts/python.exe scripts/migrate_hybrid.py             # migrate
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clients.qdrant_client import COLLECTION_NAME, build_client  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.services.sparse_service import sparse_vector  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.http import models as qmodels  # noqa: E402

setup_logging(level=settings.app.log_level)

TMP_SUFFIX = "__hybrid_tmp"


def _is_multi_vector(client: QdrantClient, name: str) -> bool:
    info = client.get_collection(name)
    vectors = info.config.params.vectors
    # single unnamed vector → VectorParams; named → dict
    return isinstance(vectors, dict)


def _scroll_all(client: QdrantClient, name: str) -> list[qmodels.Record]:
    records: list[qmodels.Record] = []
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=name,
            limit=256,
            with_payload=True,
            with_vectors=True,
            offset=offset,
        )
        records.extend(batch)
        if offset is None:
            break
    return records


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate Qdrant collection to multi-vector."
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    client = build_client(timeout=60)
    name = COLLECTION_NAME

    if not client.collection_exists(name):
        print(f"collection '{name}' does not exist — nothing to migrate")
        return 0
    if _is_multi_vector(client, name):
        print(f"collection '{name}' already multi-vector — nothing to do")
        return 0

    records = _scroll_all(client, name)
    print(f"points to migrate: {len(records)}")
    if args.dry_run or not records:
        print("[dry-run] no changes")
        return 0

    dimension = settings.openai.embedding_dimension
    tmp = name + TMP_SUFFIX
    if client.collection_exists(tmp):
        client.delete_collection(tmp)
    dense_params = qmodels.VectorParams(
        size=dimension, distance=qmodels.Distance.COSINE
    )
    client.create_collection(
        collection_name=tmp,
        vectors_config={"dense": dense_params},
        sparse_vectors_config={"sparse": qmodels.SparseVectorParams()},
    )

    migrated = 0
    skipped = 0
    batch: list[qmodels.PointStruct] = []
    for rec in records:
        dense = rec.vector
        if isinstance(dense, dict):  # already named somehow — keep dense part
            dense = dense.get("dense")
        payload = rec.payload or {}
        text = str(payload.get("text") or "")
        if dense is None or not text:
            skipped += 1
            continue
        batch.append(
            qmodels.PointStruct(
                id=rec.id,
                vector={
                    "dense": list(dense),
                    "sparse": sparse_vector(text, dim=settings.retrieval.sparse_dim),
                },
                payload=payload,
            )
        )
        if len(batch) >= 128:
            client.upsert(collection_name=tmp, points=batch, wait=True)
            migrated += len(batch)
            batch = []
    if batch:
        client.upsert(collection_name=tmp, points=batch, wait=True)
        migrated += len(batch)

    # swap: drop old collection, recreate canonical (multi-vector), copy tmp
    # points over (Qdrant has no rename). tmp is dropped afterwards.
    print(f"swapping '{name}' → recreating multi-vector and copying '{tmp}'")
    client.delete_collection(name)
    client.create_collection(
        collection_name=name,
        vectors_config={"dense": dense_params},
        sparse_vectors_config={"sparse": qmodels.SparseVectorParams()},
    )
    batch = []
    for rec in _scroll_all(client, tmp):
        batch.append(
            qmodels.PointStruct(id=rec.id, vector=rec.vector, payload=rec.payload or {})
        )
        if len(batch) >= 128:
            client.upsert(collection_name=name, points=batch, wait=True)
            batch = []
    if batch:
        client.upsert(collection_name=name, points=batch, wait=True)
    client.delete_collection(tmp)
    print(f"MIGRATION DONE ✓ — collection '{name}' is multi-vector (dense+sparse)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
