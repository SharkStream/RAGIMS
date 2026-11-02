"""Stats schemas (G3)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StatsResponse(BaseModel):
    total_documents: int = Field(description="documents of the tenant (excl. deleted)")
    total_chunks: int = Field(description="chunks across the tenant's documents")
    total_jobs: int = Field(description="ingestion jobs of the tenant")
    succeeded_jobs: int
    failed_jobs: int
    processed_today: int = Field(description="jobs created since 00:00 UTC today")
    success_rate: float | None = Field(
        description="succeeded / (succeeded + failed); None when no terminal job"
    )
