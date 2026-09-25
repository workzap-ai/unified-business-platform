"""Platform email: centralized templates and an EmailService that picks a transport.

Templates are fixed in code (plain text + escaped HTML). Callers pass variables; every
variable is HTML-escaped and length-limited, links must be http(s). Routes never accept
arbitrary HTML.

Transport selection: the workspace's connected email integration (smtp, resend,
sendgrid; most recently connected wins) or, if none, the platform SMTP server from
settings (PLATFORM_SMTP_*). Without either, sending fails with EMAIL_NOT_CONFIGURED.
"""

import html
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from string import Template

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations.catalog import REGISTRY
from app.integrations.http import CallContext, OutboundClient
from app.integrations.providers.smtp import SmtpProvider
from app.integrations.registry import EmailMessage, EmailProvider, ProviderContext, SendResult
from app.integrations.runtime import ConnectionRuntime
from app.modules.integrations.models import IntegrationConnection
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

EMAIL_KEYS = ("smtp", "resend", "sendgrid")


@dataclass(frozen=True, slots=True)
class EmailTemplate:
    subject: str
    text: str
    html: str
    variables: frozenset[str]
    links: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str
    text: str
    html: str


_LAYOUT = (
    '<!doctype html><html><body style="font-family:Arial,sans-serif;color:#111">'
    '$body<p style="color:#666;font-size:12px">Sent by $workspace</p></body></html>'
)

TEMPLATES: dict[str, EmailTemplate] = {
    "invitation": EmailTemplate(
        subject="You're invited to $workspace",
        text="Hello $name,\n\n$inviter invited you to join $workspace.\n"
        "Accept the invitation: $link\n\nIf you did not expect this, ignore this email.",
        html="<p>Hello $name,</p><p>$inviter invited you to join <b>$workspace</b>.</p>"
        '<p><a href="$link">Accept the invitation</a></p>'
        "<p>If you did not expect this, ignore this email.</p>",
        variables=frozenset({"name", "inviter", "workspace", "link"}),
        links=frozenset({"link"}),
    ),
    "handoff_notification": EmailTemplate(
        subject="Conversation needs attention: $customer",
        text="A conversation with $customer was handed off to your team.\n"
        "Reason: $reason\nOpen it: $link",
        html="<p>A conversation with <b>$customer</b> was handed off to your team.</p>"
        '<p>Reason: $reason</p><p><a href="$link">Open the conversation</a></p>',
        variables=frozenset({"customer", "reason", "link", "workspace"}),
        links=frozenset({"link"}),
    ),
    "integration_failure": EmailTemplate(
        subject="Integration needs attention: $integration",
        text="The $integration connection in $workspace is failing.\n"
        "Last error: $error\nReview it: $link",
        html="<p>The <b>$integration</b> connection in $workspace is failing.</p>"
        '<p>Last error: $error</p><p><a href="$link">Review the connection</a></p>',
        variables=frozenset({"integration", "workspace", "error", "link"}),
        links=frozenset({"link"}),
    ),
    "system_alert": EmailTemplate(
        subject="[$severity] $title",
        text="$title\n\n$message",
        html="<p><b>$title</b></p><p>$message</p>",
        variables=frozenset({"severity", "title", "message", "workspace"}),
    ),
}


def render_template(name: str, variables: Mapping[str, str]) -> RenderedEmail:
    template = TEMPLATES.get(name)
    if template is None:
        raise BusinessRuleViolation("UNKNOWN_TEMPLATE", "Unknown email template")
    unknown = set(variables) - template.variables
    if unknown:
        raise BusinessRuleViolation("INVALID_TEMPLATE_VARIABLES", "Unknown template variables")
    values: dict[str, str] = {key: "" for key in template.variables}
    values["workspace"] = "your workspace"
    for key, value in variables.items():
        text = str(value).replace("\r", " ").replace("\n", " ").strip()[:500]
        if key in template.links and text and not text.startswith(("https://", "http://")):
            raise BusinessRuleViolation("INVALID_TEMPLATE_VARIABLES", "Links must be http(s)")
        values[key] = text
    escaped = {k: html.escape(v, quote=True) for k, v in values.items()}
    subject = Template(template.subject).safe_substitute(values)[:200]
    body = Template(template.html).safe_substitute(escaped)
    return RenderedEmail(
        subject=subject.replace("\r", " ").replace("\n", " "),
        text=Template(template.text).safe_substitute(values),
        html=Template(_LAYOUT).safe_substitute(body=body, workspace=escaped["workspace"]),
    )


class EmailService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        http: OutboundClient,
        scope: WorkspaceScope,
        *,
        redis: object = None,
    ) -> None:
        self.session, self.settings, self.http, self.scope = session, settings, http, scope
        self.redis = redis

    async def _connection(self) -> IntegrationConnection | None:
        found: IntegrationConnection | None = await self.session.scalar(
            select(IntegrationConnection)
            .where(
                IntegrationConnection.tenant_id == self.scope.tenant_id,
                IntegrationConnection.environment_id == self.scope.environment_id,
                IntegrationConnection.integration_key.in_(EMAIL_KEYS),
                IntegrationConnection.status.in_(("connected", "degraded")),
            )
            .order_by(IntegrationConnection.connected_at.desc().nulls_last())
            .limit(1)
        )
        return found

    def _platform_context(self) -> ProviderContext:
        s = self.settings
        if not s.platform_smtp_host or not s.platform_smtp_from:
            raise BusinessRuleViolation(
                "EMAIL_NOT_CONFIGURED", "Email sending is not configured", 503
            )
        return ProviderContext(
            settings=s,
            http=self.http,
            config={
                "host": s.platform_smtp_host,
                "port": s.platform_smtp_port,
                "security": s.platform_smtp_security,
                "username": s.platform_smtp_username,
                "from_address": s.platform_smtp_from,
            },
            credentials={"password": s.platform_smtp_password.get_secret_value()}
            if s.platform_smtp_password
            else {},
            call=CallContext(request_id=self.scope.request_id),
        )

    async def send(self, message: EmailMessage) -> SendResult:
        connection = await self._connection()
        if connection is not None:
            provider = REGISTRY.provider(connection.integration_key)
            if isinstance(provider, EmailProvider):
                runtime = ConnectionRuntime(
                    self.session, self.settings, self.http, redis=self.redis
                )

                async def operation(ctx: ProviderContext) -> SendResult:
                    return await provider.send_email(ctx, message)

                result, _latency = await runtime.call(
                    connection,
                    operation,
                    kind="send",
                    call=CallContext(request_id=self.scope.request_id),
                )
                return result
        return await SmtpProvider().send_email(self._platform_context(), message)

    async def send_template(
        self,
        template: str,
        to: Sequence[str],
        variables: Mapping[str, str],
        *,
        idempotency_key: str | None = None,
    ) -> SendResult:
        rendered = render_template(template, variables)
        return await self.send(
            EmailMessage(
                to=list(to),
                subject=rendered.subject,
                text=rendered.text,
                html=rendered.html,
                idempotency_key=idempotency_key,
            )
        )
