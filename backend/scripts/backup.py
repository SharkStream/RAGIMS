"""Full backup (M5): MySQL dump + MinIO objects into a timestamped folder.

Layout::

    backups/20261106-171500/
      mysql.sql            (mysqldump --single-transaction)
      minio/raw-docs/...   (every object, preserving keys)
      minio/parsed-text/...
      MANIFEST.json        (versions, counts, durations)

MySQL dump needs the ``mysqldump`` client on PATH (docker deployments:
``docker exec <mysql-container> mysqldump ...`` — see runbook §7).
Restore steps live in ``docs/runbook.md`` §7; restore is intentionally manual
(destructive, wants a human).

Usage (from ``backend/``)::

    env/Scripts/python.exe scripts/backup.py
    env/Scripts/python.exe scripts/backup.py --out D:\\backups
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clients.minio_client import MinioObjectStore  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402

setup_logging(level=settings.app.log_level)


def _python_dump(out_dir: Path) -> Path:
    """Zero-dependency dump: per-table INSERT statements + full-表 DELETE.

    Restore contract (runbook §7): empty schema via alembic, then run this
    file with FOREIGN_KEY_CHECKS disabled (it manages the pragma itself).
    Column values are rendered as literals (str/number/bool/JSON/datetime/None).
    """
    from app.core.db import engine
    from sqlalchemy import text

    tables = [
        "tenants",
        "users",
        "datasources",
        "embedding_models",
        "documents",
        "document_versions",
        "chunks",
        "ingestion_jobs",
        "job_steps",
        "audit_logs",
        "quality_checks",
        "evaluation_runs",
    ]
    sql_path = out_dir / "mysql.sql"
    with sql_path.open("w", encoding="utf-8") as fh:
        fh.write("-- RAGIMS python dump (data only; schema via alembic)\n")
        fh.write("SET FOREIGN_KEY_CHECKS=0;\n")
        with engine.connect() as conn:
            for table in tables:
                fh.write(f"DELETE FROM {table};\n")
                rows = conn.execute(
                    text(f"SELECT * FROM {table}")  # noqa: S608 — fixed names
                )
                cols = list(rows.keys())
                for row in rows:
                    values = ", ".join(_render(v) for v in row)
                    fh.write(
                        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({values});\n"
                    )
        fh.write("SET FOREIGN_KEY_CHECKS=1;\n")
    return sql_path


def _render(value: object) -> str:
    """SQL literal for one column value."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, datetime):
        return "'" + value.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "'"
    if isinstance(value, (dict, list)):
        return "'" + json.dumps(value, ensure_ascii=False).replace("'", "''") + "'"
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def _mysql_dump(out_dir: Path) -> Path:
    """mysqldump --single-transaction into ``mysql.sql``."""
    sql_path = out_dir / "mysql.sql"
    cmd = [
        "mysqldump",
        f"-h{settings.mysql.host}",
        f"-P{settings.mysql.port}",
        f"-u{settings.mysql.user}",
        f"-p{settings.mysql.password}",
        "--single-transaction",
        "--routines",
        settings.mysql.database,
    ]
    with sql_path.open("wb") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE)  # noqa: S603
    if proc.returncode != 0:
        raise RuntimeError(
            f"mysqldump failed (rc={proc.returncode}): "
            f"{proc.stderr.decode(errors='replace')[:400]}\n"
            "hint: use --mode python (zero-dependency) or "
            "'docker exec <mysql-container> mysqldump ...' (runbook §7)"
        )
    return sql_path


def _minio_objects(out_dir: Path) -> dict[str, int]:
    """Download every object of both buckets, preserving keys."""
    objects = MinioObjectStore()
    counts: dict[str, int] = {}
    for bucket in (settings.minio.bucket_raw, settings.minio.bucket_parsed):
        target = out_dir / "minio" / bucket
        target.mkdir(parents=True, exist_ok=True)
        n = 0
        for obj in objects._client.list_objects(bucket, recursive=True):
            dest = target / obj.object_name
            dest.parent.mkdir(parents=True, exist_ok=True)
            objects._client.fget_object(bucket, obj.object_name, str(dest))
            n += 1
        counts[bucket] = n
    return counts


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Full RAGIMS backup.")
    parser.add_argument("--out", default="backups", help="backup root directory")
    parser.add_argument(
        "--mode",
        choices=("python", "mysqldump"),
        default="python",
        help="python = zero-dependency INSERT dump (default); "
        "mysqldump = native client (must be on PATH)",
    )
    args = parser.parse_args(argv)

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out) / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[backup] → {out_dir}")

    started = time.perf_counter()
    manifest: dict[str, object] = {
        "created_at": datetime.now(UTC).isoformat(),
        "database": settings.mysql.database,
        "minio": {
            "raw": settings.minio.bucket_raw,
            "parsed": settings.minio.bucket_parsed,
        },
    }

    sql_path = _python_dump(out_dir) if args.mode == "python" else _mysql_dump(out_dir)
    manifest["mysql_dump_bytes"] = sql_path.stat().st_size
    manifest["mysql_dump_mode"] = args.mode
    print(f"[backup] mysql.sql ({sql_path.stat().st_size / 1024:.1f} KB, {args.mode})")

    counts = _minio_objects(out_dir)
    manifest["minio_objects"] = counts
    for bucket, n in counts.items():
        print(f"[backup] minio {bucket}: {n} objects")

    (out_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"[backup] DONE ✓ ({time.perf_counter() - started:.1f}s) — restore: runbook §7"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
