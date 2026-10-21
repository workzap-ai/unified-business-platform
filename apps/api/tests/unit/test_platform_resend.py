"""Platform email with Resend's key goes through Resend's HTTPS API, not SMTP (hosts
like Railway block SMTP ports). Other SMTP servers still use SMTP."""

from types import SimpleNamespace

from pydantic import SecretStr

from app.integrations import email
from app.integrations.registry import EmailMessage, SendResult


def settings(host: str, password: str):
    return SimpleNamespace(
        platform_smtp_host=host,
        platform_smtp_password=SecretStr(password),
        platform_smtp_from="pi <onboarding@resend.dev>",
        platform_smtp_port=587,
        platform_smtp_security="starttls",
        platform_smtp_username="resend",
    )


async def test_resend_key_sends_through_the_api(monkeypatch):
    calls = []

    async def resend(self, ctx, message):
        calls.append(("resend", ctx.credentials["api_key"], message.from_address))
        return SendResult(provider_message_id="x")

    async def smtp(self, ctx, message):
        calls.append(("smtp",))
        return SendResult(provider_message_id="y")

    monkeypatch.setattr(email.ResendProvider, "send_email", resend)
    monkeypatch.setattr(email.SmtpProvider, "send_email", smtp)
    message = EmailMessage(to=["a@example.com"], subject="Hi", text="Hi")

    await email.send_platform_email(settings("smtp.resend.com", "re_abc123"), None, message)
    assert calls[-1] == ("resend", "re_abc123", "onboarding@resend.dev")
    await email.send_platform_email(settings("smtp.gmail.com", "app-pass"), None, message)
    assert calls[-1] == ("smtp",)
