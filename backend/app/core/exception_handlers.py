"""Global exception handlers — every error leaves the API as an ``ApiResponse``.

Registered once from ``main.py`` via :func:`register_exception_handlers`. Covers:

* :class:`AppError` — business errors raised by routers/services.
* ``RequestValidationError`` — FastAPI/pydantic request validation (422).
* ``StarletteHTTPException`` — raw ``HTTPException``s so they never escape the
  unified envelope.
* ``Exception`` — last-resort 500, logged with full traceback via loguru.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import (
    ERR_BAD_REQUEST,
    ERR_DUPLICATE,
    ERR_FORBIDDEN,
    ERR_INTERNAL,
    ERR_NOT_FOUND,
    ERR_UNAUTHORIZED,
    ERR_VALIDATION,
    AppError,
)
from app.schemas.common import fail

# HTTP status -> error code for exceptions that arrive without an AppError code.
_STATUS_TO_CODE: dict[int, str] = {
    401: ERR_UNAUTHORIZED,
    403: ERR_FORBIDDEN,
    404: ERR_NOT_FOUND,
    409: ERR_DUPLICATE,
    422: ERR_VALIDATION,
}


def _code_for_status(status_code: int) -> str:
    if status_code in _STATUS_TO_CODE:
        return _STATUS_TO_CODE[status_code]
    return ERR_BAD_REQUEST if status_code < 500 else ERR_INTERNAL


def _error_response(
    status_code: int, code: str, message: str, details: Any = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=fail(code, message, data=details).model_dump(),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the unified error handlers to ``app``."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Keep only JSON-safe fields; pydantic v2 ``errors()`` may embed
        # non-serializable ctx values (e.g. ValueError instances).
        details = [
            {
                "loc": [str(part) for part in err.get("loc", ())],
                "msg": str(err.get("msg", "")),
                "type": str(err.get("type", "")),
            }
            for err in exc.errors()
        ]
        return _error_response(
            422, ERR_VALIDATION, "Request validation failed", details
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return _error_response(
            exc.status_code, _code_for_status(exc.status_code), str(exc.detail)
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.opt(exception=exc).error(
            "Unhandled exception on {} {}", request.method, request.url.path
        )
        return _error_response(500, ERR_INTERNAL, "Internal server error")
