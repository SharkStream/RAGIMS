"""Application entrypoint.

Logging is bootstrapped here so every subsequent import is covered. The FastAPI app
instance, CORS, routers and exception handlers are assembled in A3 (FastAPI 骨架).
"""

from app.core.config import settings
from app.core.logging import setup_logging

setup_logging(level=settings.app.log_level)

# A3 will create the FastAPI app here and call setup_logging() at startup.
