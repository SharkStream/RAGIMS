"""Evaluation engine (L3) — retrieval quality benchmarks over a live tenant.

A run takes a small dataset (``[{query, expected_doc_ids}]``), executes each
query through the same retrieval path as ``/search/test`` (mandatory tenant +
is_latest + ACL filters; evaluated from the admin viewpoint so every level the
tenant owns is visible), and aggregates classic ranking metrics:

* ``recall@k``      — share of expected docs retrieved in top-k
* ``mrr``           — mean reciprocal rank of the first relevant hit
* ``ndcg@k``        — normalized DCG with binary relevance
* ``hit_rate``      — share of queries with at least one expected doc in top-k

Results persist on the ``evaluation_runs`` row (metrics aggregate + per-query
breakdown) so the dashboard can chart history and reviewers can flag bad rows.
"""

from __future__ import annotations

import logging
import math
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.evaluation_run import EvaluationRun
from app.services.search_service import search_test

logger = logging.getLogger(__name__)


def _dcg(relevances: list[float]) -> float:
    return sum(rel / math.log2(pos + 1) for pos, rel in enumerate(relevances, start=1))


def single_query_metrics(
    hit_doc_ids: list[str],
    expected: set[str],
    top_k: int,
) -> dict[str, float]:
    """recall@k / rr / ndcg@k for one query (binary relevance)."""
    top = hit_doc_ids[:top_k]
    relevant_positions = [i + 1 for i, d in enumerate(top) if d in expected]

    recall = len(set(top) & expected) / len(expected) if expected else 0.0
    rr = 1.0 / relevant_positions[0] if relevant_positions else 0.0

    dcg = _dcg([1.0 if d in expected else 0.0 for d in top])
    ideal_hits = min(len(expected), top_k)
    idcg = _dcg([1.0] * ideal_hits)
    ndcg = dcg / idcg if idcg > 0 else 0.0

    return {
        "recall@k": round(recall, 4),
        "reciprocal_rank": round(rr, 4),
        "ndcg@k": round(ndcg, 4),
        "first_hit_rank": float(relevant_positions[0]) if relevant_positions else 0.0,
    }


def run_evaluation(
    session: Session,
    run: EvaluationRun,
    *,
    top_k: int = 5,
) -> EvaluationRun:
    """Execute every dataset query, aggregate metrics, persist on the run row."""
    per_query: list[dict[str, Any]] = []
    recalls: list[float] = []
    rrs: list[float] = []
    ndcgs: list[float] = []
    hits: list[float] = []

    for item in run.dataset:
        query = str(item["query"])
        expected = {str(d) for d in item.get("expected_doc_ids") or []}
        result = search_test(
            query=query,
            tenant_id=run.tenant_id,
            top_k=top_k,
            role="admin",  # benchmark view: every access level the tenant owns
        )
        # Document-level ranking: a doc contributing several chunk hits should
        # occupy ONE slot in the top-k ranking, not skew recall@k downward.
        hit_ids: list[str] = []
        seen: set[str] = set()
        for h in result.hits:
            if h.doc_id not in seen:
                seen.add(h.doc_id)
                hit_ids.append(h.doc_id)
        m = single_query_metrics(hit_ids, expected, top_k)
        recalls.append(m["recall@k"])
        rrs.append(m["reciprocal_rank"])
        ndcgs.append(m["ndcg@k"])
        hits.append(1.0 if m["first_hit_rank"] > 0 else 0.0)
        per_query.append(
            {
                "query": query,
                "expected_doc_ids": sorted(expected),
                "hit_doc_ids": hit_ids[:top_k],
                **m,
            }
        )
    n = len(run.dataset) or 1
    run.metrics = {
        "queries": len(run.dataset),
        "top_k": top_k,
        "recall@k": round(sum(recalls) / n, 4),
        "mrr": round(sum(rrs) / n, 4),
        "ndcg@k": round(sum(ndcgs) / n, 4),
        "hit_rate": round(sum(hits) / n, 4),
    }
    run.result = per_query
    logger.info(
        f"[eval] run {run.id} '{run.name}': recall@k={run.metrics['recall@k']} "
        f"mrr={run.metrics['mrr']} ndcg@k={run.metrics['ndcg@k']} "
        f"hit_rate={run.metrics['hit_rate']}"
    )
    return run


def create_and_run_evaluation(
    session: Session,
    *,
    tenant_id: str,
    user_id: str,
    name: str,
    dataset: list[dict[str, Any]],
    top_k: int,
    parent_run_id: str | None = None,
) -> EvaluationRun:
    """Create the run row, execute it, and commit (single user-facing step)."""
    run = EvaluationRun(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        name=name,
        parent_run_id=parent_run_id,
        dataset=dataset,
    )
    session.add(run)
    session.flush()
    run_evaluation(session, run, top_k=top_k)
    session.commit()
    return run
