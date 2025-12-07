"""
Application configuration using Pydantic Settings.

All configuration is loaded from environment variables with sensible defaults.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Application Settings
    # -------------------------------------------------------------------------
    app_name: str = Field(default="Lexia API", description="Application name")
    app_version: str = Field(default="1.0.0", description="API version")
    app_env: Literal["development", "staging", "production"] = Field(
        default="production", description="Environment"
    )
    app_debug: bool = Field(default=False, description="Debug mode")
    app_host: str = Field(default="0.0.0.0", description="API host")
    app_port: int = Field(default=8000, description="API port")
    app_workers: int = Field(default=4, description="Number of workers")

    # -------------------------------------------------------------------------
    # Security
    # -------------------------------------------------------------------------
    api_secret_key: str = Field(
        ..., description="Secret key for JWT and encryption"
    )
    api_key_salt: str = Field(
        ..., description="Salt for API key hashing"
    )
    api_key_prefix: str = Field(
        default="lx_", description="Prefix for generated API keys"
    )
    access_token_expire_minutes: int = Field(
        default=30, description="Access token expiration in minutes"
    )

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    database_url: PostgresDsn = Field(
        ..., description="PostgreSQL connection URL"
    )
    database_pool_size: int = Field(default=10, description="Connection pool size")
    database_max_overflow: int = Field(default=20, description="Max overflow connections")
    database_pool_timeout: int = Field(default=30, description="Pool timeout in seconds")

    # -------------------------------------------------------------------------
    # Redis
    # -------------------------------------------------------------------------
    redis_url: RedisDsn = Field(
        default="redis://localhost:6379/0", description="Redis connection URL"
    )
    redis_max_connections: int = Field(default=20, description="Max Redis connections")

    # -------------------------------------------------------------------------
    # Celery
    # -------------------------------------------------------------------------
    celery_broker_url: str = Field(
        default="redis://localhost:6379/0", description="Celery broker URL"
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/0", description="Celery result backend"
    )
    celery_task_default_queue: str = Field(
        default="default", description="Default task queue"
    )

    # -------------------------------------------------------------------------
    # Internal Services
    # -------------------------------------------------------------------------
    llm_service_url: str = Field(
        default="http://localhost:8001", description="vLLM service URL"
    )
    stt_service_url: str = Field(
        default="http://localhost:8002", description="STT service URL"
    )

    # -------------------------------------------------------------------------
    # Mock Mode (for development without GPU)
    # -------------------------------------------------------------------------
    use_mock_llm: bool = Field(
        default=False, description="Use mock LLM backend"
    )
    use_mock_stt: bool = Field(
        default=False, description="Use mock STT backend"
    )
    use_mock_diarization: bool = Field(
        default=False, description="Use mock diarization backend"
    )

    # -------------------------------------------------------------------------
    # Storage
    # -------------------------------------------------------------------------
    storage_backend: Literal["local", "s3"] = Field(
        default="local", description="Storage backend type"
    )
    local_storage_path: str = Field(
        default="/app/data", description="Local storage path"
    )

    # S3/MinIO settings
    s3_endpoint_url: str | None = Field(
        default=None, description="S3 endpoint URL (for MinIO)"
    )
    s3_access_key: str | None = Field(default=None, description="S3 access key")
    s3_secret_key: str | None = Field(default=None, description="S3 secret key")
    s3_bucket_name: str = Field(default="lexia-audio", description="S3 bucket name")
    s3_region: str = Field(default="eu-west-1", description="S3 region")

    # -------------------------------------------------------------------------
    # LLM Configuration
    # -------------------------------------------------------------------------
    llm_default_model: str = Field(
        default="general7Bv2",
        description="Default LLM model identifier",
    )
    llm_max_tokens: int = Field(default=4096, description="Max tokens for generation")
    llm_default_temperature: float = Field(
        default=0.7, description="Default temperature"
    )

    # -------------------------------------------------------------------------
    # STT Configuration
    # -------------------------------------------------------------------------
    stt_default_language: str = Field(default="fr", description="Default STT language")
    stt_max_audio_duration: int = Field(
        default=7200, description="Max audio duration in seconds (2 hours)"
    )
    stt_supported_formats: list[str] = Field(
        default=["wav", "mp3", "m4a", "flac", "ogg", "webm"],
        description="Supported audio formats",
    )
    stt_max_file_size_mb: int = Field(
        default=500, description="Max file size in MB"
    )

    # -------------------------------------------------------------------------
    # Rate Limiting
    # -------------------------------------------------------------------------
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_requests_per_minute: int = Field(
        default=60, description="Requests per minute per API key"
    )
    rate_limit_burst: int = Field(default=10, description="Burst allowance")

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Log level"
    )
    log_format: Literal["json", "console"] = Field(
        default="json", description="Log format"
    )

    # -------------------------------------------------------------------------
    # CORS
    # -------------------------------------------------------------------------
    cors_origins: list[str] = Field(
        default=["*"], description="Allowed CORS origins"
    )
    cors_allow_credentials: bool = Field(default=True)
    cors_allow_methods: list[str] = Field(default=["*"])
    cors_allow_headers: list[str] = Field(default=["*"])

    # -------------------------------------------------------------------------
    # Validators
    # -------------------------------------------------------------------------
    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Ensure database URL uses asyncpg driver."""
        if v and "postgresql://" in v and "asyncpg" not in v:
            v = v.replace("postgresql://", "postgresql+asyncpg://")
        return v

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
