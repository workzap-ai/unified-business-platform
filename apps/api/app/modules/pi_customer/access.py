"""Sign-in for PI Customer: a one-time code sent on WhatsApp, then a signed session.

There are no customer accounts or passwords. A code is stored only as a hash, expires
after ten minutes and allows five tries. The session cookie is signed with a key derived
from SECRETS_ENCRYPTION_KEY and carries only the phone number and an expiry; it lasts
twelve hours. Every unsafe request also needs the CSRF value derived from the session.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import HTTPException, Request, Response

from app.core.config import Settings

SESSION_COOKIE = "pi_customer_session"
CSRF_COOKIE = "pi_customer_csrf"
SESSION_SECONDS = 12 * 3600
CODE_SECONDS = 10 * 60
MAX_TRIES = 5
UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class CodeStore(Protocol):
    async def put(self, key: str, value: dict[str, Any], seconds: int) -> None: ...
    async def get(self, key: str) -> dict[str, Any] | None: ...
    async def delete(self, key: str) -> None: ...


class RedisCodeStore:
    def __init__(self, redis: Any) -> None:
        self.redis = redis

    async def put(self, key: str, value: dict[str, Any], seconds: int) -> None:
        await self.redis.set(key, json.dumps(value), ex=seconds)

    async def get(self, key: str) -> dict[str, Any] | None:
        raw = await self.redis.get(key)
        return json.loads(raw) if raw else None

    async def delete(self, key: str) -> None:
        await self.redis.delete(key)


class MemoryCodeStore:
    """For tests and single-process development."""

    def __init__(self) -> None:
        self.items: dict[str, tuple[float, dict[str, Any]]] = {}

    async def put(self, key: str, value: dict[str, Any], seconds: int) -> None:
        self.items[key] = (time.time() + seconds, value)

    async def get(self, key: str) -> dict[str, Any] | None:
        found = self.items.get(key)
        if found is None or found[0] < time.time():
            return None
        return found[1]

    async def delete(self, key: str) -> None:
        self.items.pop(key, None)


def code_store(request: Request) -> CodeStore:
    state = request.app.state
    store: CodeStore | None = getattr(state, "pi_customer_codes", None)
    if store is not None:
        return store
    if state.settings.app_env in {"development", "test"}:
        # One local process and often no Redis: keep codes in memory there.
        store = MemoryCodeStore()
        state.pi_customer_codes = store
        return store
    return RedisCodeStore(state.redis)


def _key(settings: Settings) -> bytes:
    secret = settings.secrets_encryption_key
    if secret is None:
        raise HTTPException(503, "PI Customer is not available right now")
    return hashlib.sha256(b"pi-customer-v1:" + secret.get_secret_value().encode()).digest()


def _sign(settings: Settings, data: bytes) -> str:
    mac = hmac.new(_key(settings), data, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def code_key(settings: Settings, phone: str) -> str:
    return "pi-customer:code:" + _sign(settings, phone.encode())[:40]


def new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def code_hash(settings: Settings, phone: str, code: str) -> str:
    return _sign(settings, f"code:{phone}:{code}".encode())


@dataclass(frozen=True)
class CustomerSession:
    phone: str  # digits only, as WhatsApp ids are stored
    nonce: str
    expires: int


def _csrf(settings: Settings, nonce: str) -> str:
    return _sign(settings, f"csrf:{nonce}".encode())[:32]


def issue(response: Response, settings: Settings, phone: str) -> CustomerSession:
    nonce = secrets.token_urlsafe(16)
    expires = int(time.time()) + SESSION_SECONDS
    payload = base64.urlsafe_b64encode(
        json.dumps({"p": phone, "n": nonce, "e": expires}).encode()
    ).decode()
    token = f"{payload}.{_sign(settings, payload.encode())}"
    common: dict[str, Any] = {
        "max_age": SESSION_SECONDS,
        "path": "/",
        "secure": settings.secure_cookies,
    }
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", **common)
    response.set_cookie(
        CSRF_COOKIE, _csrf(settings, nonce), httponly=False, samesite="strict", **common
    )
    return CustomerSession(phone, nonce, expires)


def clear(response: Response, settings: Settings) -> None:
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/", secure=settings.secure_cookies)


def read(request: Request) -> CustomerSession | None:
    settings: Settings = request.app.state.settings
    token = request.cookies.get(SESSION_COOKIE, "")
    payload, _, signature = token.partition(".")
    if not payload or not hmac.compare_digest(signature, _sign(settings, payload.encode())):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
        session = CustomerSession(str(data["p"]), str(data["n"]), int(data["e"]))
    except (ValueError, KeyError, TypeError):
        return None
    if session.expires < time.time() or not session.phone.isdigit():
        return None
    return session


async def current(request: Request) -> CustomerSession:
    """FastAPI dependency: the signed-in customer, with CSRF checked on changes."""
    session = read(request)
    if session is None:
        raise HTTPException(401, "Sign in with your WhatsApp number")
    if request.method in UNSAFE:
        supplied = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(supplied, _csrf(request.app.state.settings, session.nonce)):
            raise HTTPException(403, "Refresh the page and try again")
    return session


def mask(phone: str) -> str:
    return f"+{phone[:2]}{'•' * max(len(phone) - 6, 2)}{phone[-4:]}"
