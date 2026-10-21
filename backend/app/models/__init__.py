"""SQLAlchemy models.

Importing this package registers every MVP table on ``Base.metadata`` so
Alembic autogenerate can discover all 9 tables (B2 step 3). Deferred tables
(see ``docs/db-schema.md`` §7) deliberately have no model here.
"""

from app.models.base import Base
from app.models.chunk import Chunk
from app.models.datasource import Datasource
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.embedding_model import EmbeddingModel
from app.models.ingestion_job import IngestionJob
from app.models.job_step import JobStep
from app.models.tenant import Tenant
from app.models.user import User

__all__ = [
    "Base",
    "Chunk",
    "Datasource",
    "Document",
    "DocumentVersion",
    "EmbeddingModel",
    "IngestionJob",
    "JobStep",
    "Tenant",
    "User",
]
