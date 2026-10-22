"""DOCX parser (D2 step 2) — python-docx.

Paragraphs become ``paragraph``/``heading`` blocks (Heading styles map to
``block_type="heading"``); tables are rendered as GitHub-flavoured markdown.
Body elements are walked in document order so headings/paragraphs/tables
interleave correctly.
"""

from __future__ import annotations

import io

from docx import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.parsers.base import BaseParser, Block, ParsedDocument
from app.parsers.registry import register


def _table_to_markdown(table: Table) -> str:
    """Render a docx table as a small GitHub-flavoured markdown table."""
    rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
    if not rows:
        return ""
    head, *body = rows
    lines = [
        "| " + " | ".join(head) + " |",
        "| " + " | ".join("---" for _ in head) + " |",
    ]
    lines.extend("| " + " | ".join(r) + " |" for r in body)
    return "\n".join(lines)


@register("docx")
class DocxParser(BaseParser):
    """Extract paragraphs and tables from .docx bytes."""

    def parse_bytes(self, data: bytes) -> ParsedDocument:
        document = DocxDocument(io.BytesIO(data))
        blocks: list[Block] = []
        texts: list[str] = []

        body = document.element.body
        for child in body.iterchildren():
            if child.tag == qn("w:p"):
                para = Paragraph(child, document)
                text = para.text.strip()
                if not text:
                    continue
                block_type = (
                    "heading"
                    if para.style is not None and para.style.name.startswith("Heading")
                    else "paragraph"
                )
                blocks.append(Block(text=text, block_type=block_type))
                texts.append(text)
            elif child.tag == qn("w:tbl"):
                markdown = _table_to_markdown(Table(child, document))
                if markdown:
                    blocks.append(Block(text=markdown, block_type="table"))
                    texts.append(markdown)

        core = document.core_properties
        metadata = {
            key: value
            for key, value in {
                "title": core.title,
                "author": core.author,
                "subject": core.subject,
            }.items()
            if value
        }
        return ParsedDocument(text="\n\n".join(texts), blocks=blocks, metadata=metadata)
