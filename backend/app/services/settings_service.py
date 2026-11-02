"""Effective settings service (H5): read-only view for the settings page."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.embedding_model import EmbeddingModel
from app.schemas.settings import ChunkingOut, EffectiveSettings


def get_effective_settings(db: Session) -> EffectiveSettings:
    """Default embedding model row + active chunking config (read-only)."""
    model = db.scalars(
        select(EmbeddingModel).where(EmbeddingModel.is_default.is_(True))
    ).first()
    return EffectiveSettings(
        embedding_model=model,
        chunking=ChunkingOut(
            chunk_size=settings.app.chunk_size,
            chunk_overlap=settings.app.chunk_overlap,
        ),
    )
