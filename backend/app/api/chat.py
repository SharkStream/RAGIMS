"""Chat API (N1): SSE streaming RAG answers with citation provenance.

``POST /api/chat`` body::

    {"query": "...", "conversation_id": "...?", "history": [{role, content}]}

Response ``text/event-stream``::

    event: token     data: {"delta": "..."}
    event: done      data: {"answer", "citations", "usage", "conversation_id"}
    event: error     data: {"message"}      (mid-stream LLM failure)

The retrieval (search_test) runs with the CALLER's role so the tenant/
is_latest/deleted/access-level mandatory filter applies unchanged.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.clients.chat_client import get_chat_client
from app.core.deps import CurrentUser, get_current_user
from app.core.errors import AppError
from app.core.metrics import record_chat_tokens
from app.core.ratelimit import RateLimitExceeded, check_rate_limit, limit_for
from app.core.tracing import trace_span
from app.services.chat_service import (
    build_chat_contexts,
    build_messages,
    citations_of,
)
from app.services.guardrails import guard_chunk_text, guard_query

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: str = Field(pattern=r"^(user|assistant)$")
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=64)
    history: list[ChatMessage] = Field(default_factory=list, max_length=40)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post(
    "",
    summary="RAG chat: stream an answer synthesized from retrieved chunks",
    response_class=StreamingResponse,
)
def chat(
    body: ChatRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> StreamingResponse:
    # N4: per-user rate limit (429 before any LLM/retrieval work).
    try:
        check_rate_limit(user.id, "chat", limit_for("chat"))
    except RateLimitExceeded as exc:
        raise AppError(
            f"操作过于频繁，请 {exc.retry_after} 秒后重试",
            code="ERR_RATE_LIMITED",
            status_code=429,
        ) from exc

    # N4: PII redaction on the query (config-gated).
    query = guard_query(body.query)
    contexts = build_chat_contexts(
        query=query,
        tenant_id=user.tenant_id,
        role=user.role,
        top_k=settings_chat_top_k(),
    )
    # N4: sanitize retrieved chunk texts (injection patterns) before prompt.
    for c in contexts:
        c.text = guard_chunk_text(c.text)
    messages = build_messages(query, contexts, [m.model_dump() for m in body.history])
    conversation_id = body.conversation_id
    client = get_chat_client()

    def stream() -> Generator[str, None, None]:
        answer_parts: list[str] = []
        usage_payload: dict = {}
        try:
            with trace_span(
                "ragims.chat.generation",
                {"model": client.model_name, "contexts": len(contexts)},
            ):
                for piece in client.stream_chat(messages):
                    if isinstance(piece, str):
                        answer_parts.append(piece)
                        yield _sse("token", {"delta": piece})
                    else:
                        usage_payload = {
                            "prompt_tokens": piece.prompt_tokens,
                            "completion_tokens": piece.completion_tokens,
                            "total_tokens": piece.total_tokens,
                            "model": piece.model,
                            "latency_ms": piece.latency_ms,
                        }
                        record_chat_tokens(piece.prompt_tokens, piece.completion_tokens)
            done: dict = {
                "answer": "".join(answer_parts),
                "citations": citations_of(contexts),
                "usage": usage_payload,
                "conversation_id": conversation_id,
            }
            yield _sse("done", done)
        except Exception as exc:  # noqa: BLE001 — mid-stream failure → error event
            yield _sse(
                "error",
                {
                    "message": f"{type(exc).__name__}: {exc}"[:300],
                    "answer": "".join(answer_parts),
                },
            )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def settings_chat_top_k() -> int:
    from app.core.config import settings

    return settings.chat.top_k
