"""Capture of platform emails sent during a test.

The API never returns an invitation link (SEC-1), so tests read it from the email the
mailbox owner would get."""

import re
from typing import Any

MESSAGES: list[Any] = []
_TOKEN = re.compile(r"accept-invite\?token=([A-Za-z0-9_-]+)")


def invite_token(email: str) -> str:
    for message in reversed(MESSAGES):
        if email in [a.lower() for a in message.to]:
            found = _TOKEN.search(message.text)
            if found:
                return found.group(1)
    raise AssertionError(f"no invitation email with a link was sent to {email}")


def sent_to(email: str) -> list[Any]:
    return [m for m in MESSAGES if email in [a.lower() for a in m.to]]
