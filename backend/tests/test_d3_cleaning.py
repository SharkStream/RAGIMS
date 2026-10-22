"""D3 cleaning tests (offline, pure function).

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_d3_cleaning.py -v -p no:cacheprovider
"""

from __future__ import annotations

from app.parsers.base import Block, ParsedDocument
from app.services.cleaning import clean


def mk(text: str, page: int | None = None, btype: str = "paragraph") -> Block:
    return Block(text=text, page=page, block_type=btype)


# --------------------------------------------------------------------------- #
# normalization (rules 1-3)
# --------------------------------------------------------------------------- #


def test_normalizes_crlf_and_cr() -> None:
    out = clean(ParsedDocument(text="a\r\nb\rc", blocks=[mk("a\r\nb\rc")]))
    assert out.blocks[0].text == "a\nb\nc"


def test_strips_control_and_zero_width_chars() -> None:
    raw = "he\x00llo\u200b wo\ufeffrld\x07"
    out = clean(ParsedDocument(text=raw, blocks=[mk(raw)]))
    assert out.blocks[0].text == "hello world"


def test_collapses_spaces_and_trims_lines() -> None:
    raw = "  too   many\tspaces  \n\nkeep  one "
    out = clean(ParsedDocument(text=raw, blocks=[mk(raw)]))
    assert out.blocks[0].text == "too many spaces\nkeep one"


def test_keeps_newlines_and_tabs_in_text_field_rebuilt() -> None:
    out = clean(ParsedDocument(text="x", blocks=[mk("l1"), mk("l2")]))
    assert out.text == "l1\n\nl2"


# --------------------------------------------------------------------------- #
# dedup (rules 4-5)
# --------------------------------------------------------------------------- #


def test_drops_adjacent_duplicate_lines_inside_block() -> None:
    out = clean(ParsedDocument(text="", blocks=[mk("same\nsame\nsame\ndiff\nsame")]))
    assert out.blocks[0].text == "same\ndiff\nsame"


def test_drops_adjacent_duplicate_blocks() -> None:
    out = clean(
        ParsedDocument(
            text="", blocks=[mk("dup", page=1), mk("dup", page=1), mk("other", page=2)]
        )
    )
    assert [b.text for b in out.blocks] == ["dup", "other"]
    assert out.metadata["cleaning"]["dropped_duplicate"] == 1


def test_non_adjacent_duplicates_survive() -> None:
    out = clean(ParsedDocument(text="", blocks=[mk("a"), mk("b"), mk("a")]))
    assert len(out.blocks) == 3


# --------------------------------------------------------------------------- #
# header/footer (rule 6)
# --------------------------------------------------------------------------- #


def build_pages(header: str | None, pages: int) -> list[Block]:
    return [
        mk(f"{header + chr(10) if header else ''}content line {i}", page=i)
        for i in range(1, pages + 1)
    ]


def test_removes_repeating_header_across_pages() -> None:
    out = clean(ParsedDocument(text="", blocks=build_pages("Q3 2026 Confidential", 5)))
    assert all("Confidential" not in b.text for b in out.blocks)
    assert out.metadata["cleaning"]["dropped_header_footer"] == 5


def test_removes_repeating_footer_too() -> None:
    blocks = [
        mk(f"real content {i}\nShared document footer", page=i) for i in range(1, 6)
    ]
    out = clean(ParsedDocument(text="", blocks=blocks))
    assert all("footer" not in b.text for b in out.blocks)


def test_no_header_footer_detection_below_three_pages() -> None:
    out = clean(ParsedDocument(text="", blocks=build_pages("Repeated", 2)))
    assert all("Repeated" in b.text for b in out.blocks)


def test_repeated_middle_line_is_not_header_footer() -> None:
    blocks = [mk(f"intro\nSHARED\nbody {i}", page=i) for i in range(1, 5)]
    out = clean(ParsedDocument(text="", blocks=blocks))
    assert all("SHARED" in b.text for b in out.blocks)


def test_long_line_is_never_treated_as_header() -> None:
    long_line = "x" * 200
    blocks = [mk(f"{long_line}\nbody {i}", page=i) for i in range(1, 5)]
    out = clean(ParsedDocument(text="", blocks=blocks))
    assert all(long_line in b.text for b in out.blocks)


# --------------------------------------------------------------------------- #
# garbled + empty (rule 7)
# --------------------------------------------------------------------------- #


def test_drops_garbled_blocks() -> None:
    garbled = "ok \ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd end"
    out = clean(ParsedDocument(text="", blocks=[mk("fine text"), mk(garbled, page=2)]))
    assert [b.text for b in out.blocks] == ["fine text"]
    assert out.metadata["cleaning"]["dropped_garbled"] == 1


def test_drops_blocks_that_become_empty() -> None:
    out = clean(ParsedDocument(text="", blocks=[mk("   \n \x00 "), mk("kept", page=1)]))
    assert [b.text for b in out.blocks] == ["kept"]


# --------------------------------------------------------------------------- #
# structure preservation (acceptance criterion 2) + purity
# --------------------------------------------------------------------------- #


def test_page_and_block_type_survive_cleaning() -> None:
    blocks = [
        mk("Intro heading", page=1, btype="heading"),
        mk("Body text", page=1),
        mk("| a | b |\n| --- | --- |", page=2, btype="table"),
    ]
    out = clean(ParsedDocument(text="", blocks=blocks))
    assert [(b.page, b.block_type) for b in out.blocks] == [
        (1, "heading"),
        (1, "paragraph"),
        (2, "table"),
    ]


def test_clean_does_not_mutate_input() -> None:
    raw = "a\r\nb\x00c"
    original = ParsedDocument(text=raw, blocks=[mk(raw, page=1)])
    clean(original)
    assert original.blocks[0].text == raw


def test_cleaning_metadata_stats_present() -> None:
    out = clean(ParsedDocument(text="", blocks=[mk("ok", page=1)]))
    assert out.metadata["cleaning"] == {
        "dropped_garbled": 0,
        "dropped_header_footer": 0,
        "dropped_duplicate": 0,
        "dropped_empty": 0,
    }


# --------------------------------------------------------------------------- #
# integration with real parser output (D2), still offline
# --------------------------------------------------------------------------- #


def test_clean_after_real_pdf_parse() -> None:
    import pymupdf

    doc = pymupdf.open()
    try:
        for i in range(4):
            page = doc.new_page()
            page.insert_text((72, 60), "ACME  Internal")  # header on every page
            page.insert_text((72, 90), f"Chapter body {i + 1} with content")
        data = doc.tobytes()
    finally:
        doc.close()

    from app.parsers.pdf_parser import PdfParser

    parsed = PdfParser().parse_bytes(data)
    out = clean(parsed)
    assert all("Internal" not in b.text for b in out.blocks)
    assert all(b.page is not None for b in out.blocks)
