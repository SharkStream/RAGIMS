"""Reconcile chunks <-> Qdrant point IDs (E4 step 2, MVP).

Scan ``chunks`` rows missing ``qdrant_point_id`` and repair them:
back-fill IDs for points that already exist in Qdrant (matched via
payload ``chunk_index``), re-embed + re-upsert the rest. Safe to run
repeatedly (idempotent by construction).

J4 adds a second rule: MySQL ``documents.current_version`` vs the Qdrant
points carrying ``is_latest=true`` must agree per document — drift is
reported (not repaired; activation is an explicit API call).

Usage (from ``backend/``)::

    env/Scripts/python.exe scripts/reconcile.py
"""

from __future__ import annotations

import sys

from app.core.db import SessionLocal
from app.services.consistency import (
    find_is_latest_drift,
    find_missing_point_ids,
    repair_missing_point_ids,
)


def main() -> int:
    exit_code = 0
    with SessionLocal() as session:
        missing = find_missing_point_ids(session)
        if not missing:
            print("reconcile: all chunks carry a qdrant_point_id — nothing to do")
        else:
            print(f"reconcile: {len(missing)} chunk row(s) missing qdrant_point_id")
            report = repair_missing_point_ids(session)
            print(
                f"reconcile: backfilled={report['backfilled']} "
                f"reembedded={report['reembedded']}"
            )
            remaining = find_missing_point_ids(session)
            if remaining:
                print(
                    f"reconcile: WARNING {len(remaining)} row(s) still missing",
                    file=sys.stderr,
                )
                exit_code = 1

        drift = find_is_latest_drift(session)
        if drift:
            print(f"reconcile: WARNING {len(drift)} document(s) with is_latest drift:")
            for entry in drift:
                print(
                    f"  doc={entry['doc_id']} mysql_current="
                    f"{entry['mysql_current_version']} qdrant_latest="
                    f"{entry['qdrant_is_latest_versions']}"
                )
            exit_code = 1
        else:
            print("reconcile: is_latest pointers aligned (MySQL == Qdrant)")

        if exit_code == 0:
            print("reconcile: OK — chunks table and Qdrant are aligned")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
