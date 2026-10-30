"""Unified retry helper with exponential backoff (E1 step 2, reusable).

``with_backoff`` is deliberately dependency-free: the caller injects the
exception tuple and the sleep callable, so tests can assert the exact delay
sequence without patching time, and future callers (storage, Qdrant) reuse
the same policy.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

#: Default retry policy: 5 attempts total, 0.5s doubling, capped at 8s.
DEFAULT_RETRIES = 4
DEFAULT_BASE_DELAY = 0.5
DEFAULT_MAX_DELAY = 8.0


def with_backoff(
    fn: Callable[[], T],
    *,
    retries: int = DEFAULT_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    retry_when: Callable[[BaseException], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] | None = None,
) -> T:
    """Call ``fn()`` retrying with exponential backoff.

    Retry decision: ``retry_when(exc)`` when given, otherwise
    ``isinstance(exc, retry_on)``. The delay before attempt *n* (0-based) is
    ``min(max_delay, base_delay * 2**n)`` plus optional jitter. The last
    exception propagates unchanged when attempts are exhausted.
    """
    if retries < 0:
        raise ValueError("retries must be >= 0")

    def _should_retry(exc: BaseException) -> bool:
        if retry_when is not None:
            return retry_when(exc)
        return isinstance(exc, retry_on)

    for attempt in range(retries + 1):
        try:
            return fn()
        except BaseException as exc:
            if attempt == retries or not _should_retry(exc):
                raise
            delay = min(max_delay, base_delay * 2**attempt)
            if jitter is not None:
                delay += jitter()
            sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover
