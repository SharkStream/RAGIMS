"""Read-only effective settings (H5): default embedding model + chunking."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class EmbeddingModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    provider: str
    model_name: str
    dimension: int
    is_default: bool


class ChunkingOut(BaseModel):
    chunk_size: int
    chunk_overlap: int


class EffectiveSettings(BaseModel):
    embedding_model: EmbeddingModelOut | None
    chunking: ChunkingOut
