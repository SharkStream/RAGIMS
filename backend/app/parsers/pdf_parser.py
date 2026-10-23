"""PDF parser (D2 step 1) — PyMuPDF (fitz).

One :class:`Block` per non-empty page (accurate ``page`` numbers, 1-based);
file-level metadata (title/author/...) goes into ``ParsedDocument.metadata``
with empty values dropped.
"""

from __future__ import annotations

import pymupdf  # PyMuPDF (the modern import name; `fitz` is deprecated)

from app.parsers.base import BaseParser, Block, ParsedDocument
from app.parsers.registry import register


@register("pdf")
class PdfParser(BaseParser):
    """Extract text page-by-page from PDF files."""

    def parse_bytes(self, data: bytes) -> ParsedDocument:
        doc = pymupdf.open(stream=data, filetype="pdf")
        try:
            if doc.needs_pass and doc.authenticate("") == 0:
                raise ValueError(
                    "PDF is password-protected: cannot extract text without "
                    "credentials (D5 edge case)"
                )
            blocks: list[Block] = []
            texts: list[str] = []
            for page_no in range(doc.page_count):
                page = doc.load_page(page_no)
                page_text = page.get_text("text").strip()
                if not page_text:
                    continue
                blocks.append(Block(text=page_text, page=page_no + 1))
                texts.append(page_text)

            metadata = {
                key: value for key, value in (doc.metadata or {}).items() if value
            }
            return ParsedDocument(
                text="\n\n".join(texts), blocks=blocks, metadata=metadata
            )
        finally:
            doc.close()
