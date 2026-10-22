"""Hashing helpers (C1 step 3)."""

from __future__ import annotations

import hashlib


def sha256_hex(data: bytes) -> str:
    """Lowercase hex SHA-256 — the metadata DB's content-hash format (CHAR(64))."""
    return hashlib.sha256(data).hexdigest()
