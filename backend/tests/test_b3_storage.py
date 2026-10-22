"""B3 storage-layer acceptance tests (offline — fakes only, no services).

Covers:

* MinIO wrapper round-trips (bytes / file path), presigned URLs, deletes,
  idempotent bucket creation.
* Qdrant wrapper idempotent ``ensure_collection``, deterministic point ids,
  upsert / delete-by-filter (pre-delete count) / search pass-through.
* ``StorageService`` semantics: raw-doc object-key convention and delegation.
* Protocol conformance (fakes satisfy ``ObjectStore`` / ``VectorStore``).

Live end-to-end checks against the configured MinIO/Qdrant run in the B3
runbook script (see ``docs/tasks/b3-storage-layer.md``).

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_b3_storage.py -v -p no:cacheprovider
"""

from __future__ import annotations

import io
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from app.clients.minio_client import DEFAULT_PRESIGN_EXPIRES, MinioObjectStore
from app.clients.qdrant_client import QdrantVectorStore, chunk_point_id
from app.services.storage import ObjectStore, StorageService, VectorStore, get_storage
from qdrant_client.http import models as qmodels

# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class FakeMinio:
    """In-memory stand-in for ``minio.Minio`` with call recording."""

    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], bytes] = {}
        self.calls: list[tuple[str, tuple, dict]] = []

    def _record(self, name: str, args: tuple, kwargs: dict) -> None:
        self.calls.append((name, args, kwargs))

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self.buckets

    def make_bucket(self, bucket: str) -> None:
        self._record("make_bucket", (bucket,), {})
        self.buckets.add(bucket)

    def put_object(self, bucket: str, object_name: str, data: io.IOBase, length: int):
        self._record("put_object", (bucket, object_name), {"length": length})
        self.objects[(bucket, object_name)] = data.read()
        return SimpleNamespace(etag="fake")

    def get_object(self, bucket: str, object_name: str):
        self._record("get_object", (bucket, object_name), {})

        class FakeResponse(io.BytesIO):
            def release_conn(self) -> None: ...

        payload = self.objects.get((bucket, object_name))
        if payload is None:
            raise KeyError((bucket, object_name))
        return FakeResponse(payload)

    def presigned_get_object(
        self, bucket: str, object_name: str, expires: timedelta | None = None
    ) -> str:
        self._record(
            "presigned_get_object", (bucket, object_name), {"expires": expires}
        )
        return f"https://fake-minio/{bucket}/{object_name}?exp={expires}"

    def remove_object(self, bucket: str, object_name: str) -> None:
        self._record("remove_object", (bucket, object_name), {})
        self.objects.pop((bucket, object_name), None)

    def stat_object(self, bucket: str, object_name: str):
        if (bucket, object_name) not in self.objects:
            raise FileNotFoundError((bucket, object_name))
        return SimpleNamespace(object_name=object_name)


class FakeQdrant:
    """In-memory stand-in for ``QdrantClient`` with call recording."""

    def __init__(self) -> None:
        self.collections: dict[str, qmodels.VectorParams] = {}
        self.points: dict[str, dict[str, qmodels.PointStruct]] = {}
        self.calls: list[tuple[str, tuple, dict]] = []
        self.search_results: list = []

    def _record(self, name: str, args: tuple, kwargs: dict) -> None:
        self.calls.append((name, args, kwargs))

    def collection_exists(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def create_collection(
        self, collection_name: str, vectors_config: qmodels.VectorParams
    ) -> None:
        self._record("create_collection", (collection_name,), {})
        self.collections[collection_name] = vectors_config

    def upsert(
        self,
        collection_name: str,
        points: list,
        wait: bool = True,
    ):
        self._record("upsert", (collection_name, points), {"wait": wait})
        bucket = self.points.setdefault(collection_name, {})
        for p in points:
            bucket[p.id] = p
        return SimpleNamespace(operation_id=0, status="completed")

    def count(
        self,
        collection_name: str,
        count_filter: qmodels.Filter | None = None,
        exact: bool = False,
    ):
        self._record("count", (collection_name,), {"filter": count_filter})
        total = len(self.points.get(collection_name, {}))
        return SimpleNamespace(count=total)

    def delete(
        self,
        collection_name: str,
        points_selector: object,
        wait: bool = True,
    ):
        self._record("delete", (collection_name, points_selector), {"wait": wait})
        # Fakes only use Filter selectors with a single must condition value.
        self.points[collection_name] = {}
        return SimpleNamespace(operation_id=1, status="completed")

    def query_points(
        self,
        collection_name: str,
        query: list[float],
        query_filter: qmodels.Filter | None = None,
        limit: int = 5,
        with_payload: bool = True,
    ):
        self._record(
            "query_points",
            (collection_name, query),
            {
                "query_filter": query_filter,
                "limit": limit,
                "with_payload": with_payload,
            },
        )
        return SimpleNamespace(points=self.search_results)


# --------------------------------------------------------------------------- #
# MinIO wrapper
# --------------------------------------------------------------------------- #


def _minio_store() -> tuple[MinioObjectStore, FakeMinio]:
    fake = FakeMinio()
    return MinioObjectStore(client=fake), fake  # type: ignore[arg-type]


def test_minio_roundtrip_bytes() -> None:
    store, fake = _minio_store()
    store.upload_file("raw-docs", "a/b/c.pdf", b"%PDF-fake")
    assert fake.objects[("raw-docs", "a/b/c.pdf")] == b"%PDF-fake"
    assert store.download_file("raw-docs", "a/b/c.pdf") == b"%PDF-fake"


def test_upload_accepts_local_path(tmp_path=None) -> None:
    store, fake = _minio_store()
    # Use a file that already exists in the workspace (sandbox-safe).
    src = Path(__file__)
    store.upload_file("raw-docs", "t/d/1/test_b3.py", src)
    assert fake.objects[("raw-docs", "t/d/1/test_b3.py")] == src.read_bytes()


def test_minio_presigned_url_records_expiry() -> None:
    store, fake = _minio_store()
    url = store.generate_presigned_url("raw-docs", "t/d/1/f.pdf")
    assert url.startswith("https://fake-minio/raw-docs/t/d/1/f.pdf")
    assert fake.calls[-1][2]["expires"] is DEFAULT_PRESIGN_EXPIRES  # 1h default

    custom = timedelta(minutes=10)
    store.generate_presigned_url("raw-docs", "t/d/1/f.pdf", expires=custom)
    assert fake.calls[-1][2]["expires"] is custom


def test_minio_delete_object_removes() -> None:
    store, fake = _minio_store()
    store.upload_file("raw-docs", "k", b"x")
    store.delete_object("raw-docs", "k")
    assert ("raw-docs", "k") not in fake.objects


def test_minio_ensure_bucket_idempotent() -> None:
    store, fake = _minio_store()
    fake.buckets.add("raw-docs")  # already exists
    store.ensure_bucket("raw-docs")
    assert not any(name == "make_bucket" for name, _, _ in fake.calls)

    store.ensure_bucket("parsed-text")
    assert ("make_bucket", ("parsed-text",), {}) in fake.calls


def test_minio_object_exists() -> None:
    store, fake = _minio_store()
    store.upload_file("raw-docs", "k", b"x")
    assert store.object_exists("raw-docs", "k") is True
    assert store.object_exists("raw-docs", "missing") is False


# --------------------------------------------------------------------------- #
# Qdrant wrapper
# --------------------------------------------------------------------------- #


def _qdrant_store(exists: bool = False) -> tuple[QdrantVectorStore, FakeQdrant]:
    fake = FakeQdrant()
    if exists:
        fake.collections["documents"] = qmodels.VectorParams(
            size=1024, distance=qmodels.Distance.COSINE
        )
    return QdrantVectorStore(client=fake), fake  # type: ignore[arg-type]


def test_ensure_collection_idempotent_when_exists() -> None:
    store, fake = _qdrant_store(exists=True)
    assert store.ensure_collection() == "documents"
    assert not any(name == "create_collection" for name, _, _ in fake.calls)


def test_ensure_collection_creates_with_settings_dimension_and_cosine() -> None:
    from app.core.config import settings

    store, fake = _qdrant_store(exists=False)
    store.ensure_collection()
    params = fake.collections["documents"]
    assert params.size == settings.openai.embedding_dimension
    assert params.distance is qmodels.Distance.COSINE


def test_chunk_point_id_is_deterministic_uuid5() -> None:
    v1, v2 = (
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    )
    assert chunk_point_id(v1, 0) == chunk_point_id(v1, 0)
    assert chunk_point_id(v1, 0) != chunk_point_id(v1, 1)
    assert chunk_point_id(v1, 0) != chunk_point_id(v2, 0)
    value = chunk_point_id(v1, 7)
    assert len(value) == 36 and value.count("-") == 4


def test_upsert_points_passes_wait_default() -> None:
    store, fake = _qdrant_store()
    point = qmodels.PointStruct(
        id=chunk_point_id("d", 0), vector=[0.1, 0.2], payload={}
    )
    store.upsert_points([point])
    name, args, kwargs = fake.calls[-1]
    assert name == "upsert" and kwargs["wait"] is True and len(args[1]) == 1


def test_delete_by_filter_returns_pre_delete_count() -> None:
    store, fake = _qdrant_store()
    fake.points["documents"] = {str(i): None for i in range(7)}
    flt = qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="doc_version_id", match=qmodels.MatchValue(value="d1")
            )
        ]
    )
    deleted = store.delete_by_filter(flt)
    assert deleted == 7
    delete_calls = [c for c in fake.calls if c[0] == "delete"]
    assert len(delete_calls) == 1
    assert delete_calls[0][1][1] is flt  # points_selector is the filter


def test_search_forwards_top_k_and_filter() -> None:
    store, fake = _qdrant_store()
    flt = qmodels.Filter(must=[])
    store.search([0.1, 0.2], query_filter=flt, top_k=3)
    _, args, kwargs = fake.calls[-1]
    assert args[0] == "documents"
    assert kwargs["limit"] == 3 and kwargs["query_filter"] is flt


# --------------------------------------------------------------------------- #
# StorageService
# --------------------------------------------------------------------------- #


class RecordingObjectStore:
    """Minimal ObjectStore fake recording semantic calls."""

    def __init__(self) -> None:
        self.uploads: list[tuple[str, str, object]] = []
        self.deleted: list[tuple[str, str]] = []
        self.objects: dict[tuple[str, str], bytes] = {}

    def ensure_bucket(self, bucket: str) -> None: ...

    def upload_file(self, bucket, object_name, data_or_path) -> None:
        self.uploads.append((bucket, object_name, data_or_path))
        self.objects[(bucket, object_name)] = bytes(data_or_path)

    def download_file(self, bucket: str, object_name: str) -> bytes:
        return self.objects[(bucket, object_name)]

    def generate_presigned_url(self, bucket, object_name, expires=None) -> str:
        return f"https://fake/{bucket}/{object_name}"

    def delete_object(self, bucket: str, object_name: str) -> None:
        self.deleted.append((bucket, object_name))
        self.objects.pop((bucket, object_name), None)

    def object_exists(self, bucket: str, object_name: str) -> bool:
        return (bucket, object_name) in self.objects


class RecordingVectorStore:
    def __init__(self) -> None:
        self.upserts: list[tuple] = []
        self.deleted_filters: list = []
        self.searches: list[dict] = []

    def ensure_collection(self, name="documents", dimension=None, distance=None):
        return name

    def upsert_points(self, points, collection="documents", wait=True):
        self.upserts.append((points, collection, wait))

    def delete_by_filter(self, query_filter, collection="documents"):
        self.deleted_filters.append(query_filter)
        return 3

    def search(
        self,
        query_vector,
        query_filter=None,
        top_k=5,
        collection="documents",
        with_payload=True,
    ):
        self.searches.append({"vector": query_vector, "top_k": top_k})
        return []


TENANT, DOC, VER = "t-1", "d-1", 1


def _service() -> tuple[StorageService, RecordingObjectStore, RecordingVectorStore]:
    objs, vecs = RecordingObjectStore(), RecordingVectorStore()
    return StorageService(objects=objs, vectors=vecs), objs, vecs  # type: ignore[arg-type]


def test_raw_object_key_follows_c1_convention() -> None:
    key = StorageService.raw_object_key(TENANT, DOC, VER, "report.pdf")
    assert key == f"raw-docs/{TENANT}/{DOC}/{VER}/report.pdf"


def test_storage_store_read_delete_roundtrip() -> None:
    svc, objs, _ = _service()
    key = svc.store_raw_document(TENANT, DOC, VER, "f.pdf", b"data")
    assert key == f"raw-docs/{TENANT}/{DOC}/{VER}/f.pdf"
    assert objs.uploads == [("raw-docs", f"{TENANT}/{DOC}/{VER}/f.pdf", b"data")]
    assert svc.read_raw_document(key) == b"data"
    assert svc.raw_presigned_url(key).startswith("https://fake/raw-docs/")
    svc.delete_raw_document(key)
    assert objs.deleted == [("raw-docs", f"{TENANT}/{DOC}/{VER}/f.pdf")]


def test_storage_delegates_vector_calls() -> None:
    svc, _, vecs = _service()
    assert svc.ensure_vector_collection() == "documents"
    point = qmodels.PointStruct(id="p", vector=[0.1], payload={"k": "v"})
    svc.upsert_points([point])
    assert vecs.upserts[0][0] == [point] and vecs.upserts[0][1] == "documents"
    flt = qmodels.Filter(must=[])
    assert svc.delete_points_by_filter(flt) == 3
    assert vecs.deleted_filters == [flt]
    svc.search_vectors([0.5], top_k=2)
    assert vecs.searches == [{"vector": [0.5], "top_k": 2}]


def test_default_storage_lazy_singleton() -> None:
    assert get_storage() is get_storage()
    assert isinstance(get_storage(), StorageService)


# --------------------------------------------------------------------------- #
# Protocol conformance (structural typing)
# --------------------------------------------------------------------------- #


def test_concrete_stores_satisfy_protocols() -> None:
    assert isinstance(MinioObjectStore(client=FakeMinio()), ObjectStore)  # type: ignore[arg-type]
    assert isinstance(QdrantVectorStore(client=FakeQdrant()), VectorStore)  # type: ignore[arg-type]
