"""Stable, machine-readable error codes for the unified API envelope.

Every business error carries one of these codes in ``ApiResponse.code`` so the
frontend can branch on them without parsing messages. ``ERR_OK`` is the success
marker (``"OK"``); the ``ERR_*`` constants map 1:1 onto HTTP status codes chosen
by the raiser (see ``core.exception_handlers``).
"""

from __future__ import annotations

from typing import Any

# --- success ---------------------------------------------------------------- #
ERR_OK = "OK"

# --- generic ---------------------------------------------------------------- #
ERR_BAD_REQUEST = "ERR_BAD_REQUEST"  # 400
ERR_VALIDATION = "ERR_VALIDATION"  # 422 (request body/query validation)
ERR_UNAUTHORIZED = "ERR_UNAUTHORIZED"  # 401
ERR_FORBIDDEN = "ERR_FORBIDDEN"  # 403
ERR_NOT_FOUND = "ERR_NOT_FOUND"  # 404
ERR_DUPLICATE = "ERR_DUPLICATE"  # 409 (unique violation, e.g. content_hash)
ERR_INTERNAL = "ERR_INTERNAL"  # 500
ERR_UNAVAILABLE = "ERR_UNAVAILABLE"  # 503 (dependency down)


class AppError(Exception):
    """Business error carrying a stable ``code`` + HTTP ``status_code``.

    Raise it from routers/services; the global handler in
    ``core.exception_handlers`` converts it into an ``ApiResponse`` envelope::

        raise AppError("document not found", code=ERR_NOT_FOUND, status_code=404)
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = ERR_BAD_REQUEST,
        status_code: int = 400,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


class NotFoundError(AppError):
    """404 — resource does not exist (or is filtered out by tenant scope)."""

    def __init__(self, message: str = "resource not found", **kwargs: Any) -> None:
        super().__init__(message, code=ERR_NOT_FOUND, status_code=404, **kwargs)


class DuplicateError(AppError):
    """409 — uniqueness violation (e.g. same content_hash for a document)."""

    def __init__(self, message: str = "duplicate resource", **kwargs: Any) -> None:
        super().__init__(message, code=ERR_DUPLICATE, status_code=409, **kwargs)


class ValidationFailedError(AppError):
    """422 — semantic validation failure beyond pydantic's syntactic checks."""

    def __init__(self, message: str = "validation failed", **kwargs: Any) -> None:
        super().__init__(message, code=ERR_VALIDATION, status_code=422, **kwargs)
