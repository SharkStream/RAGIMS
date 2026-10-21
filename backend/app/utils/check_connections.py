"""Standalone connectivity checker for every service configured in ``backend/.env``.

Verifies that ``app.core.config.settings`` resolves the configuration and that
every configured service (MySQL, Redis, Qdrant, MinIO, OpenAI embedding) is
reachable and authenticates with the values loaded from ``.env``.

Run from the ``backend/`` directory (either form works)::

    python -m app.utils.check_connections
    python app\\utils\\check_connections.py

Filter to specific services::

    python -m app.utils.check_connections --only mysql,redis

Exit code is ``0`` when every selected check passes, ``1`` otherwise, so the
script is safe to use in CI. Passwords and API keys are never printed in
clear text.
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
import time
import traceback
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

# Allow running as a plain script (python app\utils\check_connections.py):
# put the backend/ directory on sys.path so "app.*" imports resolve.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import settings  # noqa: E402  (needs the sys.path tweak)

_SOCKET_TIMEOUT = 6.0  # seconds, for all non-OpenAI network calls


def mask(secret: str | None, visible: int = 3) -> str:
    """Return a redacted representation safe to print."""
    if not secret:
        return "<empty>"
    return f"{secret[:visible]}***({len(secret)} chars)"


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    elapsed: float = 0.0
    error: str = ""
    traceback: str = field(default="", repr=False)


def check(name: str) -> Callable[[Callable[[], str]], Callable[[], CheckResult]]:
    """Decorator factory: wraps a function returning a detail string so that
    calling it later yields a timed, exception-safe ``CheckResult``."""

    def run(fn: Callable[[], str]) -> Callable[[], CheckResult]:
        @functools.wraps(fn)  # keep __name__ so --only filtering works
        def wrapper() -> CheckResult:
            start = time.perf_counter()
            try:
                detail = fn()
                elapsed = time.perf_counter() - start
                return CheckResult(name=name, ok=True, detail=detail, elapsed=elapsed)
            except (
                Exception
            ) as exc:  # noqa: BLE001 - report *any* failure as a failed check
                elapsed = time.perf_counter() - start
                return CheckResult(
                    name=name,
                    ok=False,
                    elapsed=elapsed,
                    error=f"{type(exc).__name__}: {exc}",
                    traceback=traceback.format_exc(),
                )

        return wrapper

    return run


# --------------------------------------------------------------------------- #
# 1. Configuration loading (no network)
# --------------------------------------------------------------------------- #


@check("config-load")
def check_config_load() -> str:
    return (
        f"app={settings.app.name}/{settings.app.env} | "
        f"mysql={settings.mysql.user}@{settings.mysql.host}:{settings.mysql.port}/{settings.mysql.database} | "
        f"redis={settings.redis.host}:{settings.redis.port}/{settings.redis.db} "
        f"pw={mask(settings.redis.password)} | "
        f"qdrant={settings.qdrant.url} key={mask(settings.qdrant.api_key)} | "
        f"minio={settings.minio.endpoint} user={settings.minio.access_key} | "
        f"openai={settings.openai.base_url} model={settings.openai.embedding_model} "
        f"key={mask(settings.openai.api_key)}"
    )


# --------------------------------------------------------------------------- #
# 2. Credential URL-encoding round-trip (no network) — catches the classic
#    "password contains @ / # / &" bug that silently corrupts connection URLs.
# --------------------------------------------------------------------------- #


@check("mysql-dsn-parse")
def check_mysql_dsn_parse() -> str:
    from sqlalchemy import make_url

    url = make_url(settings.mysql.dsn)
    ok_password = url.password == settings.mysql.password
    ok_host = url.host == settings.mysql.host
    if not (ok_password and ok_host):
        raise ValueError(
            "DSN round-trip mismatch: parsed host/password differ from settings "
            f"(host={url.host!r}, password_ok={ok_password}). "
            "Did credentials get URL-encoded when building the DSN?"
        )
    return (
        f"parse OK | user={url.username} | password={mask(url.password)} | "
        f"host={url.host}:{url.port} | db={url.database}"
    )


@check("redis-url-parse")
def check_redis_url_parse() -> str:
    from urllib.parse import urlparse

    parsed = urlparse(settings.redis.url)
    decoded = unquote(parsed.password or "")
    if decoded != (settings.redis.password or ""):
        raise ValueError(
            "Redis URL round-trip mismatch: decoded password differs from settings. "
            "RedisSettings.url must quote_plus the raw password."
        )
    return f"parse OK | host={parsed.hostname}:{parsed.port} | db={parsed.path} | pw={mask(decoded)}"


# --------------------------------------------------------------------------- #
# 3. Live connectivity
# --------------------------------------------------------------------------- #


@check("mysql-connect")
def check_mysql_connect() -> str:
    import pymysql

    conn = pymysql.connect(
        host=settings.mysql.host,
        port=settings.mysql.port,
        user=settings.mysql.user,
        password=settings.mysql.password,
        database=settings.mysql.database,
        charset=settings.mysql.charset,
        connect_timeout=_SOCKET_TIMEOUT,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION(), DATABASE(), @@character_set_database")
            version, database, charset = cur.fetchone()
        return f"server={version} | db={database} | charset={charset}"
    finally:
        conn.close()


@check("redis-connect")
def check_redis_connect() -> str:
    import redis

    # Path A: what Celery/brokers do — connect via the built URL.
    via_url = redis.from_url(settings.redis.url, socket_timeout=_SOCKET_TIMEOUT)
    ping_url = bool(via_url.ping())
    # Path B: direct client with the raw password from .env.
    via_raw = redis.Redis(
        host=settings.redis.host,
        port=settings.redis.port,
        db=settings.redis.db,
        password=settings.redis.password,
        socket_timeout=_SOCKET_TIMEOUT,
    )
    ping_raw = bool(via_raw.ping())
    if not (ping_url and ping_raw):
        raise ConnectionError(f"from_url ping={ping_url}, raw-password ping={ping_raw}")
    return "PING=True on both paths (from_url with encoded pw + raw pw direct)"


@check("qdrant-connect")
def check_qdrant_connect() -> str:
    req = urllib.request.Request(settings.qdrant.url + "/collections")
    if settings.qdrant.api_key:
        req.add_header("api-key", settings.qdrant.api_key)
    with urllib.request.urlopen(req, timeout=_SOCKET_TIMEOUT) as resp:
        payload = json.loads(resp.read())
    names = [c["name"] for c in payload["result"]["collections"]]
    return f"collections={names or []}"


@check("minio-connect")
def check_minio_connect() -> str:
    from minio import Minio

    client = Minio(
        settings.minio.endpoint,
        access_key=settings.minio.access_key,
        secret_key=settings.minio.secret_key,
        secure=settings.minio.secure,
    )
    buckets = [b.name for b in client.list_buckets()]
    return f"buckets={buckets or []} (auth OK)"


@check("openai-embedding")
def check_openai_embedding() -> str:
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.openai.api_key,
        base_url=settings.openai.base_url,
        timeout=settings.openai.timeout,
    )
    response = client.embeddings.create(
        model=settings.openai.embedding_model, input=["connection check"]
    )
    dim = len(response.data[0].embedding)
    expected = settings.openai.embedding_dimension
    if dim != expected:
        raise ValueError(
            f"embedding dimension mismatch: API returned {dim}, "
            f"OPENAI__EMBEDDING_DIMENSION={expected} — update .env!"
        )
    return f"model={settings.openai.embedding_model} | dim={dim} (matches .env)"


ALL_CHECKS: list[Callable[[], CheckResult]] = [
    check_config_load,
    check_mysql_dsn_parse,
    check_redis_url_parse,
    check_mysql_connect,
    check_redis_connect,
    check_qdrant_connect,
    check_minio_connect,
    check_openai_embedding,
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check .env connectivity for all RAGIMS backend services."
    )
    parser.add_argument(
        "--only",
        default="",
        help="comma-separated substring filter, e.g. 'mysql,redis' or 'qdrant'",
    )
    parser.add_argument("--json", action="store_true", help="print results as JSON")
    args = parser.parse_args()

    # Windows consoles default to GBK/cp936 and crash on the ✅/emoji output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    needles = [s.strip().lower() for s in args.only.split(",") if s.strip()]
    selected = [
        c for c in ALL_CHECKS if not needles or any(n in c.__name__ for n in needles)
    ]
    if needles and not selected:
        print(
            f"No checks match --only '{args.only}'. Available: "
            + ", ".join(c.__name__ for c in ALL_CHECKS)
        )
        return 2

    print("=" * 74)
    print("RAGIMS backend .env connectivity check")
    print(f"workspace: {_BACKEND_DIR}")
    print("=" * 74)

    results = [fn() for fn in selected]

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "name": r.name,
                        "ok": r.ok,
                        "detail": r.detail,
                        "elapsed_s": round(r.elapsed, 2),
                        "error": r.error,
                    }
                    for r in results
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for r in results:
            status = "PASS" if r.ok else "FAIL"
            line = f"[{status}] {r.name:<22} ({r.elapsed:5.2f}s)  {r.detail or r.error}"
            print(line)
            if not r.ok:
                print("-" * 74)
                print(r.traceback.rstrip())
                print("-" * 74)

    failed = [r for r in results if not r.ok]
    print("=" * 74)
    print(
        f"Summary: {len(results) - len(failed)}/{len(results)} passed"
        + (
            f" — failed: {', '.join(r.name for r in failed)}"
            if failed
            else " — all good ✅"
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
