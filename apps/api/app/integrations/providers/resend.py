"""Resend email API (https://resend.com/docs/api-reference).

Test connection: GET /domains (read-only). A sending-only ("restricted") key answers 401
with name `restricted_api_key`; that still proves the key is valid, so the test reports
success with a note. Send: POST /emails with an Idempotency-Key header.
"""

import time
from collections.abc import Mapping
from typing import Any

from app.core.config import Settings
from app.integrations.errors import IntegrationError
from app.integrations.providers.base import (
    credential,
    no_header_injection,
    ok,
    require_field,
    safe_email,
)
from app.integrations.registry import (
    ConfigField,
    ConfigurationInvalid,
    EmailMessage,
    EmailProvider,
    HealthResult,
    IntegrationDefinition,
    ProviderContext,
    SendResult,
)

BASE = "https://api.resend.com"

DEFINITION = IntegrationDefinition(
    key="resend",
    name="Resend",
    description="Transactional email through the Resend API.",
    category="email",
    provider="Resend",
    auth_type="api_key",
    capabilities=("send_email",),
    documentation_url="https://resend.com/docs/api-reference/introduction",
    config_schema=(
        ConfigField(
            "from_address",
            "From address",
            "email",
            help="Must belong to a domain verified in Resend",
        ),
        ConfigField("api_key", "API key", "password", secret=True),
    ),
)


class ResendProvider(EmailProvider):
    key = "resend"
    capabilities = frozenset({"send_email"})

    def validate_configuration(
        self, config: Mapping[str, Any], credentials: Mapping[str, str], settings: Settings
    ) -> None:
        safe_email(require_field(config, "from_address", "From address"))
        key = credentials.get("api_key")
        if key is not None and not key.startswith("re_"):
            raise ConfigurationInvalid("Resend API keys start with re_", "api_key")

    def _headers(self, ctx: ProviderContext) -> dict[str, str]:
        return {"authorization": f"Bearer {credential(ctx.credentials, 'api_key')}"}

    async def health_check(self, ctx: ProviderContext) -> HealthResult:
        started = time.perf_counter()
        response = await ctx.http.request(
            "GET",
            f"{BASE}/domains",
            headers=self._headers(ctx),
            max_bytes=256 * 1024,
            context=ctx.call,
        )
        latency = int((time.perf_counter() - started) * 1000)
        if response.status_code == 401:
            body = response.json() if response.content else None
            if isinstance(body, dict) and body.get("name") == "restricted_api_key":
                return ok("API key verified (sending-only key)", latency)
        response.ensure_success()
        data = response.json_object()
        domains = data.get("data", []) if isinstance(data.get("data"), list) else []
        verified = sum(1 for d in domains if isinstance(d, dict) and d.get("status") == "verified")
        return ok(f"API key verified ({verified} verified domain(s))", latency)

    async def send_email(self, ctx: ProviderContext, message: EmailMessage) -> SendResult:
        sender = message.from_address or str(ctx.config["from_address"])
        no_header_injection(message.subject, sender, message.reply_to, *message.to)
        body: dict[str, Any] = {
            "from": safe_email(sender),
            "to": [safe_email(t) for t in message.to[:50]],
            "subject": message.subject[:250],
            "text": message.text,
        }
        if message.html:
            body["html"] = message.html
        if message.reply_to:
            body["reply_to"] = safe_email(message.reply_to)
        headers = self._headers(ctx)
        if message.idempotency_key:
            headers["idempotency-key"] = message.idempotency_key[:256]
        response = await ctx.http.request(
            "POST",
            f"{BASE}/emails",
            json_body=body,
            headers=headers,
            max_bytes=64 * 1024,
            context=ctx.call,
        )
        response.ensure_success()
        message_id = response.json_object().get("id")
        if not isinstance(message_id, str):
            raise IntegrationError(
                "INVALID_RESPONSE",
                "Resend returned an unexpected response",
                kind="invalid_response",
            )
        return SendResult(message_id[:200])
