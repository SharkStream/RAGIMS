"""Sparse (lexical) vectors for hybrid retrieval (N2).

Computes a BM25-flavored sparse vector per text: tokens are mapped into a
fixed index space via a **stable** hash (zlib.crc32 — never Python's random
``hash``), values are term frequencies normalized by the chunk max.

Tokenizer: lowercase ASCII/number words + CJK unigrams and bigrams (Chinese
has no whitespace; bigrams carry the lexical signal). No external
dependencies — good enough for lexical recall until/if a real SPLADE lands.
"""

from __future__ import annotations

import re
import zlib

from qdrant_client.http import models as qmodels

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")

_DIM_DEFAULT = 65536


def tokenize(text: str) -> list[str]:
    """Lowercase words + CJK unigrams/bigrams (order preserved)."""
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text.lower()):
        tokens.append(raw)
        if re.fullmatch(r"[\u4e00-\u9fff]+", raw):
            # CJK runs: unigram + bigram for richer lexical matches
            tokens.extend(raw)
            tokens.extend(raw[i : i + 2] for i in range(len(raw) - 1))
    return tokens


def _index(token: str, dim: int) -> int:
    return zlib.crc32(token.encode("utf-8")) % dim


def sparse_vector(text: str, dim: int | None = None) -> qmodels.SparseVector:
    """Hashed-tf sparse vector for ``text`` (stable across processes)."""
    dim = dim or _DIM_DEFAULT
    counts: dict[int, float] = {}
    for token in tokenize(text):
        idx = _index(token, dim)
        counts[idx] = counts.get(idx, 0.0) + 1.0
    if not counts:
        return qmodels.SparseVector(indices=[], values=[])
    max_tf = max(counts.values())
    indices = sorted(counts)
    values = [round(counts[i] / max_tf, 4) for i in indices]
    return qmodels.SparseVector(indices=indices, values=values)
