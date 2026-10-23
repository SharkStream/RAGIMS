"""Embedding client (E1): batch, retry/backoff, token stats, DB config.

``embed_batch`` keeps the task-spec signature (returns vectors); it slices
input into batches of ``batch_size`` and retries transient failures (429 /
connection / 5xx) with :func:`app.utils.retry.with_backoff`. Token counts are
produced by :meth:`count_tokens` / :meth:`embed_with_usage` so stage F can
persist them into ``job_steps.output`` (acceptance 3).

Config comes from the ``embedding_models`` row (seeded by B2) via
:func:`build_embedder_from_model` — model name and dimension never come from
code constants at runtime.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

import tiktoken
from openai import (
    APIConnectionError,
    APIStatusError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.embedding_model import EmbeddingModel
from app.utils.retry import with_backoff

#: Transient OpenAI failures worth retrying (429 / network / 5xx).
RETRYABLE_ERRORS: tuple[type[BaseException], ...] = (
    RateLimitError,
    APIConnectionError,
    InternalServerError,
)

#: Additional server-side status codes we retry on (openai SDK raises
#: APIStatusError subclasses for these; 4xx others are permanent).
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, RETRYABLE_ERRORS):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in RETRYABLE_STATUS
    return False


@dataclass(frozen=True, slots=True)
class EmbeddingUsage:
    """Per-batch-run stats for ``job_steps.output`` (E1 step 3)."""

    token_count: int
    batch_count: int
    model_name: str
    dimension: int

    def to_output(self) -> dict:
        """The dict persisted into ``job_steps.output`` by stage F."""
        return {
            "embedding": {
                "token_count": self.token_count,
                "batch_count": self.batch_count,
                "model_name": self.model_name,
                "dimension": self.dimension,
            }
        }


class BaseEmbedder(ABC):
    """Embedding interface (E1 step 1)."""

    def __init__(
        self,
        model_name: str,
        dimension: int,
        batch_size: int = 64,
        encoding_name: str = "cl100k_base",
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        self.model_name = model_name
        self.dimension = dimension
        self.batch_size = batch_size
        self._encoding = tiktoken.get_encoding(encoding_name)

    @abstractmethod
    def _embed_once(self, texts: list[str]) -> list[list[float]]:
        """Embed one batch (<= batch_size) of texts; transient errors raise."""

    def count_tokens(self, texts: list[str]) -> int:
        """cl100k token count over the texts (E1 step 3)."""
        return sum(len(self._encoding.encode(t)) for t in texts)

    def _slice_batches(self, texts: list[str]) -> list[list[str]]:
        return [
            texts[i : i + self.batch_size] for i in range(0, len(texts), self.batch_size)
        ]

    def _validate(self, vectors: list[list[float]], expected: int) -> None:
        if len(vectors) != expected:
            raise ValueError(
                f"embedder returned {len(vectors)} vectors for {expected} inputs"
            )
        for v in vectors:
            if len(v) != self.dimension:
                raise ValueError(
                    f"embedder returned dimension {len(v)}, expected "
                    f"{self.dimension} (model={self.model_name})"
                )

    def embed_batch(
        self,
        texts: list[str],
        *,
        retry_when: Callable[[BaseException], bool] | None = None,
    ) -> list[list[float]]:
        """Embed texts in batches with transient-failure backoff (E1 step 2).

        ``retry_when`` defaults to the OpenAI transient-error predicate
        (429 / connection / 5xx); tests may inject a narrower one.
        """
        vectors: list[list[float]] = []
        for batch in self._slice_batches(texts):
            batch_vectors = with_backoff(
                lambda b=batch: self._embed_once(b),
                retry_when=retry_when or _is_retryable,
            )
            self._validate(batch_vectors, len(batch))
            vectors.extend(batch_vectors)
        return vectors

    def embed_with_usage(
        self, texts: list[str]
    ) -> tuple[list[list[float]], EmbeddingUsage]:
        """Vectors + stats for ``job_steps.output`` in one call."""
        batches = self._slice_batches(texts)
        vectors = self.embed_batch(texts)
        usage = EmbeddingUsage(
            token_count=self.count_tokens(texts),
            batch_count=len(batches),
            model_name=self.model_name,
            dimension=self.dimension,
        )
        return vectors, usage


class OpenAIEmbedder(BaseEmbedder):
    """OpenAI-compatible embeddings client (also serves local gateways)."""

    def __init__(
        self,
        model_name: str,
        dimension: int,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        batch_size: int = 64,
    ) -> None:
        super().__init__(model_name, dimension, batch_size)
        self._client = OpenAI(
            api_key=api_key if api_key is not None else settings.openai.api_key,
            base_url=base_url if base_url is not None else settings.openai.base_url,
            timeout=timeout if timeout is not None else settings.openai.timeout,
        )

    def _embed_once(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self.model_name, input=texts)
        # API may return rows out of order — restore input order by index.
        rows = sorted(response.data, key=lambda d: d.index)
        return [row.embedding for row in rows]


def build_embedder_from_model(
    model: EmbeddingModel, *, batch_size: int = 64
) -> BaseEmbedder:
    """Instantiate the right embedder from an ``embedding_models`` row (E1 step 4).

    Only the ``openai``-compatible provider exists in the MVP; the row's
    ``model_name``/``dimension`` win over settings, while credentials and
    endpoints come from ``settings.openai``.
    """
    if model.provider != "openai":
        raise ValueError(f"unsupported embedding provider: {model.provider!r}")
    return OpenAIEmbedder(
        model_name=model.model_name,
        dimension=model.dimension,
        batch_size=batch_size,
    )


def get_default_embedder(session: Session, *, batch_size: int = 64) -> BaseEmbedder:
    """Load the default model row from ``embedding_models`` and build it."""
    model = session.scalars(
        select(EmbeddingModel)
        .where(EmbeddingModel.is_default.is_(True))
        .order_by(EmbeddingModel.model_name)
        .limit(1)
    ).first()
    if model is None:
        model = session.scalars(select(EmbeddingModel).limit(1)).first()
    if model is None:
        raise LookupError("no embedding_models row — run scripts/seed.py first")
    return build_embedder_from_model(model, batch_size=batch_size)
