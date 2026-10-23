"""D5 end-to-end pipeline tests: parse -> clean -> chunk (offline).

The sample builders come from ``tests/fixtures/build_samples.py`` (imported
via ``tests/conftest.py`` sys.path entry); bytes are built in memory because
the sandbox forbids subprocess file writes — see ``tests/fixtures/README.md``.

Coverage: acceptance asks for >= 70% on core modules, measured at stage I1
(pytest-cov is not installed yet); these tests exercise every public path of
``app/parsers/*``, ``app/services/cleaning.py`` and ``app/chunkers/*``.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_parsing_pipeline.py -v -p no:cacheprovider
"""

from __future__ import annotations

import io

import build_samples
import pymupdf
import pytest
import tiktoken
from app.chunkers.base import DEFAULT_CHUNKER_CONFIG
from app.chunkers.fixed_token_chunker import FixedTokenChunker
from app.parsers.docx_parser import DocxParser
from app.parsers.pdf_parser import PdfParser
from app.parsers.txt_parser import TxtParser
from app.services.cleaning import clean
from docx import Document as DocxDocument

ENC = tiktoken.get_encoding(DEFAULT_CHUNKER_CONFIG.encoding_name)
chunker = FixedTokenChunker()


def run_pipeline(data: bytes, parser) -> list:
    """parse -> clean -> chunk with the default MVP config."""
    parsed = parser.parse_bytes(data)
    cleaned = clean(parsed)
    return chunker.chunk(cleaned)


# --------------------------------------------------------------------------- #
# acceptance 1: all three sample formats produce non-empty chunk lists
# --------------------------------------------------------------------------- #


def test_pdf_sample_end_to_end() -> None:
    data = build_samples.build_pdf_bytes(header="Q3 2026 Confidential", pages=3)
    parsed = PdfParser().parse_bytes(data)
    assert [b.page for b in parsed.blocks] == [1, 2, 3]
    assert parsed.metadata["title"] == "RAGIMS Sample"

    cleaned = clean(parsed)
    assert all("Confidential" not in b.text for b in cleaned.blocks)

    chunks = chunker.chunk(cleaned)
    assert chunks
    assert {c.page for c in chunks} <= {1, 2, 3}
    assert all(0 < c.token_count <= DEFAULT_CHUNKER_CONFIG.chunk_size for c in chunks)


def test_docx_sample_end_to_end() -> None:
    chunks = run_pipeline(build_samples.build_docx_bytes(), DocxParser())
    assert chunks
    # heading + body paragraphs + markdown table all survive as chunks
    kinds = {c.metadata["block_type"] for c in chunks}
    assert {"heading", "paragraph", "table"} <= kinds


def test_txt_sample_end_to_end() -> None:
    chunks = run_pipeline(build_samples.build_txt_bytes(), TxtParser())
    assert chunks
    assert all(c.page is None for c in chunks)  # txt has no page structure


def test_sample_hashes_are_unique_and_stable() -> None:
    chunks = run_pipeline(build_samples.build_txt_bytes(), TxtParser())
    hashes = [c.chunk_hash for c in chunks]
    assert len(set(hashes)) == len(hashes)  # no identical chunks in the sample
    again = run_pipeline(build_samples.build_txt_bytes(), TxtParser())
    assert [c.chunk_hash for c in again] == hashes  # deterministic builders


# --------------------------------------------------------------------------- #
# acceptance 2: edge cases fail clearly, never crash the pipeline
# --------------------------------------------------------------------------- #


def test_empty_txt_yields_zero_chunks_without_error() -> None:
    assert run_pipeline(b"", TxtParser()) == []
    assert run_pipeline(b"   \n\n  ", TxtParser()) == []


def test_empty_pdf_raises_empty_file_error() -> None:
    with pytest.raises(pymupdf.EmptyFileError):
        PdfParser().parse_bytes(b"")


def test_empty_docx_raises_bad_zip() -> None:
    with pytest.raises(Exception) as exc:  # noqa: PT011 - zipfile raises many
        DocxParser().parse_bytes(b"")
    assert type(exc.value).__name__ in {"BadZipFile", "PackageNotFoundError"}


def test_encrypted_pdf_raises_with_clear_message() -> None:
    data = build_samples.build_encrypted_pdf_bytes(password="pw")
    with pytest.raises(ValueError, match="password-protected"):
        PdfParser().parse_bytes(data)


def test_oversize_text_is_chunked_not_rejected() -> None:
    # ~4x the default chunk_size of tokens in ONE block: the API layer rejects
    # oversized uploads (C1, 413); the pipeline layer must handle big input.
    big = build_samples.lorem(tokens_hint=2048, offset=7)
    chunks = run_pipeline(big.encode("utf-8"), TxtParser())
    assert len(chunks) >= 4
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    for c in chunks:
        assert 0 < c.token_count <= DEFAULT_CHUNKER_CONFIG.chunk_size


def test_very_long_single_paragraph_keeps_window_invariant() -> None:
    cfg_over, cfg_size = 50, 512
    one_block = build_samples.lorem(tokens_hint=5000, offset=11)
    parsed = DocxParser().parse_bytes(_docx_with_single_paragraph(one_block))
    cleaned = clean(parsed)
    chunks = chunker.chunk(cleaned)
    assert len(chunks) > 5
    for c in chunks[:-1]:
        assert c.token_count == cfg_size
    assert cfg_over < chunks[-1].token_count <= cfg_size


def _docx_with_single_paragraph(text: str) -> bytes:
    doc = DocxDocument()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_whitespace_only_pdf_text_survives_pipeline() -> None:
    # a PDF whose "text" is only whitespace: parsers/cleaners must not crash
    doc = pymupdf.open()
    try:
        doc.new_page().insert_text((72, 72), "     ")
        data = doc.tobytes()
    finally:
        doc.close()
    assert run_pipeline(data, PdfParser()) == []
