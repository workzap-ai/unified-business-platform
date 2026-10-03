"""Business-owned tool connections for the standalone Pi app: Google Calendar and Shopify.

Each business authorizes its OWN calendar/store; the platform only holds its OAuth app
credentials (settings). Connections are ordinary integration connections (encrypted
credentials, health, circuit breaker, audit) so Owner OS operators see the same records.

* Google Calendar: authorization code + PKCE through `app.integrations.oauth`, with the
  Pi app's callback URL (same-origin with the Pi session cookie).
* Shopify: per-shop authorization code grant. The callback HMAC is verified with the app
  secret, the shop must equal the one the owner typed, and the single-use state is bound
  to the same user, business and environment. Expiring offline tokens are refreshed.

Customer-facing screens never show tokens, client ids or provider account ids.
"""

import hashlib
import hmac
import secrets
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audience import PI_PREFIX
from app.core.config import Settings
from app.integrations import oauth
from app.integrations.catalog import REGISTRY
from app.integrations.crypto import CredentialManager
from app.integrations.errors import IntegrationError
from app.integrations.http import OutboundClient
from app.integrations.providers.shopify import SCOPES as SHOPIFY_SCOPES
from app.integrations.providers.shopify import valid_shop
from app.modules.audit.service import record
from app.modules.integrations.models import IntegrationConnection, OAuthState
from app.modules.integrations.schemas import ConnectionCreate
from app.modules.integrations.service import IntegrationService, Runtime
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

KEYS = ("google_calendar", "shopify")
CALLBACK = {
    "google_calendar": f"{PI_PREFIX}/pi/connectors/google_calendar/callback",
    "shopify": f"{PI_PREFIX}/pi/connectors/shopify/callback",
}
USABLE = ("connected", "degraded")
PLAIN = {
    "google_calendar": (
        "Google Calendar",
        "pi checks your free times and adds confirmed bookings to your calendar.",
    ),
    "shopify": (
        "Shopify",
        "pi can tell customers where their Shopify order is. It cannot change orders.",
    ),
}


def _now() -> datetime:
    return datetime.now(UTC)


def server_ready(settings: Settings, key: str) -> bool:
    if key == "google_calendar":
        return bool(settings.google_oauth_client_id and settings.google_oauth_client_secret)
    return bool(settings.shopify_client_id and settings.shopify_client_secret)


def callback_uri(settings: Settings, key: str, app: str = "pi") -> str:
    """Where the provider sends the browser back: the Pi app, or the Owner OS web app
    (both must be registered as redirect URIs in the Google/Shopify app)."""
    if app == "web":
        base = (settings.cors_origins[0] if settings.cors_origins else "").rstrip("/")
        if not base:
            raise BusinessRuleViolation(
                "APP_URL_REQUIRED", "The app address is not configured on this server", 503
            )
        return f"{base}/api/v1/pi/connectors/{key}/callback"
    base = (settings.pi_app_public_url or "").rstrip("/")
    if not base:
        raise BusinessRuleViolation(
            "PI_APP_URL_REQUIRED", "The Pi app address is not configured on this server", 503
        )
    return base + CALLBACK[key]


async def current(
    session: AsyncSession, scope: WorkspaceScope, key: str, *, for_update: bool = False
) -> IntegrationConnection | None:
    query = (
        WorkspaceRepository(session, IntegrationConnection, scope)
        .select()
        .where(
            IntegrationConnection.integration_key == key,
            IntegrationConnection.status != "revoked",
        )
        # A working connection wins over a newer unfinished or failed attempt (for
        # example one started from Owner OS Integrations and abandoned), so Pi keeps
        # using the calendar or store that works.
        .order_by(
            case((IntegrationConnection.status.in_(USABLE), 0), else_=1),
            IntegrationConnection.created_at.desc(),
        )
        .limit(1)
    )
    if for_update:
        query = query.with_for_update()
    row: IntegrationConnection | None = await session.scalar(query)
    return row


def _service(session: AsyncSession, scope: WorkspaceScope, rt: Runtime) -> IntegrationService:
    return IntegrationService(session, scope, rt)


def view(settings: Settings, key: str, row: IntegrationConnection | None) -> dict[str, Any]:
    name, description = PLAIN[key]
    if row is None:
        state = "not_connected"
    elif row.status in USABLE:
        state = "connected"
    elif row.status in ("draft", "connecting"):
        state = "connecting"
    else:
        state = "action_required"
    detail = ""
    if row is not None and key == "shopify":
        detail = str(row.config.get("shop_domain") or "")
    return {
        "key": key,
        "name": name,
        "description": description,
        # False: the platform's own app credentials are not configured on this server.
        "available": server_ready(settings, key),
        "state": state,
        "detail": detail,
        "health": row.health if row else "unknown",
        "last_checked_at": row.last_health_check_at if row else None,
        "problem": (row.last_error or "") if row is not None and state != "connected" else "",
    }


async def status(
    session: AsyncSession, settings: Settings, scope: WorkspaceScope
) -> list[dict[str, Any]]:
    scope.require("integrations.read")
    return [view(settings, key, await current(session, scope, key)) for key in KEYS]


async def _connection(
    session: AsyncSession,
    scope: WorkspaceScope,
    rt: Runtime,
    key: str,
    config: dict[str, Any],
) -> IntegrationConnection:
    """Reuse the business's pending/failed connection (reconnect) or create one."""
    row = await current(session, scope, key, for_update=True)
    same = row is not None and row.config.get("shop_domain") == config.get("shop_domain")
    if row is not None and row.status not in USABLE and same:
        return row
    if row is not None:
        # A different store/calendar, or a reconnect of a working one: retire the old one.
        await _service(session, scope, rt).disconnect(row.id)
    name, _ = PLAIN[key]
    return await _service(session, scope, rt).create(
        ConnectionCreate(integration_key=key, display_name=name, mode="production", config=config)
    )


async def start_google(
    session: AsyncSession, scope: WorkspaceScope, rt: Runtime, app: str = "pi"
) -> str:
    scope.require("integrations.manage")
    if not server_ready(rt.settings, "google_calendar"):
        raise BusinessRuleViolation(
            "CONNECTOR_UNAVAILABLE", "Google Calendar isn't available on this server yet", 503
        )
    definition = REGISTRY.definition("google_calendar")
    assert definition is not None
    connection = await _connection(session, scope, rt, "google_calendar", {})
    url = await oauth.start(
        session,
        rt.settings,
        scope,
        connection,
        definition,
        callback_uri=callback_uri(rt.settings, "google_calendar", app),
    )
    await record(
        session,
        "pi.connector.started",
        scope=scope,
        entity_type="integration_connection",
        entity_id=connection.id,
        details={"integration": "google_calendar"},
    )
    return url


async def finish_google(
    session: AsyncSession,
    scope: WorkspaceScope,
    rt: Runtime,
    *,
    state: str,
    code: str | None,
    error: str | None,
) -> bool:
    try:
        result = await oauth.callback(
            session,
            rt.settings,
            rt.http,
            REGISTRY.definition,
            state=state,
            code=code,
            error=error,
            user_id=scope.user_id,
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
        )
    except oauth.OAuthStateInvalid:
        return False
    await record(
        session,
        "pi.connector.completed",
        scope=scope,
        entity_type="integration_connection",
        entity_id=result.connection_id,
        outcome="success" if result.ok else "failure",
        details={"integration": "google_calendar"},
    )
    return result.ok


# --- Shopify ---------------------------------------------------------------------------


def shopify_hmac_valid(params: Mapping[str, str], secret: str) -> bool:
    """Shopify: remove `hmac`, sort the rest, join as k=v with '&', HMAC-SHA256 hex."""
    given = params.get("hmac") or ""
    message = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if k != "hmac")
    expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return bool(given) and hmac.compare_digest(expected, given)


async def start_shopify(
    session: AsyncSession, scope: WorkspaceScope, rt: Runtime, shop_input: str, app: str = "pi"
) -> str:
    scope.require("integrations.manage")
    settings = rt.settings
    if not server_ready(settings, "shopify"):
        raise BusinessRuleViolation(
            "CONNECTOR_UNAVAILABLE", "Shopify isn't available on this server yet", 503
        )
    if scope.user_id is None:
        raise BusinessRuleViolation("OAUTH_USER_REQUIRED", "Sign in to connect this integration")
    try:
        shop = valid_shop(shop_input)
    except IntegrationError as exc:
        raise BusinessRuleViolation("INVALID_SHOP", exc.message, 422) from None
    connection = await _connection(session, scope, rt, "shopify", {"shop_domain": shop})
    state = secrets.token_urlsafe(32)
    uri = callback_uri(settings, "shopify", app)
    session.add(
        OAuthState(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            connection_id=connection.id,
            state_hash=hashlib.sha256(state.encode()).hexdigest(),
            user_id=scope.user_id,
            code_verifier_encrypted=None,
            redirect_uri=uri,
            scopes=list(SHOPIFY_SCOPES),
            expires_at=_now() + timedelta(seconds=settings.oauth_state_ttl_seconds),
        )
    )
    await session.flush()
    await record(
        session,
        "pi.connector.started",
        scope=scope,
        entity_type="integration_connection",
        entity_id=connection.id,
        details={"integration": "shopify"},
    )
    query = urlencode(
        {
            "client_id": settings.shopify_client_id or "",
            "scope": ",".join(SHOPIFY_SCOPES),
            "redirect_uri": uri,
            "state": state,
        }
    )
    return f"https://{shop}/admin/oauth/authorize?{query}"


def _store_tokens(
    manager: CredentialManager, connection: IntegrationConnection, data: Mapping[str, Any]
) -> None:
    access = data.get("access_token")
    if not isinstance(access, str) or not access:
        raise IntegrationError(
            "INVALID_RESPONSE", "Shopify returned no access token", kind="invalid_response"
        )
    granted = str(data.get("scope") or "").replace(" ", "").split(",")
    # Shopify may report an implied scope (write_x covers read_x).
    missing = {
        s
        for s in SHOPIFY_SCOPES
        if s not in granted and s.replace("read_", "write_") not in granted
    }
    if missing:
        raise IntegrationError(
            "MISSING_SCOPE", "Required permissions were not granted", kind="auth"
        )
    credentials = manager.decrypt_json(connection.credentials_encrypted)
    credentials["access_token"] = access
    if isinstance(data.get("refresh_token"), str) and data["refresh_token"]:
        credentials["refresh_token"] = data["refresh_token"]
    connection.credentials_encrypted = manager.encrypt_json(credentials)
    expires_in = data.get("expires_in")
    connection.expires_at = (
        _now() + timedelta(seconds=float(expires_in))
        if isinstance(expires_in, int | float) and expires_in > 0
        else None
    )
    connection.scopes = [s for s in granted if s][:20]


async def _shopify_token(
    http: OutboundClient, settings: Settings, shop: str, form: dict[str, str]
) -> dict[str, Any]:
    secret = settings.shopify_client_secret
    body = {
        "client_id": settings.shopify_client_id or "",
        "client_secret": secret.get_secret_value() if secret else "",
        **form,
    }
    response = await http.request(
        "POST",
        f"https://{shop}/admin/oauth/access_token",
        form=body,
        headers={"accept": "application/json"},
        max_bytes=64 * 1024,
    )
    if response.status_code in (400, 401, 403):
        raise IntegrationError(
            "OAUTH_GRANT_INVALID", "Authorization expired or was revoked", kind="auth"
        )
    return response.ensure_success().json_object()


async def finish_shopify(
    session: AsyncSession, scope: WorkspaceScope, rt: Runtime, params: Mapping[str, str]
) -> bool:
    settings = rt.settings
    secret = settings.shopify_client_secret
    if secret is None or not shopify_hmac_valid(params, secret.get_secret_value()):
        return False
    state = params.get("state") or ""
    if not state or len(state) > 200:
        return False
    row = await session.scalar(
        select(OAuthState)
        .where(OAuthState.state_hash == hashlib.sha256(state.encode()).hexdigest())
        .with_for_update()
    )
    if (
        row is None
        or row.consumed_at is not None
        or row.expires_at <= _now()
        or row.user_id != scope.user_id
        or row.tenant_id != scope.tenant_id
        or row.environment_id != scope.environment_id
    ):
        return False
    row.consumed_at = _now()  # single use, even if the exchange below fails
    connection = await WorkspaceRepository(session, IntegrationConnection, scope).find(
        IntegrationConnection.id == row.connection_id
    )
    if connection is None or connection.integration_key != "shopify":
        return False
    if connection.status in ("revoked", "disabled"):
        return False
    try:
        shop = valid_shop(params.get("shop") or "")
    except IntegrationError:
        return False
    if shop != connection.config.get("shop_domain") or not params.get("code"):
        connection.status, connection.last_error = "error", "Authorization was declined"
        connection.last_error_code = "OAUTH_DECLINED"
        return False
    manager = CredentialManager(settings)
    try:
        data = await _shopify_token(
            rt.http, settings, shop, {"code": params["code"][:2048], "expiring": "1"}
        )
        _store_tokens(manager, connection, data)
    except IntegrationError as failure:
        connection.status = "error"
        connection.last_error, connection.last_error_code = failure.message, failure.code
        return False
    connection.status, connection.health = "connected", "healthy"
    connection.connected_at = _now()
    connection.last_error = connection.last_error_code = None
    await record(
        session,
        "pi.connector.completed",
        scope=scope,
        entity_type="integration_connection",
        entity_id=connection.id,
        details={"integration": "shopify"},
    )
    return True


# --- use --------------------------------------------------------------------------------


async def fresh(
    session: AsyncSession,
    settings: Settings,
    http: OutboundClient,
    connection: IntegrationConnection,
) -> IntegrationConnection:
    """Refresh an expiring access token before use. Marks the connection `expired` (and
    raises) when the business must reconnect; nothing is silently treated as working."""
    if not oauth.needs_refresh(connection):
        return connection
    if connection.integration_key == "google_calendar":
        definition = REGISTRY.definition("google_calendar")
        assert definition is not None
        refreshed = await oauth.refresh(session, settings, http, connection, definition)
    else:
        manager = CredentialManager(settings)
        token = manager.decrypt_json(connection.credentials_encrypted).get("refresh_token")
        refreshed = False
        if token:
            try:
                data = await _shopify_token(
                    http,
                    settings,
                    valid_shop(str(connection.config.get("shop_domain") or "")),
                    {"grant_type": "refresh_token", "refresh_token": str(token)},
                )
                _store_tokens(manager, connection, data)
                refreshed = True
            except IntegrationError as failure:
                connection.last_error, connection.last_error_code = failure.message, failure.code
                if failure.kind != "auth":
                    raise
        if not refreshed:
            connection.status, connection.health = "expired", "failing"
        await session.flush()
    if not refreshed:
        raise IntegrationError(
            "RECONNECT_REQUIRED", "The connection expired; reconnect it in Tools", kind="auth"
        )
    return connection


async def usable(
    session: AsyncSession, scope: WorkspaceScope, key: str
) -> IntegrationConnection | None:
    row = await current(session, scope, key)
    return row if row is not None and row.status in USABLE else None


async def test(session: AsyncSession, scope: WorkspaceScope, rt: Runtime, key: str) -> Any:
    scope.require("integrations.manage")
    row = await current(session, scope, key, for_update=True)
    if row is None:
        raise BusinessRuleViolation("NOT_CONNECTED", "Connect this tool first", 409)
    try:
        await fresh(session, rt.settings, rt.http, row)
    except IntegrationError as exc:
        return {"ok": False, "status": row.status, "message": exc.message}
    result = await _service(session, scope, rt).run_test(row)
    return {"ok": result.ok, "status": result.status, "message": result.message}


async def disconnect(session: AsyncSession, scope: WorkspaceScope, rt: Runtime, key: str) -> None:
    """Destroys stored tokens (and revokes Google's grant). Shopify store owners also
    uninstall the app in their Shopify admin to remove its access completely."""
    scope.require("integrations.manage")
    row = await current(session, scope, key, for_update=True)
    if row is not None:
        await _service(session, scope, rt).disconnect(row.id)
