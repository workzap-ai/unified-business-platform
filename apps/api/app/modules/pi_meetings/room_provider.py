"""pi's own video rooms: the video provider behind them (Stream Video).

A room is a call that staff and customers join from the browser. The provider carries the video and
audio and, after the call, hands back the transcript with the id of who spoke. pi's other code only
ever sees transcript lines, so a different provider can sit behind `RoomProvider` without touching
the analysis, review or Problem Map.

What lives here: the provider interface, the Stream adapter (plain HTTPS, no vendor library), the
user tokens a browser needs to join one call, and the check of the signature on every callback.

Facts about Stream below were exercised against a real account on 2026-11-24 (docs/pi-saas/
pi-room-phase0.md): call create and delete, the transcript file (`jsonl`, one finished sentence per
line with `speaker_id`, `text`, `start_ts`, `stop_ts` in milliseconds), the callback signature
(HMAC-SHA256 hex of the body with the API secret) and the token claims. Recording and the call
type's grants are exercised in the tests with a fake provider and noted in the doc as still to be
confirmed live.
"""

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
import zlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = 15.0
BASE = "https://video.stream-io-api.com/api/v2"
CALL_TYPE = "pi_room"
GZIP_MAGIC = bytes((0x1F, 0x8B))  # the first two bytes of a gzip body
TRANSCRIPT_HOST = ".stream-io-cdn.com"  # the transcript is fetched only from the provider's CDN
MAX_TRANSCRIPT_BYTES = 5_000_000
STAFF_PREFIX = "s_"
GUEST_PREFIX = "g_"
# what any person in a room may do: be in it, hear and be heard. No one can end the call, mute
# others or remove them from the browser: the host ends it through our API.
USER_GRANTS = ["join-call", "read-call", "send-audio", "send-video", "screenshare"]


# the languages the provider's own captions understand (Urdu is not one of them)
CAPTION_LANGUAGES = frozenset(
    "auto en fr es de it nl pt pl ca cs da el fi id ja ru sv ta th tr hu ro zh ar tl he hi hr ko "
    "ms no uk bg et sl sk".split()
)
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # what the speech-to-text services take in one file
INDIVIDUAL_AUDIO = {"mode": "available", "output_types": ["audio_only"]}
# individual_<call type>_<call id>_<user id>_<uuid>_audio_only_<time>.mkv
_RECORDING_NAME = re.compile(
    r"individual_"
    + re.escape(CALL_TYPE)
    + r"_r[0-9a-f]{32}_(?P<user>[sg]_[0-9a-f]{32})_[0-9a-f-]{36}_audio_only_"
)


def caption_language(code: str) -> str:
    """The caption language to ask the provider for: ours if it understands it, else 'auto'."""
    return code if code in CAPTION_LANGUAGES else "auto"


@dataclass(frozen=True)
class RoomRecording:
    """One person's own audio of the call (one file per person)."""

    user_id: str  # the room user id: s_... or g_...
    url: str
    start: datetime | None


def _when(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)  # 3.11+: a trailing Z and long fractions are fine
    except ValueError:
        return None


class RoomProviderError(Exception):
    """The provider refused or could not be reached. `code` is ours, `message` is safe to show: it
    never carries the provider's reply or any key."""

    def __init__(self, code: str, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def new_call_id() -> str:
    """A random call id: it names no workspace or meeting and cannot be guessed."""
    return "r" + secrets.token_hex(16)


def staff_user(user_id: UUID) -> str:
    return f"{STAFF_PREFIX}{user_id.hex}"


def guest_user(participant_id: UUID) -> str:
    return f"{GUEST_PREFIX}{participant_id.hex}"


def _b64(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def sign_jwt(secret: str, claims: dict[str, Any]) -> str:
    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps(claims, separators=(",", ":")).encode())
    mac = hmac.new(secret.encode(), head + b"." + body, hashlib.sha256).digest()
    return (head + b"." + body + b"." + _b64(mac)).decode()


def verify_signature(secret: str, signature: str, body: bytes) -> bool:
    """The callback is ours only when its signature is the HMAC-SHA256 (hex) of the exact body."""
    if not secret or not signature:
        return False
    good = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(good, signature.strip().lower())


def plain_body(body: bytes, limit: int) -> bytes | None:
    """The body a signature is computed over. The provider may gzip a callback, and signs the bytes
    after unzipping; anything that unzips to more than `limit` bytes (or is not valid gzip) is
    refused, so a small request cannot grow into a large one."""
    if body[:2] != GZIP_MAGIC:
        return body if len(body) <= limit else None
    unzip = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        out = unzip.decompress(body, limit)
    except zlib.error:
        return None
    return None if unzip.unconsumed_tail else out


def trusted_transcript_url(url: str) -> bool:
    """Only an https address on the provider's own CDN is ever fetched, so a callback can never make
    the server read some other address."""
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and host.endswith(TRANSCRIPT_HOST)
        and port in (None, 443)
        and not parts.username
        and not parts.password
    )


class RoomProvider(Protocol):
    name: str

    async def create_call(self, call_id: str, *, language: str, audio: bool = False) -> None:
        """Make the call (idempotent). Transcription starts by itself when people are in it; with
        `audio` each person's own voice is also recorded, to be transcribed by us and deleted."""

    def user_token(self, user_id: str, call_id: str, *, ttl_s: int) -> str:
        """A token that lets one browser user join THIS call only."""

    async def end_call(self, call_id: str) -> None:
        """End the call for everyone."""

    async def block_user(self, call_id: str, user_id: str) -> None:
        """Remove one person from the call and stop them rejoining it. A person who never reached
        the provider is not an error (the caller also refuses them a new token)."""

    async def transcript(self, call_id: str, url: str = "") -> list[dict[str, Any]] | None:
        """The finished transcript lines, or None when it is not ready. `url` is the address the
        provider's callback gave, when there is one."""

    async def recordings(self, call_id: str) -> list[RoomRecording]:
        """Each person's own audio file, once the provider has finished writing them."""

    async def download(self, url: str) -> bytes | None:
        """The bytes of a recording (None when it is missing or too large to transcribe)."""

    async def delete_call(self, call_id: str) -> None:
        """Remove the call and its stored transcript and recording at the provider."""


def build_provider(settings: Any, http: httpx.AsyncClient) -> "StreamProvider | None":
    """The configured provider (from the settings of the API or the worker), or None."""
    if not settings.stream_api_key or settings.stream_api_secret is None:
        return None
    return StreamProvider(
        http, settings.stream_api_key, settings.stream_api_secret.get_secret_value()
    )


class StreamProvider:
    name = "stream"

    def __init__(self, http: httpx.AsyncClient, api_key: str, api_secret: str) -> None:
        self._http = http
        self._key = api_key
        self._secret = api_secret

    def _server_token(self) -> str:
        return sign_jwt(self._secret, {"server": True, "iat": int(time.time()) - 5})

    async def _call(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        missing_ok: bool = False,
    ) -> Any:
        try:
            reply = await self._http.request(
                method,
                f"{BASE}{path}",
                params={"api_key": self._key},
                json=body,
                headers={"Authorization": self._server_token(), "stream-auth-type": "jwt"},
                timeout=TIMEOUT,
            )
        except httpx.HTTPError:
            logger.warning("stream_unreachable", extra={"path": path.split("?")[0]})
            raise RoomProviderError(
                "ROOM_PROVIDER_UNREACHABLE", "The video room service could not be reached"
            ) from None
        if reply.status_code == 404 and missing_ok:
            return {}
        if reply.status_code in (401, 403):
            raise RoomProviderError(
                "ROOM_PROVIDER_KEY_REJECTED", "The video room service did not accept our key", 503
            )
        if reply.status_code == 429:
            raise RoomProviderError(
                "ROOM_PROVIDER_BUSY", "The video room service is busy; try again shortly", 429
            )
        if reply.status_code >= 400:
            logger.warning("stream_refused", extra={"status": reply.status_code})
            raise RoomProviderError(
                "ROOM_PROVIDER_REFUSED", "The video room service could not do that", 502
            )
        if not reply.content:
            return {}
        try:
            return reply.json()
        except ValueError:
            return {}

    async def ensure_call_type(self) -> None:
        """The room's call type, created once: transcription on by itself, and the narrow grants
        above for everyone (a browser user cannot end the call, mute or remove anyone)."""
        try:
            existing = await self._call("GET", f"/video/calltypes/{CALL_TYPE}")
            settings = existing.get("settings") if isinstance(existing, dict) else None
            single = settings.get("individual_recording") if isinstance(settings, dict) else None
            if not isinstance(single, dict) or single.get("mode") != "available":
                await self._call(
                    "PUT",
                    f"/video/calltypes/{CALL_TYPE}",
                    {"settings": {"individual_recording": INDIVIDUAL_AUDIO}},
                )
            return
        except RoomProviderError as error:
            if error.code != "ROOM_PROVIDER_REFUSED":
                raise
        await self._call(
            "POST",
            "/video/calltypes",
            {
                "name": CALL_TYPE,
                "grants": {"user": USER_GRANTS, "admin": USER_GRANTS},
                "settings": {
                    "transcription": {
                        "mode": "auto-on",
                        "closed_caption_mode": "auto-on",
                        "language": "auto",
                    },
                    "recording": {"mode": "disabled"},
                    "individual_recording": INDIVIDUAL_AUDIO,
                    "backstage": {"enabled": False},
                },
            },
        )

    async def create_call(self, call_id: str, *, language: str, audio: bool = False) -> None:
        await self.ensure_call_type()
        data: dict[str, Any] = {"created_by": {"id": "pi_server", "name": "pi (AI)"}}
        override: dict[str, Any] = {}
        spoken = caption_language(language)
        if spoken != "auto":
            override["transcription"] = {"language": spoken}
        if audio:
            override["individual_recording"] = {"mode": "auto-on", "output_types": ["audio_only"]}
        if override:
            data["settings_override"] = override
        await self._call("POST", f"/video/call/{CALL_TYPE}/{call_id}", {"data": data})

    def user_token(self, user_id: str, call_id: str, *, ttl_s: int) -> str:
        now = int(time.time())
        return sign_jwt(
            self._secret,
            {
                "user_id": user_id,
                "iat": now - 5,
                "exp": now + ttl_s,
                "call_cids": [f"{CALL_TYPE}:{call_id}"],
            },
        )

    async def end_call(self, call_id: str) -> None:
        await self._call("POST", f"/video/call/{CALL_TYPE}/{call_id}/mark_ended", {})

    async def block_user(self, call_id: str, user_id: str) -> None:
        await self._call(
            "POST",
            f"/video/call/{CALL_TYPE}/{call_id}/block",
            {"user_id": user_id},
            missing_ok=True,
        )

    async def transcript(self, call_id: str, url: str = "") -> list[dict[str, Any]] | None:
        address = url
        if not address:
            listed = await self._call("GET", f"/video/call/{CALL_TYPE}/{call_id}/transcriptions")
            items = listed.get("transcriptions") if isinstance(listed, dict) else None
            if not isinstance(items, list) or not items:
                return None
            newest = items[-1] if isinstance(items[-1], dict) else {}
            address = str(newest.get("url") or "")
        if not trusted_transcript_url(address):
            raise RoomProviderError("ROOM_TRANSCRIPT_UNTRUSTED", "That transcript is not ours", 502)
        try:
            reply = await self._http.get(address, timeout=TIMEOUT)
        except httpx.HTTPError:
            raise RoomProviderError(
                "ROOM_PROVIDER_UNREACHABLE", "The video room service could not be reached"
            ) from None
        if reply.status_code >= 400 or len(reply.content) > MAX_TRANSCRIPT_BYTES:
            return None
        lines: list[dict[str, Any]] = []
        for raw in reply.text.splitlines():
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if isinstance(row, dict):
                lines.append(row)
        return lines

    async def recordings(self, call_id: str) -> list[RoomRecording]:
        listed = await self._call("GET", f"/video/call/{CALL_TYPE}/{call_id}/recordings")
        items = listed.get("recordings") if isinstance(listed, dict) else None
        out: list[RoomRecording] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            found = _RECORDING_NAME.match(str(item.get("filename") or ""))
            url = str(item.get("url") or "")
            if found is None or not trusted_transcript_url(url):
                continue
            out.append(RoomRecording(found.group("user"), url, _when(item.get("start_time"))))
        return out

    async def download(self, url: str) -> bytes | None:
        if not trusted_transcript_url(url):
            raise RoomProviderError("ROOM_RECORDING_UNTRUSTED", "That recording is not ours", 502)
        try:
            reply = await self._http.get(url, timeout=60.0)
        except httpx.HTTPError:
            raise RoomProviderError(
                "ROOM_PROVIDER_UNREACHABLE", "The video room service could not be reached"
            ) from None
        if reply.status_code >= 400 or len(reply.content) > MAX_AUDIO_BYTES:
            return None
        return reply.content

    async def delete_call(self, call_id: str) -> None:
        await self._call(
            "POST", f"/video/call/{CALL_TYPE}/{call_id}/delete", {"hard": True}, missing_ok=True
        )
