"""Calendar invitations (.ics) and the email attachment path they travel on."""

import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from test_integrations_adapters import RESEND_CREDS, ctx

from app.integrations.email import calendar_attachments
from app.integrations.providers.resend import ResendProvider
from app.integrations.providers.smtp import SmtpProvider
from app.integrations.registry import EmailAttachment, EmailMessage
from app.modules.pi_saas import calendar_invite


def _ics(summary: str = "Suit fitting with Noor Tailors, Lahore; bring fabric") -> str:
    return calendar_invite.booking_ics(
        uuid4(),
        datetime(2026, 10, 6, 10, 30, tzinfo=UTC),
        datetime(2026, 10, 6, 11, 0, tzinfo=UTC),
        summary,
        "Line one\nLine two, with commas; and semicolons\\ " + "x" * 200,
        sequence=5,
        now=datetime(2026, 9, 30, 0, 0, tzinfo=UTC),
    )


def test_ics_is_valid_rfc5545():
    ics = _ics()
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert "\n" not in ics.replace("\r\n", "")  # CRLF line endings only
    assert "DTSTART:20261006T103000Z" in ics and "DTEND:20261006T110000Z" in ics
    assert "METHOD:PUBLISH" in ics and "SEQUENCE:5" in ics
    unfolded = ics.replace("\r\n ", "")
    assert "SUMMARY:Suit fitting with Noor Tailors\\, Lahore\\; bring fabric" in unfolded
    assert "Line one\\nLine two\\, with commas\\; and semicolons\\\\ " in unfolded
    for line in ics.split("\r\n"):
        assert len(line.encode()) <= 75  # folded


def test_folding_never_splits_multibyte_characters():
    ics = _ics("قیمت اور وقت " * 20)
    for line in ics.split("\r\n"):
        line.encode().decode()  # every physical line is valid UTF-8
        assert len(line.encode()) <= 75


def test_only_small_calendar_files_can_be_attached():
    good = calendar_invite.attachment(_ics())
    assert calendar_attachments([good]) == (
        EmailAttachment(good["filename"], good["content_type"], good["content"]),
    )
    bad = [
        {**good, "filename": "invoice.exe"},
        {**good, "content_type": "application/octet-stream"},
        {**good, "content": "MZ\x90\x00"},
        {**good, "content": "BEGIN:VCALENDAR" + "x" * 70_000},
        "not a dict",
    ]
    assert calendar_attachments(bad) == ()
    assert len(calendar_attachments([good, good, good])) == 2
    assert calendar_attachments(None) == ()


async def test_providers_send_the_attachment():
    content = _ics()
    message = EmailMessage(
        to=["amina@example.com"],
        subject="Booking confirmed",
        text="See you soon",
        attachments=(EmailAttachment("booking.ics", calendar_invite.CONTENT_TYPE, content),),
    )
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "email_1"})

    await ResendProvider().send_email(
        ctx(handler, {"from_address": "bookings@example.com"}, RESEND_CREDS), message
    )
    [attached] = seen["body"]["attachments"]
    assert attached["filename"] == "booking.ics"
    assert base64.b64decode(attached["content"]).decode() == content
    mime = SmtpProvider().build(ctx(handler, {"from_address": "bookings@example.com"}), message)
    parts = [p for p in mime.iter_attachments()]
    assert [p.get_filename() for p in parts] == ["booking.ics"]
    assert parts[0].get_content_type() == "text/calendar"
