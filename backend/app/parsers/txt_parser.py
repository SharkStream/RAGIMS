"""TXT parser (D2 step 3) — chardet encoding detection.

Plain text has no structural granularity: the whole content is returned as a
single ``paragraph`` block (page is None). CRLF/CR line endings are normalized
to LF.
"""

from __future__ import annotations

import chardet

from app.parsers.base import BaseParser, Block, ParsedDocument
from app.parsers.registry import register

#: chardet detects on the first 64 KiB — enough for BOM/statistical detection.
_SAMPLE = 64 * 1024


@register("txt")
class TxtParser(BaseParser):
    """Decode text bytes (chardet) into a one-block ParsedDocument."""

    def parse_bytes(self, data: bytes) -> ParsedDocument:
        if not data.strip():
            return ParsedDocument(text="", blocks=[], metadata={})

        detected = chardet.detect(data[:_SAMPLE]) or {}
        encoding = str(detected.get("encoding") or "utf-8")
        try:
            text = data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            text = data.decode("utf-8", errors="replace")

        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        return ParsedDocument(
            text=text,
            blocks=[Block(text=text, block_type="paragraph")],
            metadata={"encoding": encoding},
        )
