"""Reconcile chunks <-> Qdrant point IDs (E4 step 2, MVP).

Scan ``chunks`` rows missing ``qdrant_point_id`` and repair them:
back-fill IDs for points that already exist in Qdrant (matched via
payload ``chunk_index``), re-embed + re-upsert the rest. Safe to run
repeatedly (idempotent by construction).

Usage (from ``backend/``)::

    env/Scripts/python.exe scripts/reconcile.py
"""

from __future__ import annotations

import sys

from app.core.db import SessionLocal
from app.services.consistency import find_missing_point_ids, repair_missing_point_ids


def main() -> int:
    with SessionLocal() as session:
        missing = find_missing_point_ids(session)
        if not missing:
            print("reconcile: all chunks carry a qdrant_point_id — nothing to do")
            return 0
        print(f"reconcile: {len(missing)} chunk row(s) missing qdrant_point_id")
        report = repair_missing_point_ids(session)
        print(
            f"reconcile: backfilled={report['backfilled']} "
            f"reembedded={report['reembedded']}"
        )
        remaining = find_missing_point_ids(session)
        if remaining:
            print(f"reconcile: WARNING {len(remaining)} row(s) still missing", file=sys.stderr)
            return 1
        print("reconcile: OK — chunks table and Qdrant are aligned")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
