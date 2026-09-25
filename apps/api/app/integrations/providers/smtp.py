"""SMTP email (stdlib smtplib + ssl, run in a worker thread with timeouts).

Test connection: connect, EHLO, STARTTLS (or implicit TLS), EHLO, AUTH, QUIT. No message
is sent. The destination host is checked with the same public-address policy as HTTP
egress (resolved addresses must be public unicast); ports are limited to 25/465/587/2525.
Plaintext SMTP ("none") is refused in production.
"""

import asyncio
import ipaddress
import smtplib
import ssl
import time
from collections.abc import Mapping
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, make_msgid
from typing import Any

from app.core.config import Settings
from app.integrations.errors import IntegrationError, OutboundUrlRejected
from app.integrations.http import Resolver, forbidden_reason, system_resolver
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

SMTP_PORTS = frozenset({25, 465, 587, 2525})

DEFINITION = IntegrationDefinition(
    key="smtp",
    name="SMTP email",
    description="Send workspace email through your own SMTP server.",
    category="email",
    provider="SMTP",
    auth_type="basic_auth",
    capabilities=("send_email",),
    config_schema=(
        ConfigField("host", "SMTP host", "text"),
        ConfigField("port", "Port", "number", help="587 (STARTTLS) or 465 (TLS)"),
        ConfigField(
            "security",
            "Security",
            "select",
            options=(
                ("starttls", "STARTTLS"),
                ("ssl", "Implicit TLS"),
                ("none", "None (development only)"),
            ),
        ),
        ConfigField("username", "Username", "text", required=False),
        ConfigField("from_address", "From address", "email"),
        ConfigField("from_name", "From name", "text", required=False),
        ConfigField("password", "Password", "password", secret=True, required=False),
    ),
)


async def check_smtp_host(
    host: str, port: int, settings: Settings, resolver: Resolver | None = None
) -> None:
    if port not in SMTP_PORTS:
        raise OutboundUrlRejected("non-standard port")
    if settings.app_env != "production" and host in settings.outbound_http_allowlist:
        return
    try:
        literal = ipaddress.ip_address(host)
        answers = [str(literal)]
    except ValueError:
        try:
            async with asyncio.timeout(settings.outbound_connect_timeout_seconds):
                answers = await (resolver or system_resolver)(host, port)
        except (OSError, TimeoutError, UnicodeError):
            raise OutboundUrlRejected("host could not be resolved") from None
    if not answers:
        raise OutboundUrlRejected("host could not be resolved")
    for answer in answers:
        reason = forbidden_reason(ipaddress.ip_address(answer.split("%", 1)[0]))
        if reason:
            raise OutboundUrlRejected(f"host resolves to a {reason}")


class SmtpProvider(EmailProvider):
    key = "smtp"
    capabilities = frozenset({"send_email"})

    def validate_configuration(
        self, config: Mapping[str, Any], credentials: Mapping[str, str], settings: Settings
    ) -> None:
        require_field(config, "host", "SMTP host")
        try:
            port = int(config.get("port", 0))
        except (TypeError, ValueError):
            raise ConfigurationInvalid("Port must be a number", "port") from None
        if port not in SMTP_PORTS:
            raise ConfigurationInvalid("Use port 25, 465, 587 or 2525", "port")
        security = config.get("security", "starttls")
        if security not in {"starttls", "ssl", "none"}:
            raise ConfigurationInvalid("Choose a security mode", "security")
        if security == "none" and settings.app_env == "production":
            raise ConfigurationInvalid("Unencrypted SMTP is not allowed", "security")
        safe_email(require_field(config, "from_address", "From address"))
        no_header_injection(config.get("from_name"), config.get("username"))

    def _params(self, ctx: ProviderContext) -> tuple[str, int, str]:
        return (
            str(ctx.config["host"]).strip().lower(),
            int(ctx.config["port"]),
            str(ctx.config.get("security", "starttls")),
        )

    def _session(
        self, ctx: ProviderContext, host: str, port: int, security: str, timeout: float
    ) -> smtplib.SMTP:
        context = ssl.create_default_context()
        client: smtplib.SMTP
        if security == "ssl":
            client = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
        else:
            client = smtplib.SMTP(host, port, timeout=timeout)
        try:
            client.ehlo()
            if security == "starttls":
                client.starttls(context=context)
                client.ehlo()
            username = ctx.config.get("username")
            if username:
                client.login(str(username), credential(ctx.credentials, "password"))
        except BaseException:
            try:
                client.close()
            finally:
                pass
            raise
        return client

    async def _run(self, ctx: ProviderContext, action: str, message: MimeMessage | None) -> None:
        host, port, security = self._params(ctx)
        if security == "none" and ctx.settings.app_env == "production":
            raise IntegrationError("INVALID_CONFIGURATION", "Unencrypted SMTP is not allowed")
        await check_smtp_host(host, port, ctx.settings, ctx.http.resolver)
        timeout = ctx.settings.platform_smtp_timeout_seconds

        def work() -> None:
            client = self._session(ctx, host, port, security, timeout)
            try:
                if message is not None:
                    client.send_message(message)
            finally:
                try:
                    client.quit()
                except smtplib.SMTPException:
                    client.close()

        try:
            async with asyncio.timeout(timeout * 3):
                await asyncio.to_thread(work)
        except smtplib.SMTPAuthenticationError:
            raise IntegrationError(
                "INVALID_CREDENTIALS", "The SMTP server rejected the login", kind="auth"
            ) from None
        except smtplib.SMTPRecipientsRefused:
            raise IntegrationError(
                "RECIPIENT_REFUSED", "The SMTP server refused the recipient"
            ) from None
        except (smtplib.SMTPNotSupportedError, ssl.SSLError):
            raise IntegrationError(
                "TLS_FAILED", "Secure connection to the SMTP server failed"
            ) from None
        except TimeoutError:
            raise IntegrationError(
                "PROVIDER_TIMEOUT",
                "The SMTP server did not respond in time",
                kind="retryable" if message is None else "ambiguous",
            ) from None
        except (smtplib.SMTPException, OSError):
            raise IntegrationError(
                "PROVIDER_UNREACHABLE", "The SMTP server could not be reached", kind="retryable"
            ) from None

    async def health_check(self, ctx: ProviderContext) -> HealthResult:
        started = time.perf_counter()
        await self._run(ctx, "check", None)
        return ok(
            "SMTP login verified (no email was sent)", int((time.perf_counter() - started) * 1000)
        )

    def build(self, ctx: ProviderContext, message: EmailMessage) -> MimeMessage:
        sender = message.from_address or str(ctx.config["from_address"])
        no_header_injection(message.subject, sender, message.reply_to, *message.to)
        mime = MimeMessage()
        name = ctx.config.get("from_name")
        mime["From"] = formataddr((str(name), safe_email(sender))) if name else safe_email(sender)
        mime["To"] = ", ".join(safe_email(t) for t in message.to[:50])
        mime["Subject"] = message.subject[:250]
        mime["Message-ID"] = make_msgid()
        if message.reply_to:
            mime["Reply-To"] = safe_email(message.reply_to)
        mime.set_content(message.text)
        if message.html:
            mime.add_alternative(message.html, subtype="html")
        return mime

    async def send_email(self, ctx: ProviderContext, message: EmailMessage) -> SendResult:
        mime = self.build(ctx, message)
        await self._run(ctx, "send", mime)
        return SendResult(str(mime["Message-ID"]))
