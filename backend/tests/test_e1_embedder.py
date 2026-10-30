"""E1 embedder tests (offline — OpenAI SDK mocked, backoff asserted via sleep).

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_e1_embedder.py -v -p no:cacheprovider
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
import tiktoken
from app.clients.embedder import (
    BaseEmbedder,
    EmbeddingUsage,
    OpenAIEmbedder,
    build_embedder_from_model,
)
from app.models.embedding_model import EmbeddingModel
from app.utils.retry import with_backoff

ENC = tiktoken.get_encoding("cl100k_base")


class FakeEmbedder(BaseEmbedder):
    """Records per-batch calls; fails the first N calls if configured."""

    def __init__(self, dimension: int = 8, batch_size: int = 4, fail_times: int = 0):
        super().__init__("fake-model", dimension, batch_size)
        self.batches: list[list[str]] = []
        self.fail_times = fail_times
        self.calls = 0

    def _embed_once(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        self.batches.append(list(texts))
        if self.calls <= self.fail_times:
            raise TimeoutError("transient")
        return [[0.0] * self.dimension for _ in texts]


# --------------------------------------------------------------------------- #
# batching + contract
# --------------------------------------------------------------------------- #


def test_embed_batch_slices_into_batches() -> None:
    emb = FakeEmbedder(batch_size=4)
    vectors = emb.embed_batch([f"t{i}" for i in range(10)])
    assert len(vectors) == 10
    assert [len(b) for b in emb.batches] == [4, 4, 2]  # 64-style tail batch


def test_embed_batch_validates_dimension() -> None:
    emb = FakeEmbedder(dimension=8)
    emb._embed_once = lambda texts: [[0.0] * 3 for _ in texts]  # wrong dim
    with pytest.raises(ValueError, match="dimension 3"):
        emb.embed_batch(["a"])


def test_embed_batch_validates_count() -> None:
    emb = FakeEmbedder(dimension=8)
    emb._embed_once = lambda texts: []  # dropped rows
    with pytest.raises(ValueError, match="0 vectors for 1"):
        emb.embed_batch(["a"])


def test_batch_size_must_be_positive() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        FakeEmbedder(batch_size=0)


def test_count_tokens_uses_tiktoken() -> None:
    emb = FakeEmbedder()
    texts = ["hello world", "embedding"]
    assert emb.count_tokens(texts) == sum(len(ENC.encode(t)) for t in texts)


# --------------------------------------------------------------------------- #
# retry / backoff (acceptance 2)
# --------------------------------------------------------------------------- #


def test_transient_failure_is_retried_until_success() -> None:
    emb = FakeEmbedder(fail_times=2)
    sleeps: list[float] = []
    vectors = emb.embed_batch(
        ["a", "b"], retry_when=lambda e: isinstance(e, TimeoutError)
    )
    assert len(vectors) == 2
    assert emb.calls == 3  # 2 failures + 1 success
    assert sleeps == []  # real with_backoff slept via time.sleep; delays asserted below


def test_backoff_delays_are_exponential_through_embed_batch() -> None:
    emb = FakeEmbedder(batch_size=4, fail_times=2)
    sleeps: list[float] = []
    real_with_backoff = with_backoff

    def recording(fn, **kw):
        kw["sleep"] = sleeps.append
        return real_with_backoff(fn, **kw)

    with patch("app.clients.embedder.with_backoff", side_effect=recording):
        emb.embed_batch(["a"], retry_when=lambda e: isinstance(e, TimeoutError))
    assert sleeps == [0.5, 1.0]  # exponential: base * 2**attempt


def test_permanent_failure_is_not_retried() -> None:
    emb = FakeEmbedder()

    def boom(texts: list[str]) -> list[list[float]]:
        emb.calls += 1
        raise KeyError("bad request")

    emb._embed_once = boom
    with pytest.raises(KeyError):
        emb.embed_batch(["a"])
    assert emb.calls == 1


def test_with_backoff_delay_sequence_and_exhaustion() -> None:
    sleeps: list[float] = []
    calls = {"n": 0}

    def always_fails() -> int:
        calls["n"] += 1
        raise TimeoutError("down")

    with pytest.raises(TimeoutError):
        with_backoff(
            always_fails, retries=3, base_delay=0.5, max_delay=8.0, sleep=sleeps.append
        )
    assert calls["n"] == 4  # retries=3 -> 4 attempts
    assert sleeps == [0.5, 1.0, 2.0]  # capped later by max_delay

    # cap: retries with big base stay <= max_delay
    sleeps2: list[float] = []
    with pytest.raises(TimeoutError):
        with_backoff(
            always_fails, retries=3, base_delay=5.0, max_delay=6.0, sleep=sleeps2.append
        )
    assert sleeps2 == [5.0, 6.0, 6.0]


def test_retryable_predicate_matches_openai_errors() -> None:
    from app.clients.embedder import _is_retryable
    from openai import APIStatusError, RateLimitError

    def http_resp(status: int) -> SimpleNamespace:
        return SimpleNamespace(
            status_code=status,
            headers={},
            request=SimpleNamespace(method="POST", url="http://x/v1/embeddings"),
        )

    rate = RateLimitError("slow down", response=http_resp(429), body=None)
    assert _is_retryable(rate) is True

    server = APIStatusError("boom", response=http_resp(500), body=None)
    assert _is_retryable(server) is True

    invalid = APIStatusError("bad", response=http_resp(400), body=None)
    assert _is_retryable(invalid) is False


# --------------------------------------------------------------------------- #
# usage stats (acceptance 3)
# --------------------------------------------------------------------------- #


def test_embed_with_usage_stats_shape() -> None:
    emb = FakeEmbedder(dimension=8, batch_size=4)
    vectors, usage = emb.embed_with_usage(["a", "b", "c"])
    assert len(vectors) == 3
    assert isinstance(usage, EmbeddingUsage)
    assert usage.batch_count == 1
    assert usage.token_count == emb.count_tokens(["a", "b", "c"])
    assert usage.model_name == "fake-model"
    output = usage.to_output()
    assert output["embedding"] == {
        "token_count": usage.token_count,
        "batch_count": 1,
        "model_name": "fake-model",
        "dimension": 8,
    }  # this dict is what stage F writes to job_steps.output


# --------------------------------------------------------------------------- #
# OpenAIEmbedder with mocked SDK
# --------------------------------------------------------------------------- #


def _sdk_response(vectors: list[list[float]], order: list[int]) -> SimpleNamespace:
    """Fake embeddings.create response with rows in arbitrary order."""
    return SimpleNamespace(
        data=[
            SimpleNamespace(index=i, embedding=v)
            for i, v in zip(order, vectors, strict=False)
        ]
    )


def test_openai_embedder_restores_input_order() -> None:
    emb = OpenAIEmbedder(
        "text-embedding-3-small", dimension=4, api_key="k", base_url="http://x"
    )
    vectors = [[1.0] * 4, [2.0] * 4, [3.0] * 4]
    with patch.object(emb._client.embeddings, "create") as create:
        create.return_value = _sdk_response(vectors, order=[2, 0, 1])
        out = emb.embed_batch(["a", "b", "c"])
    # response rows carry index 2,0,1 -> restoring input order yields v1,v2,v0
    assert out == [[2.0] * 4, [3.0] * 4, [1.0] * 4]
    create.assert_called_once_with(
        model="text-embedding-3-small", input=["a", "b", "c"]
    )


def test_build_embedder_from_model_row_uses_row_config() -> None:
    row = EmbeddingModel(
        id="m1",
        name="default",
        provider="openai",
        model_name="text-embedding-3-small",
        dimension=1536,
    )
    emb = build_embedder_from_model(row)
    assert emb.model_name == "text-embedding-3-small"
    assert emb.dimension == 1536
    assert emb.batch_size == 64

    bad = EmbeddingModel(
        id="m2", name="x", provider="huggingface", model_name="bge", dimension=768
    )
    with pytest.raises(ValueError, match="huggingface"):
        build_embedder_from_model(bad)
