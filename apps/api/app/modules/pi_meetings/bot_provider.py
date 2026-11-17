"""The meeting-bot provider: who actually joins the Zoom, Meet or Teams call for pi.

pi's own code never talks to a call. A provider (Recall.ai first) runs a bot that joins the link,
sends us the words as they are said, and leaves. Everything else in the platform (the transcript,
review, the Problem Map) only sees transcript lines, so a different provider can be put behind the
same interface (`BotProvider`) without touching any of it.

What lives here: the link check (only real Zoom, Meet and Teams links reach a provider), the
provider interface, the Recall.ai adapter, the mapping of the provider's status words to ours, and
the check of the signature the provider puts on every callback.

Facts about Recall.ai below come from its documentation (docs.recall.ai) as read on 2026-11-17:
create `POST /api/v1/bot/`, leave `POST /api/v1/bot/{id}/leave_call/`,
retrieve `GET /api/v1/bot/{id}/`,
`Authorization: Token <key>`, one base URL per region, callbacks signed with HMAC-SHA256 over
`webhook-id.webhook-timestamp.body` (secret `whsec_...`). Not yet exercised against a live account.
"""

import base64
import hashlib
import hmac
import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

BOT_NAME = "pi (AI) - Workzap notetaker"  # what everyone in the call sees: it says it is an AI
TIMEOUT = 15.0

_ZOOM = re.compile(r"^/(j|wc/join|w|s)/[\w-]{5,}", re.I)
_MEET = re.compile(r"^/[a-z]{3,4}-[a-z]{4}-[a-z]{3,4}/?$", re.I)
_TEAMS = re.compile(r"^/(l/meetup-join|meet)/", re.I)
_TEAMS_HOSTS = frozenset({"teams.microsoft.com", "teams.live.com"})


class BotProviderError(Exception):
    """The provider refused or could not be reached. `code` is ours, `message` is safe to show: it
    never carries the provider's reply or any key."""

    def __init__(self, code: str, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class MeetingLink:
    source: str  # zoom | meet | teams
    host: str


def parse_meeting_link(url: str) -> MeetingLink | None:
    """A real Zoom, Google Meet or Teams invitation over https, or None. Anything else (another
    site, an address with a login in it, a made-up port) is never sent to a provider."""
    try:
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or not host or parts.username or parts.password:
        return None
    if port not in (None, 443):
        return None
    if (host == "zoom.us" or host.endswith((".zoom.us", ".zoomgov.com"))) and _ZOOM.match(
        parts.path
    ):
        return MeetingLink("zoom", host)
    if host == "meet.google.com" and _MEET.match(parts.path):
        return MeetingLink("meet", host)
    if host in _TEAMS_HOSTS and _TEAMS.match(parts.path):
        return MeetingLink("teams", host)
    return None


def link_hash(url: str) -> str:
    """Stops the same call being joined twice. The link (it may hold a passcode) is not kept."""
    parts = urlsplit(url.strip())
    key = f"{(parts.hostname or '').lower()}{parts.path.rstrip('/')}"
    return hashlib.sha256(key.encode()).hexdigest()


# the provider's words for where a bot is -> ours (see BOT_STATUSES)
_STATUS = {
    "joining_call": "joining",
    "in_waiting_room": "waiting",
    "in_call_not_recording": "in_call",
    "recording_permission_allowed": "in_call",
    "recording_permission_denied": "denied",
    "in_call_recording": "recording",
    "call_ended": "ended",
    "done": "done",
    "fatal": "failed",
}


def our_status(code: str) -> str | None:
    """Ours for the provider's `code` (with or without the `bot.` prefix); None when it is a word we
    do not track (breakout rooms and any new one the provider adds)."""
    return _STATUS.get(code.removeprefix("bot."))


class BotProvider(Protocol):
    name: str

    async def join(
        self, *, meeting_url: str, bot_name: str, webhook_url: str, language: str
    ) -> str:
        """Send a bot to the call; returns the provider's id for it."""

    async def leave(self, bot_id: str) -> None:
        """Ask the bot to leave the call now (it cannot be sent back into that visit)."""

    async def status(self, bot_id: str) -> tuple[str, str] | None:
        """(code, sub_code) of the bot's latest state, or None when it has none yet."""


class RecallProvider:
    name = "recall"

    def __init__(self, http: httpx.AsyncClient, api_key: str, region: str) -> None:
        self._http = http
        self._key = api_key
        self._base = f"https://{region}.recall.ai"

    async def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        try:
            reply = await self._http.request(
                method,
                f"{self._base}{path}",
                json=body,
                headers={"Authorization": f"Token {self._key}"},
                timeout=TIMEOUT,
            )
        except httpx.HTTPError:
            logger.warning("recall_unreachable", extra={"path": path})
            raise BotProviderError(
                "BOT_PROVIDER_UNREACHABLE", "The meeting bot service could not be reached"
            ) from None
        if reply.status_code in (401, 403):
            raise BotProviderError(
                "BOT_PROVIDER_KEY_REJECTED", "The meeting bot service did not accept our key", 503
            )
        if reply.status_code == 429:
            raise BotProviderError(
                "BOT_PROVIDER_BUSY", "The meeting bot service is busy; try again shortly", 429
            )
        if reply.status_code >= 400:
            logger.warning("recall_refused", extra={"path": path, "status": reply.status_code})
            raise BotProviderError(
                "BOT_PROVIDER_REFUSED", "The meeting bot service could not do that", 502
            )
        if not reply.content:
            return {}
        try:
            return reply.json()
        except ValueError:
            return {}

    async def join(
        self, *, meeting_url: str, bot_name: str, webhook_url: str, language: str
    ) -> str:
        reply = await self._call(
            "POST",
            "/api/v1/bot/",
            {
                "meeting_url": meeting_url,
                "bot_name": bot_name,
                "recording_config": {
                    "transcript": {
                        "provider": {
                            "recallai_streaming": {
                                "mode": "prioritize_low_latency",
                                "language_code": language or "en",
                            }
                        }
                    },
                    "realtime_endpoints": [
                        {"type": "webhook", "url": webhook_url, "events": ["transcript.data"]}
                    ],
                },
            },
        )
        bot_id = reply.get("id") if isinstance(reply, dict) else None
        if not isinstance(bot_id, str) or not bot_id:
            raise BotProviderError(
                "BOT_PROVIDER_REFUSED", "The meeting bot service did not start a bot", 502
            )
        return bot_id

    async def leave(self, bot_id: str) -> None:
        await self._call("POST", f"/api/v1/bot/{bot_id}/leave_call/")

    async def status(self, bot_id: str) -> tuple[str, str] | None:
        reply = await self._call("GET", f"/api/v1/bot/{bot_id}/")
        changes = reply.get("status_changes") if isinstance(reply, dict) else None
        if not isinstance(changes, list) or not changes or not isinstance(changes[-1], dict):
            return None
        last = changes[-1]
        return str(last.get("code") or ""), str(last.get("sub_code") or "")


def verify_any(secrets: str, headers: dict[str, str], payload: bytes) -> bool:
    """`secrets` may hold several `whsec_` secrets separated by commas or spaces: Recall signs the
    dashboard's status webhooks and the per-bot transcript webhooks with different secrets on some
    accounts, and a secret being replaced stays valid for a day. True when any one matches."""
    return any(verify_signature(one, headers, payload) for one in secrets.replace(",", " ").split())


def verify_signature(secret: str, headers: dict[str, str], payload: bytes) -> bool:
    """Is this callback really from the provider? HMAC-SHA256 of `id.timestamp.body` with the
    workspace secret (`whsec_` + base64), compared in constant time against every `v1,<sig>` entry.
    False for anything missing or wrong, including no secret configured."""
    if not secret.startswith("whsec_"):
        return False
    msg_id = headers.get("webhook-id") or headers.get("svix-id") or ""
    stamp = headers.get("webhook-timestamp") or headers.get("svix-timestamp") or ""
    given = headers.get("webhook-signature") or headers.get("svix-signature") or ""
    if not (msg_id and stamp and given):
        return False
    try:
        key = base64.b64decode(secret.removeprefix("whsec_"), validate=True)
    except ValueError:
        return False
    signed = b".".join([msg_id.encode(), stamp.encode(), payload])
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    for entry in given.split():
        version, _, signature = entry.partition(",")
        if version == "v1" and hmac.compare_digest(signature, expected):
            return True
    return False
