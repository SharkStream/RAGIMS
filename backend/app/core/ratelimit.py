"""Per-user fixed-window rate limiter (N4) — Redis INCR + EXPIRE.

Zero dependencies (Redis client already present). Fixed window is deliberate:
simple, atomic, and sufficient for abuse prevention (not for billing).

Disabled by default (``RATELIMIT__ENABLED=false``) so dev/tests are
unaffected; production sets it true and tunes per-endpoint limits.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when a user exceeds the configured window limit."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"rate limited; retry in {retry_after}s")


def check_rate_limit(
    user_id: str, bucket: str, limit: int, window_seconds: int = 60
) -> int:
    """Count one call for ``(user, bucket)``; raise when over ``limit``.

    Returns the remaining allowance. Uses Redis INCR + EXPIRE (atomic via
    transaction when the key is new).
    """
    if not settings.ratelimit.enabled or limit <= 0:
        return limit
    import redis

    try:
        client: Any = redis.from_url(
            settings.redis.url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        key = f"ratelimit:{bucket}:{user_id}"
        pipe = client.pipeline()
        pipe.incr(key, 1)
        pipe.ttl(key)
        count, ttl = pipe.execute()
        if count == 1 or ttl < 0:
            client.expire(key, window_seconds)
            ttl = window_seconds
        remaining = max(limit - int(count), 0)
        if int(count) > limit:
            raise RateLimitExceeded(max(int(ttl), 1))
        return remaining
    except RateLimitExceeded:
        raise
    except Exception as exc:  # noqa: BLE001 — limiter outage never blocks traffic
        logger.warning(
            f"[ratelimit] degraded (allowing request): {type(exc).__name__}: {exc}"
        )
        return limit


def limit_for(bucket: str) -> int:
    """Configured limit for a bucket name (chat / upload / search)."""
    r = settings.ratelimit
    return {
        "chat": r.chat_per_min,
        "upload": r.upload_per_min,
        "search": r.search_per_min,
    }.get(bucket, 60)
