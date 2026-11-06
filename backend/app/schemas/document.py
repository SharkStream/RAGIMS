"""Document-related API schemas (C1 step 2, C2 query shapes)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    access_level: str = "internal"
    tags: list[str] | None = None
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
    embedding_model: str | None = None
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


class DocumentVersionDeleteResponse(BaseModel):
    """Payload of ``DELETE /documents/{id}/versions/{version}`` (J4 reclaim)."""

    doc_id: str
    version: int
    status: str = "deleted"


class DocumentPatchRequest(BaseModel):
    """``PATCH /documents/{id}`` body (J3) — metadata only, all fields optional.

    At least one field must be sent; ``null`` values are skipped (no clearing
    of ``title``). ``tags`` replaces the whole list; unknown fields are 422.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=512)
    tags: list[str] | None = Field(
        default=None,
        description="Whole-list replacement of the document tags",
    )
    access_level: Literal["internal", "confidential", "public"] | None = None
    datasource_id: str | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> DocumentPatchRequest:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


# --------------------------------------------------------------------------- #
# L2 · document quality checks
# --------------------------------------------------------------------------- #


class QualityCheckOut(BaseModel):
    """One quality-check row for the dashboard (score: risk, lower is better)."""

    version: int
    doc_version_id: str
    check_type: str
    score: float
    detail: dict[str, object] | None = None
    created_at: datetime | None = None


# --------------------------------------------------------------------------- #
# F3 · reprocess + cancel
# --------------------------------------------------------------------------- #


class JobCancelResponse(BaseModel):
    """Payload of ``POST /documents/{id}/jobs/{job_id}/cancel``."""

    job_id: str = Field(description="ingestion_jobs.id (UUID string)")
    status: str = Field(description="new job status (always 'cancelled' on success)")
