"""Generation quality evaluation (N3) — LLM-as-judge, zero extra dependencies.

Two metrics per query, each 0-1, judged with the same chat model (temperature
0, strict JSON output, one retry on parse failure):

* **faithfulness**     — decompose the answer into atomic claims and check how
  many are supported by the retrieved contexts. Low = hallucination.
* **answer_relevancy** — how directly the answer addresses the question.

Refusals (the model says it cannot answer) are reported separately as
``refusal_rate`` — an honest refusal is the *correct* behavior for an
unanswerable query and must not be punished.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.clients.chat_client import ChatClient, get_chat_client

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True, slots=True)
class GenerationJudgement:
    faithfulness: float
    relevancy: float
    refusal: bool
    notes: str


def _parse_json(raw: str) -> dict[str, Any] | None:
    match = _JSON_RE.search(raw)
    if not match:
        return None
    try:
        return json.loads(match.group(0))  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        return None


def _ask_json(client: ChatClient, prompt: str) -> dict[str, Any] | None:
    """Judge call with one retry on unparseable output."""
    for _ in range(2):
        content, _usage = client.complete_chat([{"role": "user", "content": prompt}])
        data = _parse_json(content)
        if data is not None:
            return data
    return None


FAITHFULNESS_PROMPT = """评审任务：判断「回答」中的每一条断言是否能被「上下文」支撑。

问题：{question}

上下文：
{contexts}

回答：
{answer}

只输出 JSON：{{"claims": [{{"claim": "...", "supported": true/false}}]}}
把回答拆成原子断言并逐条判定 supported。"""

RELEVANCY_PROMPT = """评审任务：评估「回答」与「问题」的相关性。

问题：{question}

回答：
{answer}

只输出 JSON：{{"relevancy": 0-10 的整数, "refusal": true/false, "note": "一句话理由"}}
- refusal=true 表示回答明确声明无法回答（这是合理的拒答行为）。
- relevancy：回答对该问题的直接相关程度（0-10）。"""


def judge_generation(
    question: str,
    answer: str,
    contexts: list[str],
    *,
    client: ChatClient | None = None,
) -> GenerationJudgement:
    """Faithfulness + relevancy for one (question, answer, contexts) triple."""
    judge = client or get_chat_client()
    ctx_text = "\n\n".join(f"[{i + 1}] {c[:400]}" for i, c in enumerate(contexts))

    faithfulness = 0.0
    claims_detail: list[dict[str, Any]] = []
    fdata = _ask_json(
        judge,
        FAITHFULNESS_PROMPT.format(question=question, contexts=ctx_text, answer=answer),
    )
    if fdata and isinstance(fdata.get("claims"), list):
        claims_detail = fdata["claims"]
        supported = [
            c for c in claims_detail if c.get("supported") in (True, "true", "yes", 1)
        ]
        if claims_detail:
            faithfulness = round(len(supported) / len(claims_detail), 4)
    else:
        logger.warning("[gen-eval] faithfulness judge unparseable")

    relevancy = 0.0
    refusal = False
    note = ""
    rdata = _ask_json(
        judge,
        RELEVANCY_PROMPT.format(question=question, answer=answer),
    )
    if rdata:
        try:
            relevancy = round(float(rdata.get("relevancy", 0)) / 10.0, 4)
        except (TypeError, ValueError):
            relevancy = 0.0
        refusal = rdata.get("refusal") in (True, "true", "yes", 1)
        note = str(rdata.get("note", ""))
    else:
        logger.warning("[gen-eval] relevancy judge unparseable")

    return GenerationJudgement(
        faithfulness=faithfulness,
        relevancy=relevancy,
        refusal=refusal,
        notes=note or json.dumps(claims_detail, ensure_ascii=False)[:500],
    )
