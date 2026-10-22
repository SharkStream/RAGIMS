"""Document cleaning (D3): denoise + normalize, preserving block structure.

``clean`` is a **pure function**: it returns a new ``ParsedDocument`` and
never mutates its input. Rules (stage plan D3 step 2):

1. normalize line endings (``\\r\\n``/``\\r`` → ``\\n``)
2. strip control characters & zero-width characters (keep ``\\n``)
3. collapse runs of spaces/tabs inside a line; trim line edges
4. drop repeated lines inside a block (adjacent duplicates)
5. drop adjacent duplicate blocks
6. header/footer removal: a line that starts/ends blocks on >= 3 distinct
   pages is page furniture and is stripped from block edges
7. drop garbled blocks (high U+FFFD ratio after decoding fallbacks) and
   blocks that became empty

Cleaning stats are appended to ``metadata["cleaning"]`` for observability;
``page``/``block_type`` survive untouched (acceptance criterion 2).
"""

from __future__ import annotations

import re
from dataclasses import replace

from app.parsers.base import Block, ParsedDocument

#: A line seen at block edges on at least this many distinct pages is
#: treated as header/footer (below 3 pages the signal is too weak).
_HDR_FOOTER_MIN_PAGES = 3

#: Only short lines are eligible as header/footer candidates.
_HDR_FOOTER_MAX_LEN = 120

#: Blocks whose replacement-character ratio exceeds this are dropped.
_GARBLED_RATIO = 0.05

# C0/C1 controls except \n; DEL; zero-width & BOM characters.
_CTRL_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u0080-\u009f\u200b-\u200f\ufeff]"
)
_SPACES_RE = re.compile(r"[ \t\u00a0]+")


def _normalize_text(text: str) -> str:
    """Line endings, control chars, whitespace collapsing (rule 1-3)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CTRL_RE.sub("", text)
    lines = (_SPACES_RE.sub(" ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def _strip_repeated_lines(text: str) -> str:
    """Drop adjacent duplicate lines inside one block (rule 4)."""
    kept: list[str] = []
    for line in text.split("\n"):
        if not kept or kept[-1] != line:
            kept.append(line)
    return "\n".join(kept)


def _looks_garbled(text: str) -> bool:
    """Heuristic: too many U+FFFD replacement chars → decoding failed."""
    if not text:
        return False
    return text.count("\ufffd") / len(text) > _GARBLED_RATIO


def _header_footer_lines(blocks: list[Block]) -> set[str]:
    """Lines recurring at block edges across >= 3 distinct pages (rule 6).

    A line is counted at most once per page — a one-line block whose text is
    both first and last, or two blocks sharing a first line on the same page,
    must not inflate the page count.
    """
    edge_pages: dict[str, set[int]] = {}
    for block in blocks:
        if block.page is None:
            continue
        lines = [ln for ln in block.text.split("\n") if ln]
        for edge in (lines[:1], lines[-1:]):
            for line in edge:
                if len(line) <= _HDR_FOOTER_MAX_LEN:
                    edge_pages.setdefault(line, set()).add(block.page)
    return {
        line
        for line, pages in edge_pages.items()
        if len(pages) >= _HDR_FOOTER_MIN_PAGES
    }


def clean(parsed: ParsedDocument) -> ParsedDocument:
    """Return a cleaned copy of ``parsed`` (input untouched)."""
    stats = {
        "dropped_garbled": 0,
        "dropped_header_footer": 0,
        "dropped_duplicate": 0,
        "dropped_empty": 0,
    }

    # pass 1: per-block normalize + repeated-line strip + garbled filter
    blocks: list[Block] = []
    for block in parsed.blocks:
        text = _strip_repeated_lines(_normalize_text(block.text))
        if not text:
            stats["dropped_empty"] += 1
            continue
        if _looks_garbled(text):
            stats["dropped_garbled"] += 1
            continue
        blocks.append(replace(block, text=text))

    # pass 2: header/footer line removal (page-aware)
    hf_lines = _header_footer_lines(blocks)
    if hf_lines:
        cleaned_blocks: list[Block] = []
        for block in blocks:
            lines = block.text.split("\n")
            while lines and lines[0] in hf_lines:
                lines.pop(0)
                stats["dropped_header_footer"] += 1
            while lines and lines[-1] in hf_lines:
                lines.pop()
                stats["dropped_header_footer"] += 1
            text = "\n".join(lines)
            if not text:
                stats["dropped_empty"] += 1
                continue
            cleaned_blocks.append(replace(block, text=text))
        blocks = cleaned_blocks

    # pass 3: adjacent duplicate blocks (rule 5)
    deduped: list[Block] = []
    for block in blocks:
        if deduped and deduped[-1].text == block.text:
            stats["dropped_duplicate"] += 1
            continue
        deduped.append(block)
    blocks = deduped

    metadata = {**parsed.metadata, "cleaning": stats}
    return ParsedDocument(
        text="\n\n".join(b.text for b in blocks), blocks=blocks, metadata=metadata
    )
