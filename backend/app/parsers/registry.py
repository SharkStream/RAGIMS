"""Parser registry (D1 step 3): ``file_type`` → concrete parser dispatch.

Concrete parsers self-register at import time (stage D2)::

    @register("pdf")
    class PdfParser(BaseParser): ...

``get_parser`` returns a fresh instance per call (parsers are stateless, but
fresh instances keep that invariant honest).
"""

from __future__ import annotations

from typing import TypeVar

from app.parsers.base import SUPPORTED_TYPES, BaseParser, UnsupportedFileType

TParser = TypeVar("TParser", bound=BaseParser)

_REGISTRY: dict[str, type[BaseParser]] = {}


def register(file_type: str):
    """Class decorator registering a parser under ``file_type``.

    Registering the same type twice is a programming error → ``ValueError``;
    registering outside :data:`SUPPORTED_TYPES` is likewise rejected so the
    registry and the DB's ``file_type`` domain stay aligned.
    """

    def decorator(cls: type[TParser]) -> type[TParser]:
        if file_type not in SUPPORTED_TYPES:
            raise ValueError(
                f"cannot register {file_type!r}: not in SUPPORTED_TYPES"
                f" {sorted(SUPPORTED_TYPES)}"
            )
        if file_type in _REGISTRY:
            raise ValueError(f"parser for {file_type!r} already registered")
        _REGISTRY[file_type] = cls
        return cls

    return decorator


def get_parser(file_type: str) -> BaseParser:
    """Instantiate the parser registered for ``file_type``.

    Raises :class:`UnsupportedFileType` for unknown/unsupported types.
    """
    cls = _REGISTRY.get(file_type)
    if cls is None:
        raise UnsupportedFileType(file_type, supported=set(_REGISTRY))
    return cls()


def registered_types() -> set[str]:
    """Types that currently have a parser (used by probes and health checks)."""
    return set(_REGISTRY)
