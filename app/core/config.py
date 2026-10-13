"""Application configuration loaded from environment variables / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings.

    All values are sourced from environment variables (optionally via a
    local .env file). Nothing here has a secret-bearing default: credentials
    and connection strings must be supplied explicitly.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "skinai-ai-service"
    app_env: str = Field(default="development", description="development|test|staging|production")
    log_level: str = "INFO"

    api_v1_prefix: str = "/api/v1"

    database_url: str = Field(
        ...,
        description=(
            "Async SQLAlchemy connection string, e.g. "
            "postgresql+asyncpg://user:password@host:5432/dbname"
        ),
    )

    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout_seconds: int = 30

    # Dimensionality of stored embedding vectors. 1536 is the default because
    # it matches OpenAI's text-embedding-3-small, a common off-the-shelf
    # choice. No embedding provider is wired up yet (see app/services/embedding.py);
    # this value only defines the pgvector column width. Changing it after
    # data has been written requires a new Alembic migration that rewrites
    # the vector columns, since pgvector columns are declared with a fixed
    # dimension.
    embedding_dimension: int = Field(default=1536, ge=1)

    # JSON array of allowed CORS origins, e.g. ["http://localhost:3000"].
    # Left empty by default, meaning no CORS middleware is installed.
    cors_origins: list[str] = Field(default_factory=list)

    default_page_size: int = 20
    max_page_size: int = 100

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings instance (cached after first call)."""

    return Settings()
