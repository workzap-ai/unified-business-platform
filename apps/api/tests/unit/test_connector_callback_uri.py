"""The Google/Shopify return address for Owner OS comes from the operator's setting,
not from the first allowed origin (which can be a Vercel preview URL)."""

from app.core.config import Settings
from app.modules.pi_saas.connectors import callback_uri


def _settings(**values) -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://x:x@127.0.0.1:1/x",
        redis_url="redis://127.0.0.1:1/0",
        **values,
    )


def test_owner_os_return_address_uses_the_operator_setting_host_only():
    settings = _settings(
        cors_origins=["https://preview-abc123.vercel.app"],
        oauth_redirect_base_url="https://owner.example.com/api/v1/pi-app/pi/connectors/x/callback",
        pi_app_public_url="https://pi.example.com",
    )
    assert callback_uri(settings, "google_calendar", "web") == (
        "https://owner.example.com/api/v1/pi/connectors/google_calendar/callback"
    )
    assert callback_uri(settings, "shopify", "pi") == (
        "https://pi.example.com/api/v1/pi-app/pi/connectors/shopify/callback"
    )


def test_without_the_setting_the_first_allowed_origin_is_used():
    settings = _settings(cors_origins=["https://owner.example.com/"])
    assert callback_uri(settings, "google_calendar", "web") == (
        "https://owner.example.com/api/v1/pi/connectors/google_calendar/callback"
    )
