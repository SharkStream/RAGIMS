"""Quality checks (L2) — pipeline-level output scoring per document version.

Three built-in checkers over a version's chunks (plan.md 6.2 step 11):

* ``empty_ratio``     — share of empty / near-empty chunks (risk signal)
* ``duplicate_ratio`` — share of duplicated normalized chunk texts
* ``length_spread``   — coefficient of variation of chunk lengths
  (an abrupt change points at a chunking regression)

Scores are risks: **lower is better**, normalized to [0, 1]; raw counters live
in ``detail`` for the dashboard. The worker runs them right after finalize on
a best-effort basis — a checker crash must never fail an ingest job.
"""

from __future__ import annotations

import logging
import math
import uuid
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.document_version import DocumentVersion
from app.models.quality_check import QualityCheck

logger = logging.getLogger(__name__)

#: Near-empty threshold: chunks shorter than this (stripped) count as empty.
EMPTY_CHUNK_MIN_CHARS = 20

CHECK_TYPES = ("empty_ratio", "duplicate_ratio", "length_spread")


@dataclass(frozen=True)
class CheckResult:
    """One checker outcome (score in [0, 1]; lower is better)."""

    check_type: str
    score: float
    detail: dict[str, object]


def _normalize(text: str) -> str:
    return "".join(text.split()).lower()


def check_empty_ratio(texts: list[str]) -> CheckResult:
    """Share of chunks that are empty or below ``EMPTY_CHUNK_MIN_CHARS``."""
    if not texts:
        return CheckResult("empty_ratio", 0.0, {"chunks": 0, "empty": 0})
    empties = sum(1 for t in texts if len(t.strip()) < EMPTY_CHUNK_MIN_CHARS)
    return CheckResult(
        "empty_ratio",
        round(empties / len(texts), 4),
        {"chunks": len(texts), "empty": empties, "min_chars": EMPTY_CHUNK_MIN_CHARS},
    )


def check_duplicate_ratio(texts: list[str]) -> CheckResult:
    """Share of chunks whose normalized text appears more than once."""
    if not texts:
        return CheckResult("duplicate_ratio", 0.0, {"chunks": 0, "duplicates": 0})
    counts = Counter(_normalize(t) for t in texts)
    duplicates = sum(n for n in counts.values() if n > 1)
    return CheckResult(
        "duplicate_ratio",
        round(duplicates / len(texts), 4),
        {
            "chunks": len(texts),
            "duplicates": duplicates,
            "unique": len(counts),
        },
    )


def check_length_spread(texts: list[str]) -> CheckResult:
    """Coefficient of variation of chunk lengths (0 = perfectly uniform)."""
    if not texts:
        return CheckResult("length_spread", 0.0, {"chunks": 0})
    lengths = [len(t) for t in texts]
    mean = sum(lengths) / len(lengths)
    if mean == 0:
        return CheckResult(
            "length_spread", 1.0, {"chunks": len(texts), "mean": 0.0, "cv": None}
        )
    variance = sum((n - mean) ** 2 for n in lengths) / len(lengths)
    cv = math.sqrt(variance) / mean
    return CheckResult(
        "length_spread",
        round(min(cv, 1.0), 4),
        {"chunks": len(texts), "mean": round(mean, 1), "cv": round(cv, 4)},
    )


CHECKERS = {
    "empty_ratio": check_empty_ratio,
    "duplicate_ratio": check_duplicate_ratio,
    "length_spread": check_length_spread,
}


def run_quality_checks(session: Session, doc_version_id: str) -> list[QualityCheck]:
    """Run every checker against a version's chunks, replacing previous rows.

    Idempotent by design: existing rows for the version are deleted first, so
    re-running (reprocess) always reflects the latest chunk set. Accepts a
    version id, or a DocumentVersion ORM object (defensive: pipeline stages
    pass the detached object around).
    """
    doc_version_id = str(getattr(doc_version_id, "id", doc_version_id))
    texts = list(
        session.scalars(
            select(Chunk.text).where(Chunk.doc_version_id == doc_version_id)
        )
    )
    version = session.get(DocumentVersion, doc_version_id)
    if version is None:
        raise ValueError(f"doc_version {doc_version_id} not found")

    rows: list[QualityCheck] = []
    for check_type in CHECK_TYPES:
        result = CHECKERS[check_type](texts)
        rows.append(
            QualityCheck(
                id=str(uuid.uuid4()),
                doc_version_id=doc_version_id,
                check_type=result.check_type,
                score=result.score,
                detail=result.detail,
            )
        )
    session.execute(
        delete(QualityCheck).where(QualityCheck.doc_version_id == doc_version_id)
    )
    session.add_all(rows)
    session.commit()
    logger.info(
        f"[quality] v{doc_version_id}: "
        + " ".join(f"{r.check_type}={r.score}" for r in rows)
    )
    return rows


def best_effort_quality_checks(session, doc_version_id: str) -> None:  # noqa: ANN001
    """Worker-side wrapper: a checker crash logs a warning, never fails ingest."""
    try:
        run_quality_checks(session, doc_version_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"[quality] checks skipped for {doc_version_id}: "
            f"{type(exc).__name__}: {exc}"
        )
