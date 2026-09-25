import hashlib
import hmac
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings
from app.shared.errors import BusinessRuleViolation


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
                        "message_type": kind if kind in {"text", "audio", "image"} else "other",
                        "body": str(body)[:4000],
                        "media_id": str(message.get(kind, {}).get("id", ""))[:160]
                        if kind in {"audio", "image"}
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


class WhatsApp:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self.settings, self.http = settings, http

    async def send(self, number: str, recipient: str, body: str, token: str) -> str:
        try:
            response = await self.http.post(
                f"{self.settings.whatsapp_graph_base_url}/{self.settings.whatsapp_graph_version}/{number}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": recipient,
                    "type": "text",
                    "text": {"body": body[:4000]},
                },
                timeout=15,
                follow_redirects=False,
            )
            response.raise_for_status()
            mid = response.json()["messages"][0]["id"]
            if not isinstance(mid, str) or len(mid) > 160:
                raise ValueError
            return mid
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            # An ambiguous timeout must not be blindly retried: the provider may have sent it.
            raise BusinessRuleViolation(
                "DELIVERY_UNCONFIRMED", "Message delivery could not be confirmed", 503
            ) from None

    async def media(self, media_id: str, token: str) -> tuple[bytes, str]:
        if not re.fullmatch(r"[0-9]{5,32}", media_id):
            raise BusinessRuleViolation("INVALID_MEDIA", "Unsupported media")
        try:
            metadata = await self.http.get(
                f"{self.settings.whatsapp_graph_base_url}/{self.settings.whatsapp_graph_version}/{media_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            metadata.raise_for_status()
            data = metadata.json()
            url, mime = data["url"], data["mime_type"]
            parsed = urlparse(url)
            if (
                parsed.scheme != "https"
                or parsed.hostname not in {"lookaside.fbsbx.com", "lookaside.facebook.com"}
                or parsed.username
                or parsed.port not in {None, 443}
            ):
                raise ValueError
            if (
                mime
                not in {
                    "image/jpeg",
                    "image/png",
                    "audio/ogg",
                    "audio/mpeg",
                    "audio/mp4",
                    "audio/aac",
                }
                or int(data.get("file_size", 0)) > self.settings.media_max_bytes
            ):
                raise ValueError
            chunks = bytearray()
            async with self.http.stream(
                "GET",
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
                follow_redirects=False,
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > self.settings.media_max_bytes:
                        raise ValueError
            if not chunks:
                raise ValueError
            return bytes(chunks), str(mime)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise BusinessRuleViolation("INVALID_MEDIA", "Media could not be processed") from None
