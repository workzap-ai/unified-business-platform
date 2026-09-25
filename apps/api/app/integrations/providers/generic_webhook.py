"""Generic signed outbound webhook (Zapier / Make / n8n / custom endpoints)."""

import time
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.integrations.http import validate_outbound_url
from app.integrations.providers.base import credential, ok, require_field
from app.integrations.registry import (
    ConfigField,
    ConfigurationInvalid,
    HealthResult,
    IntegrationDefinition,
    OutboundWebhookProvider,
    ProviderContext,
)
from app.integrations.signing import SIGNATURE_HEADER, signature_header

DEFINITION = IntegrationDefinition(
    key="generic_webhook",
    name="Generic webhook",
    description=(
        "Send signed JSON events to any HTTPS endpoint, such as Zapier, Make, n8n or your "
        "own service."
    ),
    category="automation",
    provider="Generic",
    auth_type="signature_secret",
    capabilities=("send_webhook",),
    config_schema=(
        ConfigField("url", "Endpoint URL", "url", help="HTTPS only"),
        ConfigField(
            "signing_secret",
            "Signing secret",
            "password",
            secret=True,
            help="Used to sign each request (HMAC-SHA256). At least 16 characters.",
        ),
    ),
)


class GenericWebhookProvider(OutboundWebhookProvider):
    key = "generic_webhook"
    capabilities = frozenset({"send_webhook"})

    def validate_configuration(
        self, config: Mapping[str, Any], credentials: Mapping[str, str], settings: Settings
    ) -> None:
        url = require_field(config, "url", "Endpoint URL")
        if not url.startswith("https://") and settings.app_env == "production":
            raise ConfigurationInvalid("Endpoint URL must use HTTPS", "url")
        secret = credentials.get("signing_secret") or ""
        if secret and len(secret) < 16:
            raise ConfigurationInvalid(
                "Signing secret must be at least 16 characters", "signing_secret"
            )

    async def health_check(self, ctx: ProviderContext) -> HealthResult:
        # Safe test: validate the destination (scheme, DNS, SSRF policy) without sending.
        started = time.perf_counter()
        await validate_outbound_url(
            str(ctx.config.get("url", "")), ctx.settings, resolver=ctx.http.resolver
        )
        credential(ctx.credentials, "signing_secret")
        return ok(
            "Endpoint address verified (no event was sent)",
            int((time.perf_counter() - started) * 1000),
        )

    async def deliver(
        self, ctx: ProviderContext, event_type: str, event_id: str, body: bytes
    ) -> int:
        secret = credential(ctx.credentials, "signing_secret")
        response = await ctx.http.request(
            "POST",
            str(ctx.config["url"]),
            content=body,
            headers={
                "content-type": "application/json",
                SIGNATURE_HEADER: signature_header(secret, body, int(time.time())),
                "X-Platform-Event": event_type,
                "X-Platform-Delivery": str(uuid4()),
                "Idempotency-Key": event_id,
            },
            max_bytes=64 * 1024,
            context=ctx.call,
        )
        response.ensure_success()
        return response.status_code

    async def execute(
        self, ctx: ProviderContext, operation: str, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if operation != "send_webhook":
            return await super().execute(ctx, operation, payload)
        import json

        body = json.dumps(payload.get("body", {}), separators=(",", ":")).encode()
        status = await self.deliver(
            ctx,
            str(payload.get("event_type", "test")),
            str(payload.get("event_id", uuid4())),
            body,
        )
        return {"status": status}
