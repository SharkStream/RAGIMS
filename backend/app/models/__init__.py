"""SQLAlchemy models.

Importing this package registers every MVP table on ``Base.metadata`` so
Alembic autogenerate can discover all tables (B2 step 3). Stage-3/4 tables
(audit_logs K1; quality_checks + evaluation_runs L1) register here too.
"""

from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.chunk import Chunk
from app.models.datasource import Datasource
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.embedding_model import EmbeddingModel
from app.models.evaluation_run import EvaluationRun
from app.models.ingestion_job import IngestionJob
from app.models.job_step import JobStep
from app.models.quality_check import QualityCheck
from app.models.tenant import Tenant
from app.models.user import User

__all__ = [
    "AuditLog",
    "Base",
    "Chunk",
    "Datasource",
    "Document",
    "DocumentVersion",
    "EmbeddingModel",
    "EvaluationRun",
    "IngestionJob",
    "JobStep",
    "QualityCheck",
    "Tenant",
    "User",
]
