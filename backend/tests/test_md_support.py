"""Markdown support tests: parser behaviour + upload whitelist."""

from __future__ import annotations

import pytest
from app.core.errors import AppError
from app.parsers import get_parser
from app.parsers.md_parser import MarkdownParser
from app.services.document_service import validate_upload


class TestMarkdownParser:
    def test_headings_and_paragraphs(self) -> None:
        doc = MarkdownParser().parse_bytes(
            b"# Title\n\nintro line\nsecond line\n\n## Section\ntail"
        )
        types = [b.block_type for b in doc.blocks]
        assert types == ["heading", "paragraph", "heading", "paragraph"]
        assert doc.blocks[0].text == "# Title"
        assert "intro line" in doc.blocks[1].text
        assert doc.metadata["headings"] == 2
        assert doc.text.startswith("# Title")

    def test_fenced_code_block(self) -> None:
        doc = MarkdownParser().parse_bytes(b"para\n\n```python\nx = 1\n```\n\nafter")
        code = [b for b in doc.blocks if b.block_type == "code"]
        assert len(code) == 1 and "x = 1" in code[0].text
        assert [b.block_type for b in doc.blocks] == ["paragraph", "code", "paragraph"]

    def test_unterminated_fence_kept_as_code(self) -> None:
        doc = MarkdownParser().parse_bytes(b"```\nnever closed")
        assert [b.block_type for b in doc.blocks] == ["code"]

    def test_empty_and_whitespace(self) -> None:
        for raw in (b"", b"   \n\t\n"):
            doc = MarkdownParser().parse_bytes(raw)
            assert doc.text == "" and doc.blocks == []

    def test_crlf_normalized(self) -> None:
        doc = MarkdownParser().parse_bytes(b"# T\r\n\r\nline one\r\nline two")
        assert "\r" not in doc.text
        assert "line one\nline two" in doc.text

    def test_registry_dispatch(self) -> None:
        assert isinstance(get_parser("md"), MarkdownParser)


class TestUploadWhitelist:
    def test_md_accepted_with_text_mime(self) -> None:
        outcome_ext = validate_upload("notes.md", "text/markdown", 100)
        assert outcome_ext == "md"

    def test_md_accepted_without_mime(self) -> None:
        assert validate_upload("notes.md", None, 100) == "md"

    @pytest.mark.parametrize("mime", ["application/pdf", "image/png"])
    def test_md_rejected_with_non_text_mime(self, mime: str) -> None:
        with pytest.raises(AppError) as ei:
            validate_upload("notes.md", mime, 100)
        assert ei.value.code == "ERR_FILE_TYPE_NOT_ALLOWED"

    def test_exe_still_rejected(self) -> None:
        with pytest.raises(AppError) as ei:
            validate_upload("evil.exe", None, 100)
        assert ei.value.code == "ERR_FILE_TYPE_NOT_ALLOWED"
        assert "md" in ei.value.details["allowed"]
