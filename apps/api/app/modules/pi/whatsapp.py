import hashlib
import hmac
import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.ai.media import normalize_mime
from app.core.config import Settings
from app.shared.errors import BusinessRuleViolation

logger = logging.getLogger("platform")


def _rejection_kind(response: httpx.Response) -> str:
    """Meta's error code, or the provider's error text as an identifier, e.g.
    "131042" (payment issue) or "cannot_send_non_template_messages_outside_the_24"."""
    try:
        data = response.json()
    except ValueError:
        return f"http_{response.status_code}"
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(data, dict) and isinstance(data.get("code"), str) and data["code"]:
        # Kapso's own refusals: {"error": "...", "code": "funding_required_unverified"}
        return re.sub(r"[^a-z0-9]+", "_", data["code"].lower()).strip("_")[:60]
    if isinstance(error, dict):
        code = error.get("code") or error.get("error_subcode")
        if code:
            return str(code)[:20]
        error = error.get("message") or error.get("type")
    text = re.sub(r"[^a-z0-9]+", "_", str(error or "").lower()).strip("_")
    return text[:60] or f"http_{response.status_code}"


def check_sent(response: httpx.Response) -> None:
    """A 4xx is WhatsApp (or Kapso) refusing the message: nothing was sent, so say so
    and log why. Timeouts and 5xx stay "unconfirmed" (it may have been sent)."""
    if 400 <= response.status_code < 500:
        kind = _rejection_kind(response)
        logger.warning(
            "whatsapp_send_rejected",
            extra={"provider": "whatsapp", "status_code": response.status_code, "error_kind": kind},
        )
        if response.status_code == 402 or "funding" in kind or "billing" in kind:
            # The account's WhatsApp billing blocks paid sends (Kapso/Meta side).
            raise BusinessRuleViolation(
                "WHATSAPP_BILLING_PAUSED",
                f"WhatsApp sending is paused until billing is fixed ({kind})",
                422,
            )
        raise BusinessRuleViolation(
            "WHATSAPP_REJECTED", f"WhatsApp refused the message ({kind})", 422
        )
    response.raise_for_status()


def encrypt_token(settings: Settings, token: str) -> str:
    if not settings.secrets_encryption_key:
        raise BusinessRuleViolation(
            "ENCRYPTION_NOT_CONFIGURED", "Connection secret storage is not configured", 503
        )
    return (
        Fernet(settings.secrets_encryption_key.get_secret_value().encode())
        .encrypt(token.encode())
        .decode()
    )


def decrypt_token(settings: Settings, token: str | None) -> str:
    if not settings.secrets_encryption_key or not token:
        raise BusinessRuleViolation("CONNECTION_NOT_CONFIGURED", "Messaging is not configured", 503)
    try:
        return (
            Fernet(settings.secrets_encryption_key.get_secret_value().encode())
            .decrypt(token.encode())
            .decode()
        )
    except (ValueError, InvalidToken):
        raise BusinessRuleViolation(
            "CONNECTION_NOT_CONFIGURED", "Messaging is not configured", 503
        ) from None


def verify_signature(body: bytes, signature: str, settings: Settings) -> bool:
    if not settings.whatsapp_app_secret:
        return False
    expected = (
        "sha256="
        + hmac.new(
            settings.whatsapp_app_secret.get_secret_value().encode(), body, hashlib.sha256
        ).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


def normalize(payload: dict[str, Any]) -> list[dict[str, Any]]:
    events = []
    for entry in payload.get("entry", [])[:100]:
        for change in entry.get("changes", [])[:100]:
            value = change.get("value", {})
            number = value.get("metadata", {}).get("phone_number_id", "")
            if not re.fullmatch(r"[0-9]{5,32}", str(number)):
                continue
            profiles = {
                x.get("wa_id"): x.get("profile", {}).get("name") for x in value.get("contacts", [])
            }
            for message in value.get("messages", [])[:100]:
                sender, mid = message.get("from", ""), message.get("id", "")
                if (
                    not re.fullmatch(r"[0-9]{6,15}", str(sender))
                    or not isinstance(mid, str)
                    or not 1 <= len(mid) <= 160
                ):
                    continue
                kind = message.get("type", "other")
                body = (
                    message.get("text", {}).get("body", "")
                    if kind == "text"
                    else message.get(kind, {}).get("caption", "")
                )
                events.append(
                    {
                        "key": f"{number}:{mid}",
                        "kind": "message",
                        "number": number,
                        "message_id": mid,
                        "sender": sender,
                        "profile": profiles.get(sender),
                        "message_type": kind
                        if kind in {"text", "audio", "image", "video"}
                        else "other",
                        "body": str(body)[:4000],
                        "media_id": str(message.get(kind, {}).get("id", ""))[:160]
                        if kind in {"audio", "image", "video"}
                        else None,
                    }
                )
            for status in value.get("statuses", [])[:100]:
                mid, state = status.get("id"), status.get("status")
                if (
                    isinstance(mid, str)
                    and len(mid) <= 160
                    and state in {"sent", "delivered", "read", "failed"}
                ):
                    events.append(
                        {
                            "key": f"{number}:{mid}:{state}",
                            "kind": "status",
                            "number": number,
                            "message_id": mid,
                            "state": state,
                        }
                    )
    return events[:100]


MEDIA_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "audio/ogg",
        "audio/mpeg",
        "audio/mp4",
        "audio/aac",
        "video/mp4",
        "video/3gpp",
    }
)


class WhatsApp:
    """Meta-compatible WhatsApp messaging over a selected transport.

    ``meta_cloud`` calls the Graph API with the number's own access token. ``kapso`` calls
    Kapso's Meta-compatible proxy with the server-held project key; each business still
    authorizes its own number through Kapso's setup link, so the key only reaches numbers
    connected to this project.
    """

    def __init__(
        self, settings: Settings, http: httpx.AsyncClient, provider: str = "meta_cloud"
    ) -> None:
        self.settings, self.http, self.provider = settings, http, provider

    def _endpoint(self, token: str) -> tuple[str, dict[str, str]]:
        if self.provider == "kapso":
            key = self.settings.kapso_api_key
            if key is None:
                raise BusinessRuleViolation(
                    "CONNECTION_NOT_CONFIGURED", "Messaging is not configured", 503
                )
            base = self.settings.kapso_base_url.rstrip("/")
            return (
                f"{base}/meta/whatsapp/{self.settings.kapso_meta_api_version}",
                {"X-API-Key": key.get_secret_value()},
            )
        return (
            f"{self.settings.whatsapp_graph_base_url}/{self.settings.whatsapp_graph_version}",
            {"Authorization": f"Bearer {token}"},
        )

    async def template_body(self, account: str, template: dict[str, str], token: str) -> str:
        """The approved text of a no-variable template, checked live against Meta
        (approval, exact language, no variables or buttons). HTTP errors propagate."""
        if (
            not re.fullmatch(r"[0-9]{5,32}", account)
            or not re.fullmatch(r"[a-z0-9_]{1,512}", template.get("name", ""))
            or not re.fullmatch(r"[a-z]{2,3}(?:_[A-Z]{2})?", template.get("language", ""))
        ):
            raise BusinessRuleViolation("REMINDER_TEMPLATE_INVALID", "Invalid reminder template")
        base, headers = self._endpoint(token)
        response = await self.http.get(
            f"{base}/{account}/message_templates",
            headers=headers,
            params={
                "name": template["name"],
                "fields": "name,status,language,components",
                "limit": 100,
            },
            timeout=15,
            follow_redirects=False,
        )
        response.raise_for_status()
        approved = next(
            (
                item
                for item in response.json().get("data", [])
                if item.get("name") == template["name"]
                and item.get("language") == template["language"]
                and item.get("status") == "APPROVED"
            ),
            None,
        )
        if not approved:
            raise BusinessRuleViolation(
                "REMINDER_TEMPLATE_NOT_APPROVED", "Reminder template is not approved"
            )
        components = approved.get("components", [])
        if any(
            "{{" in str(c)
            or (c.get("type") == "HEADER" and c.get("format") != "TEXT")
            or c.get("type") == "BUTTONS"
            for c in components
        ):
            raise BusinessRuleViolation(
                "REMINDER_TEMPLATE_PARAMETERS",
                "Use a text template without variables or buttons",
            )
        body = next((c.get("text", "") for c in components if c.get("type") == "BODY"), "")
        if not body:
            raise BusinessRuleViolation(
                "REMINDER_TEMPLATE_INVALID", "Reminder template has no text"
            )
        return str(body)

    async def send_template(
        self,
        number: str,
        account: str,
        recipient: str,
        template: dict[str, str],
        token: str,
    ) -> tuple[str, str]:
        """Check Meta approval/language, then send a no-variable reminder template."""
        base, headers = self._endpoint(token)
        try:
            body = await self.template_body(account, template, token)
            response = await self.http.post(
                f"{base}/{number}/messages",
                headers=headers,
                json={
                    "messaging_product": "whatsapp",
                    "to": recipient,
                    "type": "template",
                    "template": {
                        "name": template["name"],
                        "language": {"code": template["language"]},
                    },
                },
                timeout=15,
                follow_redirects=False,
            )
            check_sent(response)
            mid = response.json()["messages"][0]["id"]
            if not isinstance(mid, str) or not 1 <= len(mid) <= 160:
                raise ValueError
            return mid, str(body)[:4000]
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            raise BusinessRuleViolation(
                "DELIVERY_UNCONFIRMED", "Reminder delivery could not be confirmed", 503
            ) from None

    async def send_flow(
        self,
        number: str,
        recipient: str,
        body: str,
        flow: dict[str, str],
        flow_token: str,
        token: str,
    ) -> str:
        """Send a published WhatsApp Flow (form) as an interactive session message."""
        base, headers = self._endpoint(token)
        try:
            response = await self.http.post(
                f"{base}/{number}/messages",
                headers=headers,
                json={
                    "messaging_product": "whatsapp",
                    "to": recipient,
                    "type": "interactive",
                    "interactive": {
                        "type": "flow",
                        "body": {"text": body[:1024]},
                        "action": {
                            "name": "flow",
                            "parameters": {
                                "flow_message_version": "3",
                                "flow_token": flow_token,
                                "flow_id": flow["flow_id"],
                                "flow_cta": flow["cta"][:20],
                                "flow_action": "navigate",
                                "flow_action_payload": {"screen": flow["screen"]},
                            },
                        },
                    },
                },
                timeout=15,
                follow_redirects=False,
            )
            check_sent(response)
            mid = response.json()["messages"][0]["id"]
            if not isinstance(mid, str) or not 1 <= len(mid) <= 160:
                raise ValueError
            return mid
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            raise BusinessRuleViolation(
                "DELIVERY_UNCONFIRMED", "Form delivery could not be confirmed", 503
            ) from None

    async def mark_read(self, number: str, message_id: str, *, typing: bool = True) -> bool:
        """Blue ticks plus "typing…" on the customer's phone while Pi works on a reply.
        Best effort: it never delays or fails the reply. Kapso numbers only (the Meta
        path needs the number's own token, which the caller doesn't hold here)."""
        if self.provider != "kapso" or not message_id or self.settings.kapso_api_key is None:
            return False
        base, headers = self._endpoint("")
        body: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        if typing:
            body["typing_indicator"] = {"type": "text"}
        try:
            response = await self.http.post(
                f"{base}/{number}/messages",
                headers=headers,
                json=body,
                timeout=5,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            return False
        return response.status_code < 400

    async def send_image(
        self, number: str, recipient: str, link: str, caption: str, token: str
    ) -> str:
        """Send an image by public link with a caption (pi's visual cards). Session
        messages only: the caller checks the 24-hour window."""
        base, headers = self._endpoint(token)
        try:
            response = await self.http.post(
                f"{base}/{number}/messages",
                headers=headers,
                json={
                    "messaging_product": "whatsapp",
                    "to": recipient,
                    "type": "image",
                    "image": {"link": link, "caption": caption[:1024]},
                },
                timeout=20,
                follow_redirects=False,
            )
            check_sent(response)
            mid = response.json()["messages"][0]["id"]
            if not isinstance(mid, str) or not 1 <= len(mid) <= 160:
                raise ValueError
            return mid
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            raise BusinessRuleViolation(
                "DELIVERY_UNCONFIRMED", "Image delivery could not be confirmed", 503
            ) from None

    async def send(self, number: str, recipient: str, body: str, token: str) -> str:
        base, headers = self._endpoint(token)
        try:
            response = await self.http.post(
                f"{base}/{number}/messages",
                headers=headers,
                json={
                    "messaging_product": "whatsapp",
                    "to": recipient,
                    "type": "text",
                    "text": {"body": body[:4000]},
                },
                timeout=15,
                follow_redirects=False,
            )
            check_sent(response)
            mid = response.json()["messages"][0]["id"]
            if not isinstance(mid, str) or len(mid) > 160:
                raise ValueError
            return mid
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            # An ambiguous timeout must not be blindly retried: the provider may have sent it.
            raise BusinessRuleViolation(
                "DELIVERY_UNCONFIRMED", "Message delivery could not be confirmed", 503
            ) from None

    async def media(
        self, media_id: str, token: str, *, url: str = "", mime: str = ""
    ) -> tuple[bytes, str]:
        """Download one inbound file. ``url``/``mime`` are what Kapso's webhook already
        gave; they are tried first and the provider's media lookup is the fallback."""
        if not re.fullmatch(r"[0-9]{5,32}", media_id):
            raise BusinessRuleViolation("INVALID_MEDIA", "Unsupported media")
        if self.provider == "kapso" and url and mime:
            try:
                return await self._download(url, normalize_mime(mime), token)
            except BusinessRuleViolation:
                pass
        base, headers = self._endpoint(token)
        try:
            metadata = await self.http.get(f"{base}/{media_id}", headers=headers, timeout=10)
            metadata.raise_for_status()
            data = metadata.json()
            found, found_mime = data["url"], data["mime_type"]
            if not isinstance(found, str) or not isinstance(found_mime, str):
                raise ValueError
            if int(data.get("file_size", 0)) > self.settings.media_max_bytes:
                raise ValueError
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise BusinessRuleViolation("INVALID_MEDIA", "Media could not be processed") from None
        return await self._download(found, normalize_mime(found_mime), token)

    def _media_host_allowed(self, host: str) -> bool:
        if host in {"lookaside.fbsbx.com", "lookaside.facebook.com"}:
            return True
        if self.provider != "kapso":
            return False
        # Kapso serves files from its app host (app.kapso.ai) as well as its API host.
        kapso_host = urlparse(self.settings.kapso_base_url).hostname or ""
        domain = ".".join(kapso_host.split(".")[-2:])
        return bool(kapso_host) and (host == kapso_host or host.endswith("." + domain))

    async def _download(self, url: str, mime: str, token: str) -> tuple[bytes, str]:
        _, headers = self._endpoint(token)
        try:
            parsed = urlparse(url)
            if (
                parsed.scheme != "https"
                or not self._media_host_allowed(parsed.hostname or "")
                or parsed.username
                or parsed.port not in {None, 443}
                or mime not in MEDIA_TYPES
            ):
                raise ValueError
            chunks = bytearray()
            for _hop in range(2):
                async with self.http.stream(
                    "GET", url, headers=headers, timeout=15, follow_redirects=False
                ) as response:
                    if response.is_redirect and _hop == 0:
                        # A file store behind the provider: follow once, without our
                        # credentials, and only to another https address.
                        url = str(response.headers.get("location", ""))
                        if not url.startswith("https://"):
                            raise ValueError
                        headers = {}
                        continue
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > self.settings.media_max_bytes:
                            raise ValueError
                    break
            if not chunks:
                raise ValueError
            return bytes(chunks), mime
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise BusinessRuleViolation("INVALID_MEDIA", "Media could not be processed") from None
