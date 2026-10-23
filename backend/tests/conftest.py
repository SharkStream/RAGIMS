"""Shared pytest configuration for the RAGIMS backend test suite.

Adds ``tests/fixtures/`` to ``sys.path`` so the sample builders in
``build_samples.py`` can be imported by tests directly
(``import build_samples``) while staying runnable as a standalone script.
"""

from __future__ import annotations

import sys
from pathlib import Path

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
if str(_FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(_FIXTURES_DIR))
