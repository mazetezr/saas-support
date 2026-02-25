"""Configuration management with pydantic-settings validation.

Loads settings from .env file and validates at import time (fail-fast pattern).
Missing required fields will raise ValidationError immediately on module import.
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )

    # Required
    telegram_bot_token: str = Field(..., description="Telegram bot API token")
    database_url: str = Field(..., description="PostgreSQL connection string")
    encryption_key: str = Field(..., description="Fernet key for API key encryption")

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    arq_redis_url: str = "redis://localhost:6379/1"

    # LLM defaults (per-tenant keys stored in DB)
    openrouter_model: str = "openai/gpt-4o-mini"

    # Superadmin
    superadmin_ids: list[int] = Field(default_factory=list)

    @field_validator('superadmin_ids', mode='before')
    @classmethod
    def parse_superadmin_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(',') if x.strip()]
        if isinstance(v, int):
            return [v]
        return v

    # Cryptocloud payments
    cryptocloud_api_key: str = ""
    cryptocloud_shop_id: str = ""
    cryptocloud_secret: str = ""

    # Webhook server
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080

    # Bot behavior
    relevance_threshold: float = 0.72
    group_relevance_threshold: float = 0.78
    max_context_chunks: int = 5
    compact_after_messages: int = 50

    # Document processing
    chunk_size: int = 2500
    chunk_overlap: int = 300

    # Embedding
    embedding_model: str = "intfloat/multilingual-e5-small"

    # Logging
    log_level: str = "INFO"


settings = Settings()
