"""SendGrid v3 API (https://www.twilio.com/docs/sendgrid/api-reference).

Test connection: GET /v3/scopes (read-only) and check for `mail.send`.
Send: POST /v3/mail/send -> 202 Accepted with an X-Message-Id header.
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

BASE = "https://api.sendgrid.com/v3"

DEFINITION = IntegrationDefinition(
    key="sendgrid",
    name="SendGrid",
    description="Transactional email through the Twilio SendGrid v3 API.",
    category="email",
    provider="Twilio SendGrid",
    auth_type="api_key",
    capabilities=("send_email",),
    supported_scopes=("mail.send", "scopes.read"),
    required_scopes=("mail.send",),
    documentation_url="https://www.twilio.com/docs/sendgrid/api-reference",
    config_schema=(
        ConfigField(
            "from_address",
            "From address",
            "email",
            help="A verified sender or authenticated domain",
        ),
        ConfigField("from_name", "From name", "text", required=False),
        ConfigField("api_key", "API key", "password", secret=True),
    ),
)


class SendGridProvider(EmailProvider):
    key = "sendgrid"
    capabilities = frozenset({"send_email"})

    def validate_configuration(
        self, config: Mapping[str, Any], credentials: Mapping[str, str], settings: Settings
    ) -> None:
        safe_email(require_field(config, "from_address", "From address"))
        no_header_injection(config.get("from_name"))
        key = credentials.get("api_key")
        if key is not None and not key.startswith("SG."):
            raise ConfigurationInvalid("SendGrid API keys start with SG.", "api_key")

    def _headers(self, ctx: ProviderContext) -> dict[str, str]:
        return {"authorization": f"Bearer {credential(ctx.credentials, 'api_key')}"}

    async def health_check(self, ctx: ProviderContext) -> HealthResult:
        started = time.perf_counter()
        response = await ctx.http.request(
            "GET",
            f"{BASE}/scopes",
            headers=self._headers(ctx),
            max_bytes=256 * 1024,
            context=ctx.call,
        )
        response.ensure_success()
        scopes = response.json_object().get("scopes")
        if not isinstance(scopes, list):
            raise IntegrationError(
                "INVALID_RESPONSE",
                "SendGrid returned an unexpected response",
                kind="invalid_response",
            )
        latency = int((time.perf_counter() - started) * 1000)
        if "mail.send" not in scopes:
            raise IntegrationError(
                "MISSING_SCOPE", "The API key cannot send mail (mail.send)", kind="auth", status=403
            )
        return ok("API key verified (mail.send granted)", latency)

    async def send_email(self, ctx: ProviderContext, message: EmailMessage) -> SendResult:
        sender = message.from_address or str(ctx.config["from_address"])
        no_header_injection(message.subject, sender, message.reply_to, *message.to)
        from_block: dict[str, str] = {"email": safe_email(sender)}
        if ctx.config.get("from_name"):
            from_block["name"] = str(ctx.config["from_name"])[:100]
        content = [{"type": "text/plain", "value": message.text}]
        if message.html:
            content.append({"type": "text/html", "value": message.html})
        body: dict[str, Any] = {
            "personalizations": [{"to": [{"email": safe_email(t)} for t in message.to[:50]]}],
            "from": from_block,
            "subject": message.subject[:250],
            "content": content,
        }
        if message.reply_to:
            body["reply_to"] = {"email": safe_email(message.reply_to)}
        response = await ctx.http.request(
            "POST",
            f"{BASE}/mail/send",
            json_body=body,
            headers=self._headers(ctx),
            max_bytes=64 * 1024,
            context=ctx.call,
        )
        response.ensure_success()
        return SendResult((response.headers.get("x-message-id") or "")[:200] or None)
