"""Centralized configuration via ``pydantic-settings``.

Settings are read from environment variables and/or the ``backend/.env`` file
(resolved relative to this file, not the current working directory). Nested groups
are separated by ``__`` (e.g. ``MYSQL__HOST``, ``OPENAI__API_KEY``, ``APP__LOG_LEVEL``).
A missing required value (currently the OpenAI API key) raises a clear
``pydantic.ValidationError``.

Usage::

    from app.core.config import settings

    settings.mysql.dsn       # "mysql+pymysql://..."
    settings.qdrant.url      # "http://localhost:6333"
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ directory (this file lives at backend/app/core/config.py). The .env file
# is anchored here so it is found regardless of the process's current working dir.
_BASE_DIR = Path(__file__).resolve().parents[2]


class AppSettings(BaseModel):
    """Application-level settings."""

    name: str = "RAGIMS"
    version: str = "0.1.0"
    env: str = "development"
    debug: bool = True
    log_level: str = "INFO"
    api_prefix: str = "/api"
    # JSON array in env, e.g. APP__CORS_ORIGINS='["http://localhost:5173"]'
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )


class MySQLSettings(BaseModel):
    """MySQL 8 metadata database (utf8mb4)."""

    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = "ragims"
    database: str = "ragims"
    charset: str = "utf8mb4"
    pool_size: int = 10
    pool_recycle: int = 3600
    echo: bool = False

    @property
    def dsn(self) -> str:
        """SQLAlchemy async/sync DSN (pymysql driver)."""
        # URL-encode credentials so passwords containing ``@``, ``:``, ``/`` etc.
        # are not mistaken for URL delimiters.
        return (
            f"mysql+pymysql://{quote_plus(self.user)}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}/{self.database}?charset={self.charset}"
        )


class RedisSettings(BaseModel):
    """Redis for Celery broker/result backend."""

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None

    @property
    def url(self) -> str:
        auth = f":{quote_plus(self.password)}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class QdrantSettings(BaseModel):
    """Qdrant vector database."""

    host: str = "localhost"
    port: int = 6333
    api_key: str | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


class MinIOSettings(BaseModel):
    """MinIO object storage (raw docs + parsed text)."""

    endpoint: str = "localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    secure: bool = False
    bucket_raw: str = "raw-docs"
    bucket_parsed: str = "parsed-text"


class OpenAISettings(BaseModel):
    """OpenAI embedding client."""

    api_key: str = Field(
        default="", description="OpenAI API key (env: OPENAI__API_KEY)"
    )
    base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536
    timeout: float = 60.0


class Settings(BaseSettings):
    """Top-level settings singleton."""

    model_config = SettingsConfigDict(
        env_file=_BASE_DIR / ".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    app: AppSettings = Field(default_factory=AppSettings)
    mysql: MySQLSettings = Field(default_factory=MySQLSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    minio: MinIOSettings = Field(default_factory=MinIOSettings)
    openai: OpenAISettings = Field(default_factory=OpenAISettings)

    @model_validator(mode="after")
    def _require_openai_api_key(self) -> Settings:
        """Fail fast with a clear message when the OpenAI API key is missing."""
        if not self.openai.api_key.strip():
            raise ValueError(
                "OPENAI__API_KEY is required — set it in the environment or .env "
                "(see backend/.env.example)"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings instance."""
    return Settings()


settings = get_settings()
