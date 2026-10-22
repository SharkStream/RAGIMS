"""Fixed-length (token) chunker (D4 step 2).

Splits block-by-block (never across blocks) so a chunk's ``page`` is exact:
each block's tokens are windowed with ``chunk_size``/``overlap`` (stride =
``chunk_size - overlap``).

Window-length invariant: every full window is exactly ``chunk_size`` tokens,
and the last window of a multi-window block is ``len(tokens) - start`` where
the previous window ended past ``start + overlap`` — so chunks cut from a
long block carry more than ``overlap`` tokens and at most ``chunk_size``.
A block shorter than one window is emitted whole (its text may be small —
headings must not be dropped).
"""

from __future__ import annotations

import tiktoken

from app.chunkers.base import DEFAULT_CHUNKER_CONFIG, BaseChunker, Chunk, ChunkerConfig
from app.parsers.base import Block, ParsedDocument
from app.utils.hashing import sha256_hex


class FixedTokenChunker(BaseChunker):
    """Token-window chunker (tiktoken, default cl100k_base)."""

    def chunk(
        self, parsed: ParsedDocument, config: ChunkerConfig | None = None
    ) -> list[Chunk]:
        cfg = config or DEFAULT_CHUNKER_CONFIG
        encoding = tiktoken.get_encoding(cfg.encoding_name)
        step = cfg.chunk_size - cfg.overlap

        chunks: list[Chunk] = []
        for block in parsed.blocks:
            tokens = encoding.encode(block.text)
            start = 0
            while start < len(tokens):
                is_last = start + cfg.chunk_size >= len(tokens)
                window = (
                    tokens[start:]
                    if is_last
                    else tokens[start : start + cfg.chunk_size]
                )
                chunks.append(self._make_chunk(chunks, block, window, encoding, cfg))
                if is_last:
                    break
                start += step
        return chunks

    def _make_chunk(
        self,
        existing: list[Chunk],
        block: Block,
        window: list[int],
        encoding: tiktoken.Encoding,
        cfg: ChunkerConfig,
    ) -> Chunk:
        text = encoding.decode(window)
        return Chunk(
            chunk_index=len(existing),
            text=text,
            token_count=len(window),
            page=block.page,
            metadata={"block_type": block.block_type},
            chunk_hash=sha256_hex(text.encode("utf-8")),
        )
