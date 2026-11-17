"""Signed calls from pi to nori. Every call fails open: it never raises, it returns a CallResult.

`identify` is the only call made for a number nori has not vouched for, and it carries the number
alone (data minimisation): no message text leaves pi until nori says the sender is its member.
"""

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.modules.pi_saas.nori_credits import signing
from app.modules.pi_saas.nori_credits.config import BridgeEnv, WorkspaceBridge
from app.modules.pi_saas.nori_credits.resilience import (
    IDENTIFY_CACHE,
    METRICS,
    breaker_for,
    digits,
    mask_number,
)

INBOUND_PATH = "/api/workzap/inbound"
STRUCTURED_PATH = "/api/credits/pi"
IDENTIFY_TTL_SECONDS = 60.0
# Answers that say "the bridge is unhealthy" and count toward the breaker. A 400 or 422 means nori
# is up and refused this one request; it does not.
_COUNTED_STATUS = {401, 403, 408, 425, 429}


@dataclass
class CallResult:
    ok: bool
    # ok, timeout, connect, http_5xx, http_4xx, bad_signature, bad_response or circuit_open
    reason: str
    status: int | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Identity:
    """known is True only on a successful call that answered known:true."""

    known: bool
    checked: bool  # False when the call failed, so "unknown" means "could not tell"
    member: dict[str, Any] | None = None
    credits: bool | None = None
    # nori answered known:false but listed this number for a welcome (the master panel made it a
    # sign-in link in the last 7 days). Allows the welcome send only: no chat, no member rights.
    welcome_ok: bool = False


def _now_ms() -> int:
    return int(time.time() * 1000)


class NoriClient:
    def __init__(
        self,
        env: BridgeEnv,
        http: httpx.AsyncClient,
        bridge: WorkspaceBridge,
        *,
        now_ms: Callable[[], int] = _now_ms,
    ) -> None:
        self.env, self.http, self.bridge, self.now_ms = env, http, bridge, now_ms
        self.breaker = breaker_for(env.host, bridge.breaker_failures, bridge.breaker_cooldown)

    async def call(self, path: str, payload: dict[str, Any]) -> CallResult:
        if not self.breaker.allow():
            METRICS.inc("call", "circuit_open")
            return CallResult(False, "circuit_open")
        body = json.dumps(
            {"ts": self.now_ms(), **payload}, separators=(",", ":"), ensure_ascii=False
        ).encode()
        result = await self._post(path, body)
        if result.reason in {"ok", "http_4xx"}:
            self.breaker.success()
        elif result.reason in {"timeout", "connect", "http_5xx", "bad_signature", "bad_response"}:
            self.breaker.failure()
        else:
            self.breaker.release()
        METRICS.inc("call", result.reason)
        return result

    async def _post(self, path: str, body: bytes) -> CallResult:
        timeout = self.bridge.timeout
        try:
            async with asyncio.timeout(timeout + 0.25):
                response = await self.http.post(
                    self.env.url(path),
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Workzap-Signature": signing.sign(self.env.secret, body),
                    },
                    timeout=timeout,
                    follow_redirects=False,
                )
        except (TimeoutError, httpx.TimeoutException):
            return CallResult(False, "timeout")
        except httpx.HTTPError:
            return CallResult(False, "connect")
        except Exception:  # fail open on anything: the bridge must never break pi
            return CallResult(False, "connect")
        status = response.status_code
        if status in {401, 403}:
            return CallResult(False, "bad_signature", status)
        if status >= 500 or status in _COUNTED_STATUS:
            return CallResult(False, "http_5xx", status)
        # nori does not sign its answers today; when it does, a wrong signature is refused.
        sent = response.headers.get("x-workzap-signature")
        if sent and not signing.verify(self.env.secret, response.content, sent):
            return CallResult(False, "bad_signature", status)
        try:
            data = response.json()
        except ValueError:
            return CallResult(False, "bad_response", status)
        if not isinstance(data, dict):
            return CallResult(False, "bad_response", status)
        if status >= 400:
            return CallResult(False, "http_4xx", status, data)
        if not 200 <= status < 300:
            return CallResult(False, "bad_response", status)
        return CallResult(True, "ok", status, data)

    # --- the calls -------------------------------------------------------------------------

    async def identify(self, number: str, *, use_cache: bool = True) -> Identity:
        key = digits(number)
        if use_cache:
            cached = IDENTIFY_CACHE.get(key)
            if isinstance(cached, Identity):
                METRICS.inc("identify", "cache")
                return cached
        result = await self.call(STRUCTURED_PATH, {"action": "identify", "from": key})
        if not result.ok or not isinstance(result.data.get("known"), bool):
            return Identity(known=False, checked=False)
        member = result.data.get("member")
        workspace = result.data.get("workspace")
        identity = Identity(
            known=result.data["known"],
            checked=True,
            member=member if isinstance(member, dict) else None,
            credits=workspace.get("credits") if isinstance(workspace, dict) else None,
            welcome_ok=result.data["known"] is False and result.data.get("welcome_ok") is True,
        )
        IDENTIFY_CACHE.put(key, identity, IDENTIFY_TTL_SECONDS)
        METRICS.inc("identify", "known" if identity.known else "unknown")
        return identity

    async def inbound(
        self, *, sender: str, message_id: str, text: str, name: str | None
    ) -> CallResult:
        return await self.call(
            INBOUND_PATH,
            {
                "from": digits(sender),
                "message_id": message_id[:200],
                "text": text[:4000],
                "name": name,
                "timestamp": str(int(time.time())),
            },
        )

    async def structured(self, action: str, sender: str, **fields: Any) -> CallResult:
        clean = {k: v for k, v in fields.items() if v is not None}
        return await self.call(STRUCTURED_PATH, {"action": action, "from": digits(sender), **clean})


def describe(number: str) -> str:
    """How a number is written in a log line."""
    return mask_number(number)
