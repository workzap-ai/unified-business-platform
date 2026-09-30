"""A calendar invitation (.ics, RFC 5545) for a confirmed booking.

It is sent with the booking confirmation email so the customer can add the
appointment to Google Calendar, Outlook or Apple Calendar in one tap. METHOD:PUBLISH
is used (an "add to calendar" file, not a meeting request that expects RSVP replies
the platform could not receive). Times are written in UTC so every calendar app shows
the right local time. The UID is stable per booking, so a re-sent confirmation after a
change updates the same calendar entry.
"""

from datetime import UTC, datetime
from uuid import UUID

FILENAME = "booking.ics"
CONTENT_TYPE = "text/calendar; charset=utf-8; method=PUBLISH"


def _text(value: str) -> str:
    """Escape TEXT values (RFC 5545 section 3.3.11)."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _fold(line: str) -> str:
    """Fold content lines longer than 75 octets (section 3.1), never splitting UTF-8."""
    out: list[str] = []
    current = ""
    for char in line:
        limit = 75 if not out else 74  # continuation lines start with a space
        if len((current + char).encode()) > limit:
            out.append(current)
            current = char
        else:
            current += char
    out.append(current)
    return "\r\n ".join(out)


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def booking_ics(
    booking_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
    summary: str,
    description: str,
    sequence: int = 0,
    now: datetime | None = None,
) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Workzap//Pi WhatsApp//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:booking-{booking_id}@pi.workzap",
        f"SEQUENCE:{max(0, sequence)}",
        f"DTSTAMP:{_utc(now or datetime.now(UTC))}",
        f"DTSTART:{_utc(starts_at)}",
        f"DTEND:{_utc(ends_at)}",
        f"SUMMARY:{_text(summary[:200])}",
        f"DESCRIPTION:{_text(description[:1000])}",
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def attachment(content: str) -> dict[str, str]:
    """The integration-operation form of the file (validated again at send time)."""
    return {"filename": FILENAME, "content_type": CONTENT_TYPE, "content": content}
