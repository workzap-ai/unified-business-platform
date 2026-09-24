from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ProviderName = Literal["openai", "gemini", "groq", ""]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["development", "test", "production"] = "development"
    database_url: SecretStr
    redis_url: SecretStr
    cors_origins: list[str] = ["http://localhost:3000"]
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "api"]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)
    dependency_timeout_seconds: float = Field(default=3, gt=0, le=30)

    # Authentication and sessions
    session_cookie_name: str = "platform_session"
    csrf_cookie_name: str = "platform_csrf"
    session_ttl_hours: int = Field(default=168, ge=1, le=720)
    cookie_secure: bool | None = None  # defaults to True in production
    allow_registration: bool = True
    login_max_failures: int = Field(default=5, ge=3, le=20)
    login_lockout_minutes: int = Field(default=15, ge=1, le=1440)
    rate_limit_login_per_minute: int = Field(default=10, ge=1, le=1000)
    trusted_proxy_hops: int = Field(default=0, ge=0, le=3)

    # Background jobs: 'inline' runs jobs in-process and is only for development/tests.
    job_queue_mode: Literal["arq", "inline"] = "arq"
    job_queue_name: str = "arq:queue"

    # Secrets at rest (Fernet key); required to store per-connection provider tokens.
    secrets_encryption_key: SecretStr | None = None

    # AI gateway. Provider order and model aliases are configuration, never code.
    primary_llm_provider: ProviderName = "openai"
    fallback_llm_provider: ProviderName = "gemini"
    secondary_fallback_llm_provider: ProviderName = "groq"
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    openai_models: dict[str, str] = {}
    gemini_models: dict[str, str] = {}
    groq_models: dict[str, str] = {}
    openai_base_url: str = "https://api.openai.com/v1"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    llm_timeout_seconds: float = Field(default=20, gt=0, le=120)
    llm_max_retries: int = Field(default=1, ge=0, le=3)

    # WhatsApp Cloud API (platform-level app credentials; per-number tokens are encrypted).
    whatsapp_app_secret: SecretStr | None = None
    whatsapp_verify_token: SecretStr | None = None
    whatsapp_graph_base_url: str = "https://graph.facebook.com"
    whatsapp_graph_version: str = "v21.0"
    media_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    knowledge_upload_max_bytes: int = Field(default=1024 * 1024, ge=1024, le=10 * 1024 * 1024)

    @property
    def secure_cookies(self) -> bool:
        return self.app_env == "production" if self.cookie_secure is None else self.cookie_secure

    def provider_order(self) -> list[str]:
        order: list[str] = []
        for name in (
            self.primary_llm_provider,
            self.fallback_llm_provider,
            self.secondary_fallback_llm_provider,
        ):
            if name and name not in order:
                order.append(name)
        return order

    @model_validator(mode="after")
    def validate_connections(self) -> "Settings":
        try:
            db = make_url(self.database_url.get_secret_value())
            cache = make_url(self.redis_url.get_secret_value())
        except Exception:
            raise ValueError("Invalid connection configuration") from None
        if db.drivername != "postgresql+asyncpg" or cache.drivername not in {"redis", "rediss"}:
            raise ValueError("Use PostgreSQL asyncpg and Redis connection URLs")
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            raise ValueError("Explicit allowed hosts are required")
        if any(not origin.startswith(("http://", "https://")) for origin in self.cors_origins):
            raise ValueError("Explicit HTTP origins are required")
        if self.app_env == "production":
            if any(not origin.startswith("https://") for origin in self.cors_origins):
                raise ValueError("Production browser origins require HTTPS")
            if self.job_queue_mode != "arq":
                raise ValueError("Production requires the ARQ job queue")
            if self.cookie_secure is False:
                raise ValueError("Production requires secure cookies")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
