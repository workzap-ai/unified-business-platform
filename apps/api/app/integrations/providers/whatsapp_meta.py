"""WhatsApp Business Cloud API (Meta Graph API).

Docs: https://developers.facebook.com/docs/whatsapp/cloud-api
* Test connection: GET /{version}/{phone_number_id}?fields=display_phone_number,
  verified_name,quality_rating (read-only).
* Send: POST /{version}/{phone_number_id}/messages.
* Media: GET /{version}/{media_id} -> short-lived URL on lookaside.fbsbx.com, then GET it
  with the same bearer token (host allowlisted, size capped, redirects not followed).
* Webhooks: X-Hub-Signature-256 = "sha256=" + HMAC-SHA256(app secret, raw body). Meta
  sends no signed timestamp, so replay protection relies on idempotency by message id.
  GET verification: hub.mode=subscribe, hub.verify_token, hub.challenge.

Note: PI's existing webhook (/api/v1/webhooks/whatsapp, app/modules/pi) is unchanged; this
adapter is the platform implementation PI can delegate to (see docs/INTEGRATIONS.md).
"""

import hmac
import json
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from app.core.config import Settings
from app.integrations.errors import IntegrationError, RateLimited
from app.integrations.http import OutboundResponse
from app.integrations.providers.base import credential, hmac_sha256_hex, ok, require_field
from app.integrations.registry import (
    ConfigField,
    ConfigurationInvalid,
    HealthResult,
    IntegrationDefinition,
    MediaItem,
    NormalizedEvent,
    ProviderContext,
    SendResult,
    WhatsAppProvider,
)

NUMBER_ID = re.compile(r"^[0-9]{5,32}$")
RECIPIENT = re.compile(r"^\+?[0-9]{6,15}$")
MEDIA_HOSTS = frozenset({"lookaside.fbsbx.com", "lookaside.facebook.com"})
MEDIA_TYPES = frozenset({"image", "audio", "video", "document", "sticker"})
AUTH_CODES = frozenset({190, 102, 10, 200, 294})
RATE_CODES = frozenset({4, 17, 32, 613, 80007, 130429, 131048, 131056})

DEFINITION = IntegrationDefinition(
    key="whatsapp_meta",
    name="WhatsApp (Meta Cloud API)",
    description="Send and receive WhatsApp messages through the Meta WhatsApp Cloud API.",
    category="messaging",
    provider="Meta",
    auth_type="bearer_token",
    capabilities=("send_text", "send_media", "receive_messages", "media_download"),
    supported_scopes=("whatsapp_business_messaging", "whatsapp_business_management"),
    required_scopes=("whatsapp_business_messaging",),
    webhook_support=True,
    supports_sandbox=True,
    documentation_url="https://developers.facebook.com/docs/whatsapp/cloud-api",
    config_schema=(
        ConfigField("phone_number_id", "Phone number ID", "text", help="From WhatsApp Manager"),
        ConfigField("business_account_id", "WhatsApp Business Account ID", "text", required=False),
        ConfigField(
            "access_token",
            "Access token",
            "password",
            secret=True,
            help="System user token with whatsapp_business_messaging",
        ),
        ConfigField(
            "app_secret",
            "App secret",
            "password",
            secret=True,
            required=False,
            help="Verifies webhook signatures; defaults to the platform app secret",
        ),
        ConfigField(
            "verify_token",
            "Webhook verify token",
            "password",
            secret=True,
            required=False,
            help="Used once by Meta to verify the callback URL",
        ),
    ),
)


def _graph_error(response: OutboundResponse) -> IntegrationError | None:
    if response.ok:
        return None
    code: int | None = None
    try:
        data = json.loads(response.content or b"{}")
        code = int(data.get("error", {}).get("code"))
    except (ValueError, TypeError, AttributeError):
        code = None
    if response.status_code == 429 or code in RATE_CODES:
        return RateLimited(response.retry_after())
    if response.status_code in (401, 403) or code in AUTH_CODES:
        return IntegrationError(
            "INVALID_CREDENTIALS",
            "Meta rejected the access token or it lacks permission",
            kind="auth",
            status=response.status_code,
        )
    try:
        response.ensure_success()
    except IntegrationError as error:
        return error
    return None  # pragma: no cover


class WhatsAppMetaProvider(WhatsAppProvider):
    key = "whatsapp_meta"
    capabilities = frozenset(DEFINITION.capabilities)

    def _base(self, ctx: ProviderContext) -> str:
        s = ctx.settings
        return f"{s.whatsapp_graph_base_url.rstrip('/')}/{s.whatsapp_graph_version}"

    def _number(self, ctx: ProviderContext) -> str:
        number = str(ctx.config.get("phone_number_id", ""))
        if not NUMBER_ID.fullmatch(number):
            raise IntegrationError("INVALID_CONFIGURATION", "The phone number ID is invalid")
        return number

    def _auth(self, ctx: ProviderContext) -> dict[str, str]:
        return {"authorization": f"Bearer {credential(ctx.credentials, 'access_token')}"}

    def validate_configuration(
        self, config: Mapping[str, Any], credentials: Mapping[str, str], settings: Settings
    ) -> None:
        number = require_field(config, "phone_number_id", "Phone number ID")
        if not NUMBER_ID.fullmatch(number):
            raise ConfigurationInvalid("Phone number ID must be numeric", "phone_number_id")
        account = config.get("business_account_id")
        if account and not NUMBER_ID.fullmatch(str(account)):
            raise ConfigurationInvalid("Business account ID must be numeric", "business_account_id")

    async def health_check(self, ctx: ProviderContext) -> HealthResult:
        identity = await self.phone_identity(ctx)
        return ok(
            "Connected to WhatsApp number " + str(identity.get("display_phone_number", ""))[:32],
            None,
            quality_rating=str(identity.get("quality_rating", ""))[:16],
        )

    async def phone_identity(self, ctx: ProviderContext) -> Mapping[str, Any]:
        response = await ctx.http.request(
            "GET",
            f"{self._base(ctx)}/{self._number(ctx)}",
            params={"fields": "display_phone_number,verified_name,quality_rating"},
            headers=self._auth(ctx),
            max_bytes=64 * 1024,
            context=ctx.call,
        )
        error = _graph_error(response)
        if error:
            raise error
        data = response.json_object()
        return {
            "id": str(data.get("id", ""))[:32],
            "display_phone_number": str(data.get("display_phone_number", ""))[:32],
            "verified_name": str(data.get("verified_name", ""))[:120],
            "quality_rating": str(data.get("quality_rating", ""))[:16],
        }

    async def _send(self, ctx: ProviderContext, recipient: str, body: dict[str, Any]) -> SendResult:
        if not RECIPIENT.fullmatch(recipient):
            raise IntegrationError("INVALID_RECIPIENT", "The recipient number is invalid")
        response = await ctx.http.request(
            "POST",
            f"{self._base(ctx)}/{self._number(ctx)}/messages",
            json_body={"messaging_product": "whatsapp", "to": recipient.lstrip("+"), **body},
            headers=self._auth(ctx),
            max_bytes=64 * 1024,
            context=ctx.call,
        )
        error = _graph_error(response)
        if error:
            raise error
        try:
            message_id = response.json_object()["messages"][0]["id"]
        except (KeyError, IndexError, TypeError):
            raise IntegrationError(
                "INVALID_RESPONSE",
                "Meta returned an unexpected response",
                kind="invalid_response",
            ) from None
        if not isinstance(message_id, str) or not 1 <= len(message_id) <= 160:
            raise IntegrationError(
                "INVALID_RESPONSE", "Meta returned an invalid message id", kind="invalid_response"
            )
        return SendResult(message_id)

    async def send_text(self, ctx: ProviderContext, recipient: str, text: str) -> SendResult:
        return await self._send(ctx, recipient, {"type": "text", "text": {"body": text[:4096]}})

    async def send_media(
        self,
        ctx: ProviderContext,
        recipient: str,
        media_type: str,
        link: str,
        caption: str | None = None,
    ) -> SendResult:
        if media_type not in MEDIA_TYPES or not link.startswith("https://"):
            raise IntegrationError("INVALID_MEDIA", "Unsupported media")
        media: dict[str, Any] = {"link": link}
        if caption and media_type in {"image", "video", "document"}:
            media["caption"] = caption[:1024]
        return await self._send(ctx, recipient, {"type": media_type, media_type: media})

    async def get_media(self, ctx: ProviderContext, media_id: str) -> MediaItem:
        if not NUMBER_ID.fullmatch(media_id):
            raise IntegrationError("INVALID_MEDIA", "Unsupported media")
        response = await ctx.http.request(
            "GET",
            f"{self._base(ctx)}/{media_id}",
            headers=self._auth(ctx),
            max_bytes=16 * 1024,
            context=ctx.call,
        )
        error = _graph_error(response)
        if error:
            raise error
        data = response.json_object()
        url, mime = str(data.get("url", "")), str(data.get("mime_type", ""))
        parts = urlsplit(url)
        limit = ctx.settings.media_max_bytes
        if parts.scheme != "https" or parts.hostname not in MEDIA_HOSTS:
            raise IntegrationError("INVALID_MEDIA", "Media location is not trusted")
        try:
            if int(data.get("file_size", 0)) > limit:
                raise IntegrationError("INVALID_MEDIA", "Media is too large")
        except (TypeError, ValueError):
            raise IntegrationError("INVALID_MEDIA", "Media metadata is invalid") from None
        download = await ctx.http.request(
            "GET", url, headers=self._auth(ctx), max_bytes=limit, context=ctx.call
        )
        error = _graph_error(download)
        if error:
            raise error
        if not download.content:
            raise IntegrationError("INVALID_MEDIA", "Media is empty")
        return MediaItem(download.content, mime[:100])

    # --- webhooks ------------------------------------------------------------------

    def _app_secret(self, credentials: Mapping[str, str], settings: Settings) -> str | None:
        secret = credentials.get("app_secret")
        if secret:
            return secret
        return (
            settings.whatsapp_app_secret.get_secret_value()
            if settings.whatsapp_app_secret
            else None
        )

    def verify_webhook(
        self,
        headers: Mapping[str, str],
        body: bytes,
        credentials: Mapping[str, str],
        settings: Settings,
        now: float,
    ) -> bool:
        secret = self._app_secret(credentials, settings)
        signature = headers.get("x-hub-signature-256", "")
        if not secret or not signature.startswith("sha256="):
            return False
        return hmac.compare_digest("sha256=" + hmac_sha256_hex(secret, body), signature)

    def handshake(
        self, params: Mapping[str, str], credentials: Mapping[str, str], settings: Settings
    ) -> str | None:
        expected = credentials.get("verify_token")
        supplied = params.get("hub.verify_token", "")
        challenge = params.get("hub.challenge", "")
        if (
            not expected
            or params.get("hub.mode") != "subscribe"
            or not hmac.compare_digest(expected, supplied)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", challenge)
        ):
            return None
        return challenge

    def parse_webhook(self, body: bytes) -> list[NormalizedEvent]:
        payload = json.loads(body)
        if not isinstance(payload, dict) or payload.get("object") not in (
            None,
            "whatsapp_business_account",
        ):
            raise ValueError("Unexpected payload")
        events: list[NormalizedEvent] = []
        for entry in payload.get("entry", [])[:50]:
            for change in entry.get("changes", [])[:50]:
                value = change.get("value", {}) or {}
                number = str(value.get("metadata", {}).get("phone_number_id", ""))
                if not NUMBER_ID.fullmatch(number):
                    continue
                for message in value.get("messages", [])[:100]:
                    mid, sender = message.get("id"), str(message.get("from", ""))
                    if not isinstance(mid, str) or not 1 <= len(mid) <= 160:
                        continue
                    if not re.fullmatch(r"[0-9]{6,15}", sender):
                        continue
                    kind = str(message.get("type", "other"))
                    part = message.get(kind, {}) if isinstance(message.get(kind), dict) else {}
                    events.append(
                        NormalizedEvent(
                            provider_event_id=mid,
                            event_type="message.received",
                            occurred_at=None,
                            data={
                                "phone_number_id": number,
                                "message_id": mid,
                                "from": sender,
                                "type": kind if kind in {"text", *MEDIA_TYPES} else "other",
                                "text": str(message.get("text", {}).get("body", ""))[:4096]
                                if kind == "text"
                                else str(part.get("caption", ""))[:1024],
                                "media_id": str(part.get("id", ""))[:64] or None,
                                "timestamp": str(message.get("timestamp", ""))[:16],
                            },
                        )
                    )
                for status in value.get("statuses", [])[:100]:
                    mid, state = status.get("id"), status.get("status")
                    if (
                        isinstance(mid, str)
                        and len(mid) <= 160
                        and state in {"sent", "delivered", "read", "failed"}
                    ):
                        events.append(
                            NormalizedEvent(
                                provider_event_id=f"{mid}:{state}",
                                event_type="message.status",
                                data={
                                    "phone_number_id": number,
                                    "message_id": mid,
                                    "status": state,
                                },
                            )
                        )
        return events[:100]

    async def execute(
        self, ctx: ProviderContext, operation: str, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if operation == "send_text":
            result = await self.send_text(ctx, str(payload["to"]), str(payload["text"]))
            return {"provider_message_id": result.provider_message_id}
        return await super().execute(ctx, operation, payload)
