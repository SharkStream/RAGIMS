"""Parser package — importing it registers all concrete parsers.

Concrete parsers self-register via ``@register(file_type)``; the imports below
make that registration happen on ``import app.parsers`` so callers (pipeline
services, probes, tests) never need to know the module list. Keep this list in
sync with :data:`app.parsers.base.SUPPORTED_TYPES`.
"""

from __future__ import annotations

from app.parsers.base import (
    SUPPORTED_TYPES,
    BaseParser,
    Block,
    ParsedDocument,
    UnsupportedFileType,
)

# Import for the side effect of self-registration (order is irrelevant).
from app.parsers.docx_parser import DocxParser
from app.parsers.pdf_parser import PdfParser
from app.parsers.registry import get_parser, register, registered_types
from app.parsers.txt_parser import TxtParser

__all__ = [
    "SUPPORTED_TYPES",
    "BaseParser",
    "Block",
    "DocxParser",
    "ParsedDocument",
    "PdfParser",
    "TxtParser",
    "UnsupportedFileType",
    "get_parser",
    "register",
    "registered_types",
]
