"""Backward-compat shim (F2 moved the task to ``app.workers.pipeline``).

C1's upload endpoint imports ``ingest_document`` from this module; keep the
re-export so the API contract stays stable. New code should import from
``app.workers.pipeline`` directly.
"""

from app.workers.pipeline import ingest_document  # noqa: F401
