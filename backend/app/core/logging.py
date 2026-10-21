"""Unified logging configuration (loguru, JSON structured output).

`setup_logging()` is called once from ``app.main`` at startup. It removes loguru's
default handler, installs a JSON console sink and an optional rotating file sink,
and routes the stdlib ``logging`` stream (uvicorn, sqlalchemy, celery, ...) through
loguru so every record shares the same structured format.

Sinks deliberately run with ``enqueue=False``: loguru handlers are already
thread-safe in-process, ``enqueue=True`` adds a ``multiprocessing.SimpleQueue``
(creates a named pipe on Windows, hangs some test runners at exit, and breaks
under sandboxed environments). Celery workers are separate processes that call
``setup_logging()`` themselves, so cross-process safety is not needed here.
"""

from __future__ import annotations

import logging
import sys
import types
from pathlib import Path

from loguru import logger

_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)


class InterceptHandler(logging.Handler):
    """Forward stdlib log records to loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        # Map stdlib level name to loguru level number.
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Walk up the call stack to find the caller's frame (outside logging).
        frame: types.FrameType | None
        frame, depth = logging.currentframe(), 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging(
    level: str = "INFO",
    log_dir: str | Path | None = "logs",
    json_console: bool = True,
) -> None:
    """Configure loguru and redirect stdlib logging.

    Args:
        level: Minimum log level (e.g. ``"INFO"``, ``"DEBUG"``).
        log_dir: Directory for rotating file sink, or ``None`` to disable file logging.
        json_console: When ``True``, emit JSON lines to stderr; otherwise pretty text.
    """
    logger.remove()

    if json_console:
        logger.add(
            sys.stderr,
            level=level,
            serialize=True,
            enqueue=False,
            backtrace=True,
            diagnose=False,
        )
    else:
        logger.add(
            sys.stderr,
            level=level,
            format=_LOG_FORMAT,
            enqueue=False,
            backtrace=True,
            diagnose=False,
        )

    if log_dir is not None:
        # Never let an unwritable log directory kill the process (read-only
        # filesystems, sandboxed CI, permission mistakes): the console sink
        # above already covers observability. Best-effort only.
        try:
            path = Path(log_dir)
            path.mkdir(parents=True, exist_ok=True)
            logger.add(
                path / "ragims_{time:YYYY-MM-DD}.log",
                level=level,
                serialize=True,
                rotation="00:00",
                retention="14 days",
                compression="gz",
                enqueue=False,
                backtrace=True,
                diagnose=False,
            )
        except OSError as exc:
            logger.warning("File logging disabled ({}: {})", type(exc).__name__, exc)

    # Route stdlib loggers through loguru so third-party logs stay structured.
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy", "celery"):
        logging.getLogger(name).handlers = [InterceptHandler()]
        logging.getLogger(name).propagate = False
