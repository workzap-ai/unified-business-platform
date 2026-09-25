"""Slack incoming webhooks (https://api.slack.com/messaging/webhooks).

The webhook URL itself is the credential, so it is stored encrypted. The connection test
validates the URL shape and destination only: Slack has no side-effect-free endpoint for
incoming webhooks, so no message is posted during a test.
"""

import re
import time
from collections.abc import Mapping
from typing import Any

from app.core.config import Settings
from app.integrations.errors import IntegrationError
from app.integrations.http import validate_outbound_url
from app.integrations.providers.base import credential, ok
from app.integrations.registry import (
    ConfigField,
    ConfigurationInvalid,
    HealthResult,
    IntegrationDefinition,
    MessagingProvider,
    ProviderContext,
    SendResult,
)

SLACK_URL = re.compile(
    r"^https://hooks\.slack\.com/services/[A-Za-z0-9]+/[A-Za-z0-9]+/[A-Za-z0-9]+$"
)

DEFINITION = IntegrationDefinition(
    key="slack",
    name="Slack",
    description="Post notifications (handoffs, failures, alerts) to a Slack channel.",
    category="collaboration",
    provider="Slack",
    auth_type="webhook_secret",
    capabilities=("send_message",),
    documentation_url="https://api.slack.com/messaging/webhooks",
    config_schema=(
        ConfigField(
            "webhook_url",
            "Incoming webhook URL",
            "password",
            secret=True,
            help="https://hooks.slack.com/services/…",
        ),
    ),
)


class SlackProvider(MessagingProvider):
    key = "slack"
    capabilities = frozenset({"send_message"})

    def validate_configuration(
        self, config: Mapping[str, Any], credentials: Mapping[str, str], settings: Settings
    ) -> None:
        url = credentials.get("webhook_url")
        if url is not None and not SLACK_URL.fullmatch(url):
            raise ConfigurationInvalid("Enter a Slack incoming webhook URL", "webhook_url")

    async def health_check(self, ctx: ProviderContext) -> HealthResult:
        started = time.perf_counter()
        url = credential(ctx.credentials, "webhook_url")
        if not SLACK_URL.fullmatch(url):
            raise IntegrationError("INVALID_CONFIGURATION", "The Slack webhook URL is invalid")
        await validate_outbound_url(url, ctx.settings, resolver=ctx.http.resolver)
        return ok(
            "Webhook URL is valid (no message was posted)",
            int((time.perf_counter() - started) * 1000),
        )

    async def send_text(self, ctx: ProviderContext, recipient: str, text: str) -> SendResult:
        url = credential(ctx.credentials, "webhook_url")
        response = await ctx.http.request(
            "POST", url, json_body={"text": text[:3000]}, max_bytes=4096, context=ctx.call
        )
        if response.status_code == 404 or response.content.strip() in (b"no_service",):
            raise IntegrationError(
                "INVALID_CREDENTIALS",
                "Slack no longer accepts this webhook URL",
                kind="auth",
                status=response.status_code,
            )
        response.ensure_success()
        return SendResult(None)

    async def execute(
        self, ctx: ProviderContext, operation: str, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if operation == "send_message":
            await self.send_text(ctx, "", str(payload.get("text", "")))
            return {"sent": True}
        return await super().execute(ctx, operation, payload)
