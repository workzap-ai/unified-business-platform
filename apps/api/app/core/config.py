from decimal import Decimal
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
    semantic_search_enabled: bool = False
    embedding_dimensions: int = Field(default=1536, ge=2, le=4096)
    # Gateway resilience, defaults and budgets (see docs/AI_GATEWAY.md).
    # Registry defaults fill aliases missing from *_models. None = on, except app_env=test
    # (so test settings that inherit real keys never reach providers via default models).
    ai_use_default_models: bool | None = None
    groq_structured_output: Literal["json_schema", "json_object"] = "json_object"
    llm_circuit_failure_threshold: int = Field(default=3, ge=1, le=100)
    llm_circuit_cooldown_seconds: float = Field(default=30, gt=0, le=3600)
    llm_retry_after_max_seconds: float = Field(default=2, ge=0, le=30)
    # "provider:model" -> {"input": USD per 1M tokens, "output": USD per 1M tokens}
    ai_model_prices: dict[str, dict[str, Decimal]] = {}
    ai_tenant_daily_token_limit: int | None = Field(default=None, ge=1)
    ai_tenant_daily_cost_limit: Decimal | None = Field(default=None, gt=0)

    # WhatsApp Cloud API (platform-level app credentials; per-number tokens are encrypted).
    whatsapp_app_secret: SecretStr | None = None
    whatsapp_verify_token: SecretStr | None = None
    whatsapp_graph_base_url: str = "https://graph.facebook.com"
    whatsapp_graph_version: str = "v21.0"
    media_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    knowledge_upload_max_bytes: int = Field(default=1024 * 1024, ge=1024, le=10 * 1024 * 1024)

    # --- Integrations (owned by app/integrations; documented in docs/INTEGRATIONS.md) ---
    # When true, production startup requires SECRETS_ENCRYPTION_KEY (credentials fail closed).
    integrations_enabled: bool = True
    # Older Fernet keys that may still decrypt stored credentials (comma-separated).
    # SECRETS_ENCRYPTION_KEY may itself be "new,old"; the first key always encrypts.
    secrets_encryption_previous_keys: SecretStr | None = None
    # Public HTTPS origin of the API as providers reach it (inbound webhook URLs).
    integrations_public_base_url: str | None = None
    # Exact OAuth redirect URI registered with providers; callback path is fixed.
    oauth_redirect_base_url: str | None = None
    oauth_state_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    # Outbound HTTP (all provider/webhook calls go through app.integrations.http).
    outbound_connect_timeout_seconds: float = Field(default=5, gt=0, le=30)
    outbound_read_timeout_seconds: float = Field(default=15, gt=0, le=120)
    outbound_total_timeout_seconds: float = Field(default=30, gt=0, le=300)
    outbound_max_response_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=50 * 1024**2)
    outbound_verify_tls: bool = True
    # Hosts allowed over plain http (development/test only; rejected in production).
    outbound_http_allowlist: list[str] = []
    # Extra destination ports allowed besides 443 (and 80 for allowlisted http hosts).
    outbound_allowed_ports: list[int] = []
    # Inbound webhooks
    webhook_max_body_bytes: int = Field(default=1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    webhook_replay_window_seconds: int = Field(default=300, ge=30, le=3600)
    webhook_payload_retention_days: int = Field(default=30, ge=1, le=365)
    webhook_stored_payload_max_bytes: int = Field(default=64 * 1024, ge=1024, le=1024 * 1024)
    # Outbound deliveries / outbox
    delivery_max_attempts: int = Field(default=8, ge=1, le=20)
    delivery_backoff_base_seconds: float = Field(default=30, gt=0, le=3600)
    delivery_backoff_max_seconds: float = Field(default=6 * 3600, gt=0, le=86400)
    outbox_batch_size: int = Field(default=100, ge=1, le=1000)
    # Circuit breaker and provider rate limits
    circuit_failure_threshold: int = Field(default=5, ge=1, le=100)
    circuit_cooldown_seconds: int = Field(default=60, ge=5, le=3600)
    integration_rate_limit_per_minute: int = Field(default=120, ge=1, le=100000)
    integration_rate_limit_fallback_per_minute: int = Field(default=20, ge=1, le=10000)
    # Platform-level email (used when a workspace has no connected email integration)
    platform_smtp_host: str | None = None
    platform_smtp_port: int = Field(default=587, ge=1, le=65535)
    platform_smtp_username: str | None = None
    platform_smtp_password: SecretStr | None = None
    platform_smtp_from: str | None = None
    platform_smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    platform_smtp_timeout_seconds: float = Field(default=10, gt=0, le=60)
    # Object storage defaults
    storage_default_region: str = "us-east-1"
    storage_signed_url_ttl_seconds: int = Field(default=900, ge=60, le=7 * 86400)
    storage_max_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1024, le=5 * 1024**3)
    # Stripe API base (override only for tests/mocks)
    stripe_api_base_url: str = "https://api.stripe.com"
    api_key_max_per_environment: int = Field(default=50, ge=1, le=1000)

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
            # Integrations: fail closed on credential storage and plaintext egress.
            if self.integrations_enabled and not self.secrets_encryption_key:
                raise ValueError("Production integrations require SECRETS_ENCRYPTION_KEY")
            if self.outbound_http_allowlist:
                raise ValueError("Plain-http outbound allowlist is not allowed in production")
            if not self.outbound_verify_tls:
                raise ValueError("Production requires outbound TLS verification")
            for base in (self.integrations_public_base_url, self.oauth_redirect_base_url):
                if base and not base.startswith("https://"):
                    raise ValueError("Production integration URLs require HTTPS")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
