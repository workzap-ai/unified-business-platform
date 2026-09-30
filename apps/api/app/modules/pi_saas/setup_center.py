"""Setup Center: every tool's state in one place, for the Pi app and Owner OS.

Each item says plainly whether the tool is ready, what is missing, and where to fix it.
Nothing is estimated: states come from the stored connections and the server's own
configuration. "Test all" runs the existing health checks (the same ones behind each
tool's own Test button) and reports each result.

The operator gets a platform checklist on top: the server settings that must be in
place before businesses can connect anything.
"""

from typing import Any, Literal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations.email import EMAIL_KEYS
from app.modules.integrations.models import IntegrationConnection
from app.modules.pi.models import WhatsAppConnection
from app.modules.pi_saas import connectors
from app.modules.pi_saas.models import PiProviderConnection
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

App = Literal["pi", "web"]
USABLE = ("connected", "degraded")

LINKS: dict[str, dict[str, str]] = {
    "whatsapp": {"pi": "/settings/whatsapp", "web": "/pi/whatsapp"},
    "email": {"pi": "", "web": "/settings/integrations"},
    "stripe": {"pi": "/settings/payments", "web": "/settings/integrations"},
    "google_calendar": {"pi": "/my-pi/tools", "web": "/pi/setup"},
    "shopify": {"pi": "/my-pi/tools", "web": "/pi/setup"},
    "storage": {"pi": "", "web": "/settings/integrations"},
    "ai": {"pi": "", "web": ""},
}


def ai_ready(settings: Settings) -> list[str]:
    return [
        name
        for name in settings.provider_order()
        if getattr(settings, f"{name}_api_key", None) is not None
    ]


async def _integration(
    session: AsyncSession, scope: WorkspaceScope, keys: tuple[str, ...]
) -> IntegrationConnection | None:
    row: IntegrationConnection | None = await session.scalar(
        WorkspaceRepository(session, IntegrationConnection, scope)
        .select()
        .where(IntegrationConnection.integration_key.in_(keys))
        .order_by((IntegrationConnection.status.in_(USABLE)).desc())
        .limit(1)
    )
    return row


def _item(
    key: str,
    name: str,
    state: str,
    detail: str,
    app: App,
    *,
    required: bool = False,
    connection_id: Any = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "name": name,
        # connected | not_connected | needs_attention | platform (managed by the Pi team)
        "state": state,
        "detail": detail,
        "required": required,
        "href": LINKS.get(key, {}).get(app) or None,
        "connection_id": connection_id,
    }


async def status(
    session: AsyncSession, settings: Settings, scope: WorkspaceScope, app: App
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    # WhatsApp (the one thing Pi can't work without)
    number: WhatsAppConnection | None = await session.scalar(
        WorkspaceRepository(session, WhatsAppConnection, scope)
        .select()
        .order_by((WhatsAppConnection.status == "active").desc())
        .limit(1)
    )
    provider: PiProviderConnection | None = await session.scalar(
        WorkspaceRepository(session, PiProviderConnection, scope).select().limit(1)
    )
    if number is not None and number.status == "active":
        state = (
            "needs_attention" if provider and provider.status == "action_required" else "connected"
        )
        via = "Kapso" if number.provider == "kapso" else "Meta"
        detail = f"{number.display_phone_number} (via {via})"
        if state == "needs_attention" and provider is not None:
            detail += f": {provider.last_error_code or 'check the number'}"
    elif provider is not None and provider.status == "setup_pending":
        state, detail = "not_connected", "Setup started; finish it on the WhatsApp page"
    else:
        state, detail = "not_connected", "Choose a number or connect your own"
    items.append(_item("whatsapp", "WhatsApp", state, detail, app, required=True))

    # AI (platform-managed)
    providers = ai_ready(settings)
    items.append(
        _item(
            "ai",
            "AI replies",
            "platform" if providers else "needs_attention",
            "Provided by the Pi team" if providers else "The Pi team hasn't set up AI yet",
            app,
            required=True,
        )
    )

    # Email
    email = await _integration(session, scope, EMAIL_KEYS)
    if email is not None and email.status in USABLE:
        items.append(
            _item("email", "Email", "connected", email.display_name, app, connection_id=email.id)
        )
    elif email is not None:
        items.append(
            _item(
                "email",
                "Email",
                "needs_attention",
                email.last_error or email.status,
                app,
                connection_id=email.id,
            )
        )
    elif settings.platform_smtp_host:
        items.append(_item("email", "Email", "platform", "Sent from the Pi team's address", app))
    else:
        items.append(
            _item("email", "Email", "not_connected", "Booking and summary emails are off", app)
        )

    # Card payments (the business's own Stripe)
    stripe = await _integration(session, scope, ("stripe",))
    items.append(
        _item(
            "stripe",
            "Card payments (Stripe)",
            "connected"
            if stripe is not None and stripe.status in USABLE
            else "needs_attention"
            if stripe is not None
            else "not_connected",
            "Your own Stripe account" if stripe is not None else "Optional",
            app,
            connection_id=stripe.id if stripe is not None else None,
        )
    )

    # Google Calendar and Shopify (business-owned OAuth)
    for view in await connectors.status(session, settings, scope):
        state = {
            "connected": "connected",
            "connecting": "not_connected",
            "not_connected": "not_connected",
        }.get(view["state"], "needs_attention")
        detail = view["detail"] or (
            "Optional" if view["available"] else "Not offered on this server yet"
        )
        items.append(_item(view["key"], view["name"], state, detail, app))

    if app == "web":
        storage = await _integration(session, scope, ("s3",))
        items.append(
            _item(
                "storage",
                "File storage (S3)",
                "connected"
                if storage is not None and storage.status in USABLE
                else "not_connected",
                "Optional",
                app,
                connection_id=storage.id if storage is not None else None,
            )
        )
    return items


async def test_all(
    session: AsyncSession,
    settings: Settings,
    http: httpx.AsyncClient,
    scope: WorkspaceScope,
    runtime: Any,
) -> list[dict[str, Any]]:
    """Run every available health check and report each result."""
    from app.modules.integrations.service import IntegrationService
    from app.modules.pi_saas.connections import check_health, workspace_target

    results: list[dict[str, Any]] = []
    number = await session.scalar(
        WorkspaceRepository(session, WhatsAppConnection, scope)
        .select()
        .where(WhatsAppConnection.status == "active")
        .limit(1)
    )
    if number is not None and number.provider == "kapso":
        try:
            target = await workspace_target(session, scope.tenant_id, scope.environment_id)
            row = await check_health(session, settings, http, target, target.environment)  # type: ignore[arg-type]
            ok = str((row.health or {}).get("status", "")).lower() in {"healthy", "ok", "connected"}
            results.append(
                {
                    "key": "whatsapp",
                    "ok": ok,
                    "detail": str((row.health or {}).get("status", "unknown")),
                }
            )
        except Exception as exc:  # noqa: BLE001 - reported, never raised
            results.append(
                {"key": "whatsapp", "ok": False, "detail": getattr(exc, "code", "failed")}
            )
    elif number is not None:
        results.append({"key": "whatsapp", "ok": True, "detail": "Meta number active"})
    service = IntegrationService(session, scope, runtime)
    rows = await session.scalars(
        WorkspaceRepository(session, IntegrationConnection, scope)
        .select()
        .where(IntegrationConnection.status.in_(USABLE))
    )
    for connection in list(rows)[:20]:
        try:
            result = await service.test(connection.id)
            results.append(
                {"key": connection.integration_key, "ok": bool(result.ok), "detail": result.message}
            )
        except Exception as exc:  # noqa: BLE001 - one failing tool never hides the rest
            results.append(
                {
                    "key": connection.integration_key,
                    "ok": False,
                    "detail": getattr(exc, "code", "failed"),
                }
            )
    return results


def platform_checklist(settings: Settings) -> list[dict[str, Any]]:
    """Server settings the Pi team must have in place (operator only)."""
    from app.modules.pi_saas.connections import webhook_url

    def check(key: str, label: str, ok: bool, fix: str) -> dict[str, Any]:
        return {"key": key, "label": label, "ok": ok, "fix": "" if ok else fix}

    return [
        check(
            "kapso_api_key",
            "Kapso project key",
            settings.kapso_api_key is not None,
            "Set KAPSO_API_KEY",
        ),
        check(
            "kapso_webhook_secret",
            "Kapso webhook secret",
            settings.kapso_webhook_secret is not None,
            "Set KAPSO_WEBHOOK_SECRET",
        ),
        check(
            "public_api_url",
            "Public HTTPS API address (for webhooks)",
            bool(webhook_url(settings)),
            "Set INTEGRATIONS_PUBLIC_BASE_URL to the API's https:// address",
        ),
        check(
            "billing_mode", f"WhatsApp fees billed as {settings.kapso_meta_billing_mode}", True, ""
        ),
        check(
            "encryption_key",
            "Secrets encryption key",
            settings.secrets_encryption_key is not None,
            "Set SECRETS_ENCRYPTION_KEY",
        ),
        check(
            "pi_app_url",
            "Pi app address",
            bool(settings.pi_app_public_url),
            "Set PI_APP_PUBLIC_URL",
        ),
        check(
            "ai",
            "AI provider key",
            bool(ai_ready(settings)),
            "Set an AI provider key (OPENAI/GEMINI/GROQ)",
        ),
        check(
            "pi_billing",
            "Pi subscription billing (Stripe)",
            settings.pi_billing_stripe_secret_key is not None
            and settings.pi_billing_stripe_webhook_secret is not None,
            "Set PI_BILLING_STRIPE_SECRET_KEY and PI_BILLING_STRIPE_WEBHOOK_SECRET",
        ),
        check(
            "google",
            "Google Calendar app",
            connectors.server_ready(settings, "google_calendar"),
            "Set GOOGLE_OAUTH_CLIENT_ID/SECRET and register both redirect URIs",
        ),
        check(
            "shopify",
            "Shopify app",
            connectors.server_ready(settings, "shopify"),
            "Set SHOPIFY_CLIENT_ID/SECRET",
        ),
        check(
            "email",
            "Platform email (fallback)",
            bool(settings.platform_smtp_host),
            "Set PLATFORM_SMTP_* or let businesses connect their own",
        ),
        check(
            "meta_webhook",
            "Meta app secret (only for own Meta numbers)",
            settings.whatsapp_app_secret is not None,
            "Set WHATSAPP_APP_SECRET if businesses paste Meta keys",
        ),
    ]
