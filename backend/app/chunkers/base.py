"""Chunk model, config and chunker interface (D4 step 1, 3)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.parsers.base import ParsedDocument


@dataclass(slots=True)
class Chunk:
    """One retrieval unit (maps to the ``chunks`` table, D4 step 1)."""

    chunk_index: int
    text: str
    token_count: int
    page: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_hash: str = ""


@dataclass(slots=True, frozen=True)
class ChunkerConfig:
    """Split parameters; defaults come from ``Settings`` (D4 step 3).

    MVP keeps no ``chunking_strategies`` table — the config is constructed
    from settings, but stage F may pass an explicit one per document.
    """

    chunk_size: int = settings.app.chunk_size
    overlap: int = settings.app.chunk_overlap
    encoding_name: str = "cl100k_base"  # offline-cached tiktoken BPE

    def __post_init__(self) -> None:
        if self.chunk_size <= 0 or self.overlap < 0 or self.overlap >= self.chunk_size:
            raise ValueError(
                f"invalid chunker config: chunk_size={self.chunk_size}, "
                f"overlap={self.overlap} (need 0 <= overlap < chunk_size)"
            )


#: The MVP default used by the pipeline when no explicit config is given.
DEFAULT_CHUNKER_CONFIG = ChunkerConfig()


class BaseChunker(ABC):
    """Interface every chunker implements (D4 step 1)."""

    @abstractmethod
    def chunk(
        self, parsed: ParsedDocument, config: ChunkerConfig | None = None
    ) -> list[Chunk]:
        """Split ``parsed`` into chunks; never mutates ``parsed``."""
