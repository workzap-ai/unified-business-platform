"""Platform email: centralized templates and an EmailService that picks a transport.

Templates are fixed in code (plain text + escaped HTML). Callers pass variables; every
variable is HTML-escaped and length-limited, links must be http(s). Routes never accept
arbitrary HTML.

Transport selection: the workspace's connected email integration (smtp, resend,
sendgrid; most recently connected wins) or, if none, the platform SMTP server from
settings (PLATFORM_SMTP_*). Without either, sending fails with EMAIL_NOT_CONFIGURED.
"""

import html
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from string import Template
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations.catalog import REGISTRY
from app.integrations.http import CallContext, OutboundClient
from app.integrations.providers.smtp import SmtpProvider
from app.integrations.registry import (
    EmailAttachment,
    EmailMessage,
    EmailProvider,
    ProviderContext,
    SendResult,
)
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
    # Transactional message from a business to its own customer (booking confirmations).
    "customer_notice": EmailTemplate(
        subject="$title",
        text="Hello $name,\n\n$message\n\n$workspace",
        html="<p>Hello $name,</p><p>$message</p>",
        variables=frozenset({"name", "title", "message", "workspace"}),
    ),
    "system_alert": EmailTemplate(
        subject="[$severity] $title",
        text="$title\n\n$message",
        html="<p><b>$title</b></p><p>$message</p>",
        variables=frozenset({"severity", "title", "message", "workspace"}),
    ),
    # Account-level (not workspace-scoped): self-service password reset.
    "password_reset": EmailTemplate(
        subject="Reset your password",
        text="Hello $name,\n\nUse this link to choose a new password: $link\n"
        "This link expires in $minutes minutes and can only be used once.\n\n"
        "If you did not request this, ignore this email; your password stays unchanged.",
        html="<p>Hello $name,</p><p><a href=\"$link\">Choose a new password</a></p>"
        "<p>This link expires in $minutes minutes and can only be used once.</p>"
        "<p>If you did not request this, ignore this email; your password stays unchanged.</p>",
        variables=frozenset({"name", "link", "minutes", "workspace"}),
        links=frozenset({"link"}),
    ),
    "verify_email": EmailTemplate(
        subject="Confirm your email address",
        text="Hello $name,\n\nConfirm this is your email address: $link\n"
        "This link expires in $hours hours.\n\n"
        "If you did not create this account, ignore this email.",
        html='<p>Hello $name,</p><p><a href="$link">Confirm your email address</a></p>'
        "<p>This link expires in $hours hours.</p>"
        "<p>If you did not create this account, ignore this email.</p>",
        variables=frozenset({"name", "link", "hours", "workspace"}),
        links=frozenset({"link"}),
    ),
    # Account-level (not workspace-scoped): Pi subscription billing notices, sent from
    # the platform SMTP server, the same as password reset/verify email — a business's
    # own connected email integration is for messaging ITS customers, not for the
    # platform billing that business.
    "pi_payment_receipt": EmailTemplate(
        subject="Payment received — $business",
        text="Hello $name,\n\nWe received your payment for $business.\n\n"
        "Plan: $plan\nAmount: $amount\nReceipt: $receipt\nService period: $period\n\n"
        "Thank you for your business.",
        html="<p>Hello $name,</p><p>We received your payment for <b>$business</b>.</p>"
        "<ul><li>Plan: $plan</li><li>Amount: $amount</li><li>Receipt: $receipt</li>"
        "<li>Service period: $period</li></ul><p>Thank you for your business.</p>",
        variables=frozenset(
            {"name", "business", "plan", "amount", "receipt", "period", "workspace"}
        ),
    ),
    "pi_billing_past_due": EmailTemplate(
        subject="Action needed: update your Pi payment details",
        text="Hello $name,\n\nYour Pi subscription payment is past due. Update your "
        "payment details to keep Pi replying to your customers: $link\n\n"
        "If you already paid, you can ignore this message.",
        html="<p>Hello $name,</p><p>Your Pi subscription payment is past due. Update "
        "your payment details to keep Pi replying to your customers.</p>"
        '<p><a href="$link">Update payment details</a></p>'
        "<p>If you already paid, you can ignore this message.</p>",
        variables=frozenset({"name", "link", "workspace"}),
        links=frozenset({"link"}),
    ),
    "pi_invoice_paid": EmailTemplate(
        subject="Payment confirmed — $business",
        text="Hello $name,\n\nWe've received your payment of $amount for $business. "
        "Your Pi subscription is up to date.\n\nView your billing: $link",
        html="<p>Hello $name,</p><p>We've received your payment of <b>$amount</b> for "
        "<b>$business</b>. Your Pi subscription is up to date.</p>"
        '<p><a href="$link">View your billing</a></p>',
        variables=frozenset({"name", "business", "amount", "link", "workspace"}),
        links=frozenset({"link"}),
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


def platform_smtp_context(
    settings: Settings, http: OutboundClient, request_id: str | None = None
) -> ProviderContext:
    if not settings.platform_smtp_host or not settings.platform_smtp_from:
        raise BusinessRuleViolation("EMAIL_NOT_CONFIGURED", "Email sending is not configured", 503)
    return ProviderContext(
        settings=settings,
        http=http,
        config={
            "host": settings.platform_smtp_host,
            "port": settings.platform_smtp_port,
            "security": settings.platform_smtp_security,
            "username": settings.platform_smtp_username,
            "from_address": settings.platform_smtp_from,
        },
        credentials={"password": settings.platform_smtp_password.get_secret_value()}
        if settings.platform_smtp_password
        else {},
        call=CallContext(request_id=request_id),
    )


async def send_platform_template(
    settings: Settings,
    http: OutboundClient,
    template: str,
    to: Sequence[str],
    variables: Mapping[str, str],
    *,
    request_id: str | None = None,
) -> SendResult:
    """Account-level email that always goes out from the platform SMTP server, never a
    workspace's connected integration: used before any tenant is in scope (password
    reset, other auth-only notices)."""
    rendered = render_template(template, variables)
    message = EmailMessage(
        to=list(to), subject=rendered.subject, text=rendered.text, html=rendered.html
    )
    ctx = platform_smtp_context(settings, http, request_id)
    return await SmtpProvider().send_email(ctx, message)


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
        return platform_smtp_context(self.settings, self.http, self.scope.request_id)

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


CALENDAR_FILE = re.compile(r"[A-Za-z0-9_.-]{1,60}\.ics")
MAX_ATTACHMENT_CHARS = 64 * 1024


def calendar_attachments(raw: Any) -> tuple[EmailAttachment, ...]:
    """Attachments an operation may carry: at most two small iCalendar files. Anything
    else is dropped, so an operation input can never smuggle arbitrary files."""
    if not isinstance(raw, list):
        return ()
    out: list[EmailAttachment] = []
    for item in raw[:2]:
        if not isinstance(item, dict):
            continue
        name, kind, content = item.get("filename"), item.get("content_type"), item.get("content")
        if (
            isinstance(name, str)
            and CALENDAR_FILE.fullmatch(name)
            and isinstance(kind, str)
            and kind.startswith("text/calendar")
            and isinstance(content, str)
            and len(content) <= MAX_ATTACHMENT_CHARS
            and content.startswith("BEGIN:VCALENDAR")
        ):
            out.append(EmailAttachment(filename=name, content_type=kind[:80], content=content))
    return tuple(out)
