"""Markdown parser — line-structured plain text.

Markdown is text with lightweight structure, so the parser keeps the raw
syntax in ``text`` (heading markers and fences are semantic signals worth
embedding) while ``blocks`` records the granularity: ATX headings become
``heading`` blocks, fenced code spans become ``code`` blocks, blank-line
separated runs become ``paragraph`` blocks. Encoding detection reuses the
TXT parser's chardet approach.
"""

from __future__ import annotations

import re

import chardet

from app.parsers.base import BaseParser, Block, ParsedDocument
from app.parsers.registry import register

#: chardet detects on the first 64 KiB — enough for BOM/statistical detection.
_SAMPLE = 64 * 1024

_HEADING_RE = re.compile(r"^(#{1,6})\s+\S")
_FENCE_RE = re.compile(r"^(```|~~~)")
#: Thematic break (horizontal rule): --- *** ___ and spaced variants (* * *).
#: Skipped: a bare rule becomes a 1-token junk chunk that still costs an
#: embedding call. Only dashes/stars/underscores + spaces may match.
_HR_RE = re.compile(r"^(?:[-*_]\s*){3,}$")


@register("md")
class MarkdownParser(BaseParser):
    """Parse Markdown bytes into heading/code/paragraph blocks."""

    def parse_bytes(self, data: bytes) -> ParsedDocument:
        if not data.strip():
            return ParsedDocument(text="", blocks=[], metadata={})

        detected = chardet.detect(data[:_SAMPLE]) or {}
        encoding = str(detected.get("encoding") or "utf-8")
        try:
            text = data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            text = data.decode("utf-8", errors="replace")

        text = text.replace("\r\n", "\n").replace("\r", "\n")
        blocks = self._blocks(text)
        headings = sum(1 for b in blocks if b.block_type == "heading")
        return ParsedDocument(
            text=text.strip(),
            blocks=blocks,
            metadata={"encoding": encoding, "headings": headings},
        )

    @staticmethod
    def _blocks(text: str) -> list[Block]:
        blocks: list[Block] = []
        para: list[str] = []
        fence: list[str] | None = None
        fence_kind = ""

        def flush_paragraph() -> None:
            if para:
                blocks.append(Block(text="\n".join(para).strip()))
                para.clear()

        for line in text.split("\n"):
            if fence is not None:
                fence.append(line)
                if line.strip().startswith(fence_kind):
                    blocks.append(Block(text="\n".join(fence), block_type="code"))
                    fence = None
                continue
            if _FENCE_RE.match(line.strip()):
                flush_paragraph()
                fence, fence_kind = [line], line.strip()[:3]
                continue
            if _HEADING_RE.match(line.strip()):
                flush_paragraph()
                blocks.append(Block(text=line.strip(), block_type="heading"))
                continue
            if _HR_RE.match(line.strip()):
                flush_paragraph()
                continue
            if not line.strip():
                flush_paragraph()
                continue
            para.append(line)
        flush_paragraph()
        if fence is not None:  # unterminated fence: keep as a code block
            blocks.append(Block(text="\n".join(fence), block_type="code"))
        return [b for b in blocks if b.text]
