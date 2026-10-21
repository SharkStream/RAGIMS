"""Unified API response envelope and pagination structure.

Every business endpoint wraps its payload in :class:`ApiResponse` so the
frontend always gets ``{code, message, data}`` (``code="OK"`` on success, an
``ERR_*`` constant on failure — see ``app.core.errors``). List endpoints return
:class:`PageResult` inside ``data``.

Usage::

    @router.get("/documents/{doc_id}")
    def get_document(doc_id: str, db: Session = Depends(get_db)) -> ApiResponse[DocumentOut]:
        return ok(DocumentOut.model_validate(doc))

    return ok(PageResult[DocumentOut](items=rows, total=n, page=p, page_size=s))
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from app.core.errors import ERR_OK

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Unified response envelope: ``code`` / ``message`` / ``data``."""

    code: str = ERR_OK
    message: str = "ok"
    data: T | None = None


class PageResult(BaseModel, Generic[T]):
    """Pagination payload — place inside ``ApiResponse.data``."""

    items: list[T] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20

    @classmethod
    def of(
        cls, items: list[T], *, total: int, page: int, page_size: int
    ) -> PageResult[T]:
        """Build from a raw list + count (``total`` is the unpaginated count)."""
        return cls(items=items, total=total, page=page, page_size=page_size)


def ok(data: T | None = None, *, message: str = "ok") -> ApiResponse[T]:
    """Success envelope helper."""
    return ApiResponse[T](code=ERR_OK, message=message, data=data)


def fail(
    code: str,
    message: str,
    *,
    data: Any = None,
) -> ApiResponse[Any]:
    """Failure envelope helper (also used by the global exception handlers).

    ``data`` is typed ``Any`` (not ``None``) so error ``details`` (e.g. a list
    of validation errors) fit inside the envelope: ``ApiResponse[None]`` would
    make the ``data`` field literal-``None`` and reject any payload.
    """
    return ApiResponse[Any](code=code, message=message, data=data)
