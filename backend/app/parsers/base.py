"""Parser abstraction (D1 step 1-2): result model, ABC, supported types.

Concrete parsers live in ``app/parsers/*_parser.py`` (stage D2) and self-
register with :func:`app.parsers.registry.register`.

Design notes:

* ``ParsedDocument`` is the single currency between parsing (D2), cleaning
  (D3) and chunking (D4): ``text`` is the concatenated view, ``blocks`` keeps
  the structural granularity (page numbers survive into chunks), ``metadata``
  carries file-level facts (title, author, ...).
* Parsers must be side-effect-free: they only read ``file_path`` and return
  the in-memory result; persistence (parsed-text bucket, status writes) is
  the pipeline's job (D2 step 4-5).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: File types the ingestion pipeline can parse (B1 ``documents.file_type``).
SUPPORTED_TYPES = {"pdf", "docx", "txt"}


class UnsupportedFileType(Exception):
    """Raised when no parser is registered for a file type."""

    def __init__(self, file_type: str, supported: set[str] | None = None) -> None:
        self.file_type = file_type
        self.supported = supported if supported is not None else set(SUPPORTED_TYPES)
        super().__init__(
            f"unsupported file type: {file_type!r} "
            f"(supported: {', '.join(sorted(self.supported))})"
        )


@dataclass(slots=True)
class Block:
    """One structural unit of a parsed document (D1 step 1)."""

    text: str
    page: int | None = None
    block_type: str = "paragraph"  # paragraph | heading | table | ...


@dataclass(slots=True)
class ParsedDocument:
    """Uniform parse result (D1 step 1)."""

    text: str
    blocks: list[Block] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseParser(ABC):
    """Interface every concrete parser implements (D1 step 2)."""

    @abstractmethod
    def parse(self, file_path: str | Path) -> ParsedDocument:
        """Read the file at ``file_path`` and return a :class:`ParsedDocument`.

        Implementations must be side-effect-free; raise a plain exception on
        failure — the pipeline (D2 step 5) maps failures to
        ``parse_status=failed``.
        """
