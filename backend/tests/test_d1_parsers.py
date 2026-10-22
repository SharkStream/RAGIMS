"""D1 parser abstraction tests (offline, pure logic).

Concrete parsers (pdf/docx/txt) arrive with D2 and self-register; these tests
verify the contract — dataclass shapes, ABC enforcement, registry dispatch
and error behaviour — using throwaway fakes that are always cleaned up so the
global registry never leaks into other tests.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_d1_parsers.py -v -p no:cacheprovider
"""

from __future__ import annotations

import pytest
from app.parsers import registry
from app.parsers.base import (
    SUPPORTED_TYPES,
    BaseParser,
    Block,
    ParsedDocument,
    UnsupportedFileType,
)
from app.parsers.registry import get_parser, register, registered_types

# --------------------------------------------------------------------------- #
# dataclasses
# --------------------------------------------------------------------------- #


def test_block_defaults() -> None:
    b = Block(text="hello")
    assert b.page is None and b.block_type == "paragraph"


def test_parsed_document_defaults() -> None:
    doc = ParsedDocument(text="hello")
    assert doc.blocks == [] and doc.metadata == {}


def test_parsed_document_holds_blocks() -> None:
    doc = ParsedDocument(
        text="h\np",
        blocks=[Block(text="h", page=1, block_type="heading"), Block(text="p")],
        metadata={"title": "T"},
    )
    assert doc.blocks[0].block_type == "heading"
    assert doc.metadata["title"] == "T"


# --------------------------------------------------------------------------- #
# ABC contract
# --------------------------------------------------------------------------- #


def test_base_parser_is_abstract() -> None:
    with pytest.raises(TypeError):
        BaseParser()  # type: ignore[abstract]

    class Noop(BaseParser):
        def parse_bytes(self, data: bytes) -> ParsedDocument:
            return ParsedDocument(text="ok")

    assert Noop().parse_bytes(b"x").text == "ok"


def test_supported_types_match_b1_domain() -> None:
    assert SUPPORTED_TYPES == {"pdf", "docx", "txt"}


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #


class _FakePdf(BaseParser):
    def parse_bytes(self, data: bytes) -> ParsedDocument:
        return ParsedDocument(text="pdf-fake")


class _FakeDocx(BaseParser):
    def parse_bytes(self, data: bytes) -> ParsedDocument:
        return ParsedDocument(text="docx-fake")


class _FakeTxt(BaseParser):
    def parse_bytes(self, data: bytes) -> ParsedDocument:
        return ParsedDocument(text="txt-fake")


@pytest.fixture()
def clean_registry():
    """Empty the global registry for the test, restore the snapshot after.

    D2's real parsers self-register at collection time (import side effect);
    the mechanism tests below need a clean slate and must never leak fakes.
    """
    snapshot = dict(registry._REGISTRY)
    registry._REGISTRY.clear()
    yield registry._REGISTRY
    registry._REGISTRY.clear()
    registry._REGISTRY.update(snapshot)


def test_register_and_dispatch_three_types(clean_registry) -> None:
    register("pdf")(_FakePdf)
    register("docx")(_FakeDocx)
    register("txt")(_FakeTxt)

    assert registered_types() == {"pdf", "docx", "txt"}
    assert isinstance(get_parser("pdf"), _FakePdf)
    assert isinstance(get_parser("docx"), _FakeDocx)
    assert isinstance(get_parser("txt"), _FakeTxt)


def test_get_parser_returns_fresh_instances(clean_registry) -> None:
    register("pdf")(_FakePdf)
    assert get_parser("pdf") is not get_parser("pdf")


def test_unknown_type_raises_unsupported(clean_registry) -> None:
    register("pdf")(_FakePdf)
    with pytest.raises(UnsupportedFileType) as exc:
        get_parser("pptx")
    assert exc.value.file_type == "pptx"
    assert "pptx" in str(exc.value) and "pdf" in str(exc.value)


def test_unsupported_type_has_no_parser_even_when_registry_empty(
    clean_registry,
) -> None:
    with pytest.raises(UnsupportedFileType):
        get_parser("pdf")


def test_register_rejects_unknown_file_type(clean_registry) -> None:
    with pytest.raises(ValueError, match="SUPPORTED_TYPES"):
        register("pptx")(_FakePdf)


def test_register_rejects_duplicates(clean_registry) -> None:
    register("pdf")(_FakePdf)
    with pytest.raises(ValueError, match="already registered"):
        register("pdf")(_FakeDocx)
