"""Server-side OAuth 2.0 authorization-code flow with PKCE (RFC 6749, RFC 7636).

* State is random (256 bits), stored server-side only as a SHA-256 hash, bound to the
  session user + tenant + environment + connection, single-use and short-lived
  (settings.oauth_state_ttl_seconds). The PKCE verifier is stored encrypted.
* The redirect URI is built only from settings.oauth_redirect_base_url (exact match with
  what is registered at the provider); request input never influences it.
* Granted scopes must include the definition's required scopes.
* Token exchange/refresh/revoke go through the central OutboundClient (SSRF policy,
  timeouts, no redirects). Access and refresh tokens are stored encrypted with the other
  connection credentials; only expiry is visible.

No OAuth provider is live yet (all OAuth definitions are `planned`); the framework is
verified with a fake provider through MockTransport (tests/integration).
"""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations.crypto import CredentialManager
from app.integrations.errors import IntegrationError
from app.integrations.http import OutboundClient
from app.integrations.registry import IntegrationDefinition, OAuthSpec
from app.modules.integrations.models import IntegrationConnection, OAuthState
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

CALLBACK_PATH = "/api/v1/integrations/oauth/callback"
REFRESH_MARGIN = timedelta(seconds=60)


class OAuthStateInvalid(Exception):
    """Unknown, reused, expired or foreign state. Never says which."""


@dataclass(frozen=True, slots=True)
class CallbackResult:
    connection_id: Any
    ok: bool


def now() -> datetime:
    return datetime.now(UTC)


def redirect_uri(settings: Settings) -> str:
    if not settings.oauth_redirect_base_url:
        raise BusinessRuleViolation(
            "OAUTH_NOT_CONFIGURED", "OAuth is not configured on this server", 503
        )
    return settings.oauth_redirect_base_url.rstrip("/") + CALLBACK_PATH


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _spec(definition: IntegrationDefinition) -> OAuthSpec:
    if definition.oauth is None or definition.auth_type not in ("oauth2", "oauth2_pkce"):
        raise BusinessRuleViolation("OAUTH_NOT_SUPPORTED", "This integration does not use OAuth")
    return definition.oauth


def _client(
    settings: Settings,
    spec: OAuthSpec,
    connection: IntegrationConnection,
    credentials: dict[str, Any],
) -> tuple[str, str | None]:
    client_id = str(connection.config.get("client_id") or "")
    if not client_id and spec.client_id_setting:
        client_id = str(getattr(settings, spec.client_id_setting, "") or "")
    secret = credentials.get("client_secret")
    if not secret and spec.client_secret_setting:
        value = getattr(settings, spec.client_secret_setting, None)
        secret = value.get_secret_value() if value is not None else None
    if not client_id:
        raise BusinessRuleViolation(
            "OAUTH_NOT_CONFIGURED", "The OAuth client is not configured", 503
        )
    return client_id, str(secret) if secret else None


def validate_scopes(definition: IntegrationDefinition, requested: list[str] | None) -> list[str]:
    scopes = list(dict.fromkeys([*definition.required_scopes, *(requested or [])]))
    unknown = set(scopes) - set(definition.supported_scopes) - set(definition.required_scopes)
    if unknown:
        raise BusinessRuleViolation("INVALID_SCOPE", "A requested scope is not supported")
    return scopes


async def start(
    session: AsyncSession,
    settings: Settings,
    scope: WorkspaceScope,
    connection: IntegrationConnection,
    definition: IntegrationDefinition,
    requested_scopes: list[str] | None = None,
) -> str:
    spec = _spec(definition)
    if scope.user_id is None:
        raise BusinessRuleViolation("OAUTH_USER_REQUIRED", "Sign in to connect this integration")
    manager = CredentialManager(settings)
    credentials = manager.decrypt_json(connection.credentials_encrypted)
    client_id, _secret = _client(settings, spec, connection, credentials)
    uri = redirect_uri(settings)
    scopes = validate_scopes(definition, requested_scopes)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)[:96]
    session.add(
        OAuthState(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            connection_id=connection.id,
            state_hash=hashlib.sha256(state.encode()).hexdigest(),
            user_id=scope.user_id,
            code_verifier_encrypted=manager.encrypt(verifier) if spec.pkce else None,
            redirect_uri=uri,
            scopes=scopes,
            expires_at=now() + timedelta(seconds=settings.oauth_state_ttl_seconds),
        )
    )
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": uri,
        "scope": " ".join(scopes),
        "state": state,
        **dict(spec.extra_authorize_params),
    }
    if spec.pkce:
        params |= {"code_challenge": pkce_challenge(verifier), "code_challenge_method": "S256"}
    await session.flush()
    return f"{spec.authorize_url}?{urlencode(params)}"


def _token_values(
    data: dict[str, Any], definition: IntegrationDefinition, requested: list[str]
) -> tuple[str, str | None, datetime | None, list[str]]:
    access = data.get("access_token")
    if not isinstance(access, str) or not access:
        raise IntegrationError(
            "INVALID_RESPONSE", "The provider returned no access token", kind="invalid_response"
        )
    refresh = data.get("refresh_token")
    expires_in = data.get("expires_in")
    expires = None
    if isinstance(expires_in, int | float) and expires_in > 0:
        expires = now() + timedelta(seconds=min(float(expires_in), 10 * 365 * 86400))
    granted_raw = data.get("scope")
    granted = str(granted_raw).replace(",", " ").split() if granted_raw else requested
    missing = set(definition.required_scopes) - set(granted)
    if missing:
        raise IntegrationError(
            "MISSING_SCOPE", "Required permissions were not granted", kind="auth"
        )
    return access, refresh if isinstance(refresh, str) and refresh else None, expires, granted


async def _token_request(
    http: OutboundClient, spec: OAuthSpec, form: dict[str, str]
) -> dict[str, Any]:
    response = await http.request(
        "POST",
        spec.token_url,
        form=form,
        headers={"accept": "application/json"},
        max_bytes=64 * 1024,
    )
    if response.status_code in (400, 401):
        data = response.json() if response.content else None
        error = data.get("error") if isinstance(data, dict) else None
        if error in ("invalid_grant", "invalid_client", "unauthorized_client"):
            raise IntegrationError(
                "OAUTH_GRANT_INVALID",
                "Authorization expired or was revoked",
                kind="auth",
                status=response.status_code,
            )
    response.ensure_success()
    return response.json_object()


async def callback(
    session: AsyncSession,
    settings: Settings,
    http: OutboundClient,
    definition_lookup: Any,
    *,
    state: str,
    code: str | None,
    error: str | None,
    user_id: Any,
    tenant_id: Any,
    environment_id: Any,
) -> CallbackResult:
    if not state or len(state) > 200:
        raise OAuthStateInvalid
    record = await session.scalar(
        select(OAuthState)
        .where(OAuthState.state_hash == hashlib.sha256(state.encode()).hexdigest())
        .with_for_update()
    )
    if (
        record is None
        or record.consumed_at is not None
        or record.expires_at <= now()
        or record.user_id != user_id
        or record.tenant_id != tenant_id
        or record.environment_id != environment_id
    ):
        raise OAuthStateInvalid
    record.consumed_at = now()  # single use, even when the exchange below fails
    connection = await session.scalar(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.tenant_id == record.tenant_id,
            IntegrationConnection.environment_id == record.environment_id,
            IntegrationConnection.id == record.connection_id,
        )
        .with_for_update()
    )
    if connection is None or connection.status in ("revoked", "disabled"):
        raise OAuthStateInvalid
    definition: IntegrationDefinition | None = definition_lookup(connection.integration_key)
    if definition is None:
        raise OAuthStateInvalid
    spec = _spec(definition)
    if error or not code or len(code) > 2048:
        connection.status = "error"
        connection.last_error = "Authorization was declined or failed"
        connection.last_error_code = "OAUTH_DECLINED"
        await session.flush()
        return CallbackResult(connection.id, False)
    manager = CredentialManager(settings)
    credentials = manager.decrypt_json(connection.credentials_encrypted)
    client_id, client_secret = _client(settings, spec, connection, credentials)
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": record.redirect_uri,
        "client_id": client_id,
    }
    if record.code_verifier_encrypted:
        form["code_verifier"] = manager.decrypt(record.code_verifier_encrypted)
    if client_secret:
        form["client_secret"] = client_secret
    try:
        data = await _token_request(http, spec, form)
        access, refresh, expires, granted = _token_values(data, definition, list(record.scopes))
    except IntegrationError as failure:
        connection.status = "error"
        connection.last_error, connection.last_error_code = failure.message, failure.code
        await session.flush()
        return CallbackResult(connection.id, False)
    credentials["access_token"] = access
    if refresh:
        credentials["refresh_token"] = refresh
    connection.credentials_encrypted = manager.encrypt_json(credentials)
    connection.expires_at = expires
    connection.scopes = granted
    connection.status = "connected"
    connection.health = "healthy"
    connection.connected_at = now()
    connection.last_error = connection.last_error_code = None
    await session.flush()
    return CallbackResult(connection.id, True)


async def refresh(
    session: AsyncSession,
    settings: Settings,
    http: OutboundClient,
    connection: IntegrationConnection,
    definition: IntegrationDefinition,
) -> bool:
    """Refresh the access token. Returns False (and marks `expired`) when not possible."""
    spec = _spec(definition)
    manager = CredentialManager(settings)
    credentials = manager.decrypt_json(connection.credentials_encrypted)
    token = credentials.get("refresh_token")
    if not token:
        connection.status = "expired"
        await session.flush()
        return False
    client_id, client_secret = _client(settings, spec, connection, credentials)
    form = {"grant_type": "refresh_token", "refresh_token": str(token), "client_id": client_id}
    if client_secret:
        form["client_secret"] = client_secret
    try:
        data = await _token_request(http, spec, form)
        access, new_refresh, expires, granted = _token_values(
            data, definition, list(connection.scopes)
        )
    except IntegrationError as failure:
        if failure.kind == "auth":
            connection.status = "expired"
            connection.health = "failing"
        connection.last_error, connection.last_error_code = failure.message, failure.code
        await session.flush()
        return False
    credentials["access_token"] = access
    if new_refresh:  # rotating refresh tokens replace the old one
        credentials["refresh_token"] = new_refresh
    connection.credentials_encrypted = manager.encrypt_json(credentials)
    connection.expires_at, connection.scopes = expires, granted
    if connection.status == "expired":
        connection.status = "connected"
    await session.flush()
    return True


def needs_refresh(connection: IntegrationConnection) -> bool:
    return connection.expires_at is not None and connection.expires_at - REFRESH_MARGIN <= now()


async def revoke(
    settings: Settings,
    http: OutboundClient,
    connection: IntegrationConnection,
    definition: IntegrationDefinition,
) -> bool:
    """Best-effort token revocation at the provider (RFC 7009)."""
    spec = definition.oauth
    if spec is None or not spec.revoke_url:
        return False
    credentials = CredentialManager(settings).decrypt_json(connection.credentials_encrypted)
    token = credentials.get("refresh_token") or credentials.get("access_token")
    if not token:
        return False
    try:
        response = await http.request(
            "POST", spec.revoke_url, form={"token": str(token)}, max_bytes=16 * 1024
        )
        return response.ok
    except IntegrationError:
        return False
