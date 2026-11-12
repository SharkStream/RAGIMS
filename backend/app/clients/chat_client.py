"""Chat completion client (N1) — OpenAI-compatible streaming synthesis.

``stream_chat`` yields content deltas and finishes with a :class:`ChatUsage`
(if the gateway honors ``stream_options.include_usage``; degraded gateways
just omit the final usage chunk and the caller treats tokens as unknown).

Mirrors :mod:`app.clients.embedder` conventions: credentials/endpoint/model
come from settings, transient errors are the caller's concern (SSE streams
surface errors as an ``error`` event rather than retrying mid-stream).
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from app.core.config import settings


@dataclass(frozen=True, slots=True)
class ChatUsage:
    """Token accounting for one chat call (N1 metrics + cost tracking)."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    latency_ms: int = 0
    extra: dict = field(default_factory=dict)


class ChatClient:
    """OpenAI-compatible chat completions (streaming)."""

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.model_name = model_name or settings.openai.chat_model
        self._client = OpenAI(
            api_key=api_key if api_key is not None else settings.openai.api_key,
            base_url=base_url if base_url is not None else settings.openai.base_url,
            timeout=timeout if timeout is not None else settings.chat.stream_timeout,
        )

    def stream_chat(self, messages: list[dict[str, str]]) -> Iterator[str | ChatUsage]:
        """Yield content deltas, then a final :class:`ChatUsage`.

        The stream always ends with a usage object (tokens may be 0 when the
        gateway does not report usage) so callers have one deterministic
        completion signal.
        """
        started = time.perf_counter()
        params: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": 0.2,
        }
        stream = self._client.chat.completions.create(**params)  # type: ignore[arg-type]
        usage: ChatUsage | None = None
        for chunk in stream:
            if getattr(chunk, "usage", None) is not None:
                u = chunk.usage
                usage = ChatUsage(
                    prompt_tokens=getattr(u, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(u, "completion_tokens", 0) or 0,
                    total_tokens=getattr(u, "total_tokens", 0) or 0,
                    model=self.model_name,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
                continue
            for choice in getattr(chunk, "choices", None) or []:
                delta = getattr(choice, "delta", None)
                content = getattr(delta, "content", None) if delta else None
                if content:
                    yield content
        yield (
            usage
            or ChatUsage(
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                model=self.model_name,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        )


def get_chat_client() -> ChatClient:
    return ChatClient()
