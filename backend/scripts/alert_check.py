"""Alert checker (M3) — cron-able health gate with threshold exits.

Checks (in order): dependency probes (MySQL/Redis/Qdrant), then business
thresholds against the metadata DB:

* queue backlog     — pending+running+retrying jobs above ``--max-queue``
* failure rate      — 24h failed / settled above ``--max-failure-rate``
                      (skipped when fewer than ``--min-sample`` settled jobs)

Exit codes: 0 = healthy, 1 = at least one alert, 2 = checker itself failed.
Output is human-readable; ``--json`` prints the payload for log shippers.

Usage (from ``backend/``)::

    env/Scripts/python.exe scripts/alert_check.py
    env/Scripts/python.exe scripts/alert_check.py --json --max-queue 20
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.models import Document, IngestionJob  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

setup_logging(level=settings.app.log_level)

DEFAULT_MAX_QUEUE = 50
DEFAULT_MAX_FAILURE_RATE = 0.3
DEFAULT_MIN_SAMPLE = 5


def _probe(name: str, fn: Any) -> dict[str, Any]:
    import time

    started = time.perf_counter()
    try:
        detail = fn()
        return {
            "name": name,
            "ok": True,
            "detail": str(detail),
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": name,
            "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }


def _probes() -> list[dict[str, Any]]:
    from app.api.health import CHECKS

    return [_probe(name, fn) for name, fn in CHECKS]


def _business_check(max_queue: int, max_rate: float, min_sample: int) -> dict[str, Any]:
    """Queue depth + 24h failure rate straight from the metadata DB."""
    with SessionLocal() as session:
        documents_total = int(
            session.scalar(select(func.count()).select_from(Document)) or 0
        )
        by_status = session.execute(
            select(IngestionJob.status, func.count()).group_by(IngestionJob.status)
        ).all()
        counts = {s: int(n) for s, n in by_status}
        queue_depth = sum(counts.get(s, 0) for s in ("pending", "running", "retrying"))
        since = datetime.utcnow() - timedelta(hours=24)
        failed = int(
            session.scalar(
                select(func.count())
                .select_from(IngestionJob)
                .where(IngestionJob.status == "failed")
                .where(IngestionJob.updated_at >= since)
            )
            or 0
        )
        settled = int(
            session.scalar(
                select(func.count())
                .select_from(IngestionJob)
                .where(IngestionJob.status.in_(("succeeded", "failed")))
                .where(IngestionJob.updated_at >= since)
            )
            or 0
        )

    alerts: list[dict[str, str]] = []
    if queue_depth > max_queue:
        alerts.append(
            {"code": "QUEUE_BACKLOG", "detail": f"queue {queue_depth} > {max_queue}"}
        )
    rate = None
    if settled >= min_sample:
        rate = round(failed / settled, 3)
        if rate > max_rate:
            alerts.append(
                {
                    "code": "HIGH_FAILURE_RATE",
                    "detail": f"24h rate {rate} ({failed}/{settled}) > {max_rate}",
                }
            )
    return {
        "gauges": {
            "documents_total": documents_total,
            "queue_depth": queue_depth,
            "jobs_failed_24h": failed,
            "jobs_settled_24h": settled,
            "failure_rate_24h": rate,
        },
        "alerts": alerts,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="RAGIMS alert checker.")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--max-queue", type=int, default=DEFAULT_MAX_QUEUE)
    parser.add_argument(
        "--max-failure-rate", type=float, default=DEFAULT_MAX_FAILURE_RATE
    )
    parser.add_argument("--min-sample", type=int, default=DEFAULT_MIN_SAMPLE)
    args = parser.parse_args(argv)

    alerts: list[dict[str, str]] = []
    probes: list[dict[str, Any]] = []
    try:
        probes = _probes()
        alerts.extend(
            {"code": f"DEP_{p['name'].upper()}", "detail": p["detail"]}
            for p in probes
            if not p["ok"]
        )
        business = _business_check(
            args.max_queue, args.max_failure_rate, args.min_sample
        )
        alerts.extend(business["alerts"])
    except Exception as exc:  # noqa: BLE001 — the checker itself failed
        payload: dict[str, Any] = {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"[alert-check] ERROR: {payload['error']}")
        return 2

    payload = {
        "status": "ok" if not alerts else "alert",
        "probes": probes,
        **business,
        "alerts": alerts,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, default=str))
    else:
        for p in probes:
            mark = "OK " if p["ok"] else "FAIL"
            print(f"[{mark}] {p['name']}: {p['detail']}")
        g = business["gauges"]
        rate = g["failure_rate_24h"]
        print(
            f"[GAUGE] documents={g['documents_total']} queue={g['queue_depth']} "
            f"failed_24h={g['jobs_failed_24h']}/{g['jobs_settled_24h']} "
            f"rate={rate if rate is not None else 'n/a'}"
        )
        for a in alerts:
            print(f"[ALERT] {a['code']}: {a['detail']}")
        print(f"[alert-check] status={payload['status']} ({len(alerts)} alert(s))")
    return 1 if alerts else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
