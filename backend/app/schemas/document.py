"""Document-related API schemas (C1 step 2, C2 query shapes)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    """Payload of ``POST /documents/upload`` (inside ApiResponse.data)."""

    doc_id: str = Field(description="documents.id (UUID string)")
    version: int = Field(description="document version number (starts at 1)")
    job_id: str = Field(description="ingestion_jobs.id (UUID string)")
    status: str = Field(description="document status right after upload")
    duplicate: bool = Field(
        default=False,
        description="True when an identical file (same name + content hash) "
        "was already uploaded — no new version/job was created.",
    )
    file_path: str = Field(
        description="MinIO object key: bucket/tenant/doc/version/file"
    )
    content_hash: str = Field(description="SHA-256 hex of the uploaded bytes")


# --------------------------------------------------------------------------- #
# C2 · query shapes
# --------------------------------------------------------------------------- #


class DocumentOut(BaseModel):
    """List row of ``GET /documents``."""

    id: str
    title: str | None = None
    file_name: str
    file_type: str
    status: str
    current_version: int
    datasource_id: str
    created_at: datetime
    updated_at: datetime


class DocumentVersionOut(BaseModel):
    """Version row (``is_latest=true`` for the detail endpoint)."""

    id: str
    version: int
    content_hash: str
    file_path: str
    file_size: int
    parse_status: str
    chunk_count: int
    is_latest: bool
    created_at: datetime


class DocumentDetail(DocumentOut):
    """``GET /documents/{id}`` — document + its latest version."""

    latest_version: DocumentVersionOut | None = None


class ChunkOut(BaseModel):
    """Chunk row of ``GET /documents/{id}/chunks`` (ordered by chunk_index)."""

    chunk_index: int
    text: str
    token_count: int
    page: int | None = None
    section: str | None = None


class DocumentDeleteResponse(BaseModel):
    """Payload of ``DELETE /documents/{id}`` (MVP soft delete)."""

    doc_id: str
    status: str = "deleted"
