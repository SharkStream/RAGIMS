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
    mode = run.retrieval_mode or "dense"

    for item in run.dataset:
        query = str(item["query"])
        expected = {str(d) for d in item.get("expected_doc_ids") or []}
        result = search_test(
            query=query,
            tenant_id=run.tenant_id,
            top_k=top_k,
            role="admin",  # benchmark view: every access level the tenant owns
            mode=mode,
        )
        # Document-level ranking: a doc contributing several chunk hits should
        # occupy ONE slot in the top-k ranking, not skew recall@k downward.
        hit_ids: list[str] = []
        seen: set[str] = set()
        for h in result.hits:
            if h.doc_id not in seen:
                seen.add(h.doc_id)
                hit_ids.append(h.doc_id)
        if mode == "hybrid_rerank" and len(hit_ids) > 1:
            from app.services.rerank_service import rerank_hits

            outcome = rerank_hits(query, list(result.hits), top_n=top_k * 4)
            hit_ids = []
            seen = set()
            for h in outcome.hits:
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
        "retrieval_mode": mode,
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


def _run_generation_evaluation(
    session: Session,
    run: EvaluationRun,
    *,
    top_k: int,
) -> EvaluationRun:
    """N3: synthesize answers via the chat path, judge faithfulness/relevancy."""
    from app.clients.chat_client import get_chat_client
    from app.services.chat_service import build_chat_contexts, build_messages
    from app.services.generation_eval import judge_generation

    client = get_chat_client()
    per_query: list[dict[str, Any]] = []
    faiths: list[float] = []
    relevs: list[float] = []
    refusals: list[float] = []

    for item in run.dataset:
        query = str(item["query"])
        contexts = build_chat_contexts(
            query=query,
            tenant_id=run.tenant_id,
            role="admin",  # benchmark view
            top_k=top_k,
        )
        messages = build_messages(query, contexts, [])
        answer, _usage = client.complete_chat(messages)
        judgement = judge_generation(
            query,
            answer,
            [c.text for c in contexts],
            client=client,
        )
        faiths.append(judgement.faithfulness)
        relevs.append(judgement.relevancy)
        refusals.append(1.0 if judgement.refusal else 0.0)
        per_query.append(
            {
                "query": query,
                "answer": answer,
                "citations": citations_of(contexts),
                "faithfulness": judgement.faithfulness,
                "answer_relevancy": judgement.relevancy,
                "refusal": judgement.refusal,
                "judge_notes": judgement.notes,
            }
        )

    n = len(run.dataset) or 1
    run.metrics = {
        "kind": "generation",
        "queries": len(run.dataset),
        "top_k": top_k,
        "retrieval_mode": run.retrieval_mode or "dense",
        "faithfulness": round(sum(faiths) / n, 4),
        "answer_relevancy": round(sum(relevs) / n, 4),
        "refusal_rate": round(sum(refusals) / n, 4),
    }
    run.result = per_query
    logger.info(
        f"[gen-eval] run {run.id} '{run.name}': "
        f"faithfulness={run.metrics['faithfulness']} "
        f"relevancy={run.metrics['answer_relevancy']} "
        f"refusal_rate={run.metrics['refusal_rate']}"
    )
    return run


def citations_of(contexts: list[Any]) -> list[dict[str, Any]]:
    from app.services.chat_service import citations_of as _c

    return _c(contexts)


def create_and_run_evaluation(
    session: Session,
    *,
    tenant_id: str,
    user_id: str,
    name: str,
    dataset: list[dict[str, Any]],
    top_k: int,
    parent_run_id: str | None = None,
    retrieval_mode: str = "dense",
    kind: str = "retrieval",
) -> EvaluationRun:
    """Create the run row, execute it, and commit (single user-facing step)."""
    run = EvaluationRun(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        name=name,
        parent_run_id=parent_run_id,
        retrieval_mode=retrieval_mode,
        kind=kind,
        dataset=dataset,
    )
    session.add(run)
    session.flush()
    if kind == "generation":
        _run_generation_evaluation(session, run, top_k=top_k)
    else:
        run_evaluation(session, run, top_k=top_k)
    session.commit()
    return run
