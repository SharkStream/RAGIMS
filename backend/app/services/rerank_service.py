"""LLM pointwise reranker (N2) — re-order retrieved hits by relevance.

For each of the top ``rerank_top_n`` hits the judge model scores "how relevant
is this passage to the question" on 0-10 (one batched call, strict JSON out).
Failures degrade gracefully: any parse error returns the input order
unchanged (rerank is an enhancement, never a hard dependency).

Off by default (``RETRIEVAL__RERANK=false``); enable per-deployment after
measuring latency (one LLM round-trip ≈ 1-3 s).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from app.clients.chat_client import ChatClient, get_chat_client
from app.services.search_service import SearchHit

logger = logging.getLogger(__name__)

_SCORE_RE = re.compile(r"(\d+(?:\.\d+)?)")

_JUDGE_PROMPT = """你是检索相关性评审。针对「问题」，给每个候选片段打 0-10 的相关分（10 = 完全回答该问题所需，0 = 无关）。
只输出 JSON：{{"scores": [<按候选顺序的整数分>]}}，不要输出其它内容。

问题：{question}

候选片段：
{passages}
"""


@dataclass(frozen=True, slots=True)
class RerankOutcome:
    hits: list[SearchHit]
    reranked: bool
    scores: list[float]


def _parse_scores(raw: str, expected: int) -> list[float] | None:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        scores = data["scores"]
        if not isinstance(scores, list) or len(scores) != expected:
            return None
        out: list[float] = []
        for s in scores:
            m = _SCORE_RE.search(str(s))
            out.append(float(m.group(1)) if m else 0.0)
        return out
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def rerank_hits(
    question: str,
    hits: list[SearchHit],
    *,
    top_n: int,
    client: ChatClient | None = None,
) -> RerankOutcome:
    """Re-rank the top ``top_n`` hits; the tail passes through unchanged."""
    if not hits:
        return RerankOutcome(hits=hits, reranked=False, scores=[])
    head = hits[:top_n]
    tail = hits[top_n:]

    passages = "\n\n".join(f"[{i + 1}] {h.text[:500]}" for i, h in enumerate(head))
    judge = client or get_chat_client()
    messages = [
        {
            "role": "user",
            "content": _JUDGE_PROMPT.format(question=question, passages=passages),
        }
    ]
    raw_parts: list[str] = []
    try:
        for piece in judge.stream_chat(messages):
            if isinstance(piece, str):
                raw_parts.append(piece)
        raw = "".join(raw_parts)
        scores = _parse_scores(raw, len(head))
        if scores is None:
            raise ValueError(f"judge output not parseable: {raw[:120]}")
    except Exception as exc:  # noqa: BLE001 — degrade to input order
        logger.warning(
            f"[rerank] degraded to original order: {type(exc).__name__}: {exc}"
        )
        return RerankOutcome(hits=hits, reranked=False, scores=[])

    ranked = sorted(zip(head, scores, strict=True), key=lambda p: p[1], reverse=True)
    reranked = [h for h, _ in ranked]
    all_scores = [s for _, s in ranked] + [0.0] * len(tail)
    logger.info(
        f"[rerank] top order changed={reranked != head} "
        f"best={max(all_scores) if all_scores else 0}"
    )
    return RerankOutcome(hits=reranked + list(tail), reranked=True, scores=all_scores)
