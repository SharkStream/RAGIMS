"""MinIO object-store wrapper (S3-compatible).

Thin, injectable wrapper over :class:`minio.Minio` exposing the four object
operations the pipeline needs (B3 step 1). The raw :class:`Minio` client can
be injected for tests (``MinioObjectStore(client=FakeMinio())``); by default
it is built from ``settings.minio``.

Errors are deliberately NOT wrapped: ``minio.error.S3Error`` (missing bucket,
missing object, ...) propagates so callers (C1 upload transaction, D2 parsers)
can react with their own error codes.
"""

from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from pathlib import Path

from minio import Minio

from app.core.config import settings

#: Default presigned-URL validity (H2 preview links, C1 responses).
DEFAULT_PRESIGN_EXPIRES = timedelta(hours=1)

#: Max bytes read from a local file path in one go (64 MiB chunks).
_CHUNK = 64 * 1024 * 1024


class MinioObjectStore:
    """Object storage facade used by :class:`~app.services.storage.StorageService`."""

    def __init__(self, client: Minio | None = None) -> None:
        self._client = client or Minio(
            settings.minio.endpoint,
            access_key=settings.minio.access_key,
            secret_key=settings.minio.secret_key,
            secure=settings.minio.secure,
        )

    # -- buckets ------------------------------------------------------------

    def ensure_bucket(self, bucket: str) -> None:
        """Create the bucket if missing; idempotent (A2 init.sh fallback)."""
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)

    # -- objects ------------------------------------------------------------

    def upload_file(
        self,
        bucket: str,
        object_name: str,
        data_or_path: bytes | bytearray | str | Path,
    ) -> None:
        """Upload ``data_or_path`` (raw bytes or a local file path)."""
        if isinstance(data_or_path, (str, Path)):
            payload = Path(data_or_path).read_bytes()
        else:
            payload = bytes(data_or_path)
        self._client.put_object(
            bucket,
            object_name,
            BytesIO(payload),
            length=len(payload),
        )

    def download_file(self, bucket: str, object_name: str) -> bytes:
        """Return the object's bytes."""
        response = self._client.get_object(bucket, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def generate_presigned_url(
        self,
        bucket: str,
        object_name: str,
        expires: timedelta = DEFAULT_PRESIGN_EXPIRES,
    ) -> str:
        """Return a time-limited GET URL that directly serves the object."""
        return self._client.presigned_get_object(bucket, object_name, expires=expires)

    def delete_object(self, bucket: str, object_name: str) -> None:
        """Delete the object; deleting a missing object is a no-op in S3."""
        self._client.remove_object(bucket, object_name)

    def object_exists(self, bucket: str, object_name: str) -> bool:
        """True when the object exists (used by tests / re-upload checks)."""
        try:
            self._client.stat_object(bucket, object_name)
        except Exception:  # noqa: BLE001 — minio raises S3Error variants here
            return False
        return True
