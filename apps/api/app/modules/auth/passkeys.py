"""Passkeys: sign in with Face ID, Touch ID, Windows Hello or a phone fingerprint.

WebAuthn does the work. The device checks the face or fingerprint and signs a one-time
challenge with a key that never leaves it. We store only the public key and verify the
signature, the website the browser says it is on, and that the person was actually
verified (user_verification "required").

- Adding a passkey needs a signed-in session plus the account password, so a stolen
  session alone can't plant a way back in.
- Challenges are single use and expire after five minutes.
- Signing in with a passkey issues the same server-side session as a password sign-in,
  is rate limited and is audited.

The same ceremony serves three sites, each with its own allowed origins and cookies:
Owner OS (/auth/passkeys), the pi app (/pi-app/auth/passkeys) and pi Customer
(pi_customer.passkeys, for end customers who have no account).
"""

import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.authentication.verify_authentication_response import VerifiedAuthentication
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidCBORData,
    InvalidJSONStructure,
    InvalidRegistrationResponse,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from webauthn.registration.verify_registration_response import VerifiedRegistration

from app.core.audience import Audience
from app.core.config import Settings
from app.core.rate_limit import client_ip, hit
from app.modules.audit.service import record
from app.modules.auth.crypto import verify_password
from app.modules.auth.dependencies import Auth
from app.modules.auth.models import UserCredential, UserPasskey
from app.modules.auth.routes import Session, session_view, set_cookies
from app.modules.auth.service import AuthService
from app.modules.pi_customer.access import CodeStore, MemoryCodeStore, RedisCodeStore
from app.modules.users.models import PlatformUser
from app.shared.errors import BusinessRuleViolation, ResourceNotFound, Unauthenticated

CHALLENGE_SECONDS = 300
MAX_PASSKEYS = 10
VERIFY_ERRORS = (
    InvalidRegistrationResponse,
    InvalidAuthenticationResponse,
    InvalidCBORData,
    InvalidJSONStructure,
    ValueError,
    KeyError,
    TypeError,
)


# ---- The ceremony, shared by every site ---------------------------------------------


@dataclass(frozen=True)
class Site:
    key: str  # namespaces challenges
    rp_name: str
    origins: Callable[[Settings], list[str]]


OWNER_OS = Site("owner_os", "Owner OS", lambda s: [*s.cors_origins, s.web_public_url])
PI = Site("pi", "pi", lambda s: [*s.pi_app_origins, s.pi_app_public_url])
PI_CUSTOMER = Site("pi_customer", "pi Customer", lambda s: [*s.pi_app_origins, s.pi_app_public_url])


def _store(request: Request) -> CodeStore:
    state = request.app.state
    store: CodeStore | None = getattr(state, "passkey_challenges", None)
    if store is not None:
        return store
    if state.settings.app_env in {"development", "test"}:
        store = MemoryCodeStore()
        state.passkey_challenges = store
        return store
    return RedisCodeStore(state.redis)


def origin_for(request: Request, site: Site) -> tuple[str, str]:
    """The site's origin the browser is on, and its host as the WebAuthn RP ID. Only
    configured origins are accepted, so a passkey made here works nowhere else."""
    origin = request.headers.get("origin", "").rstrip("/")
    allowed = {o.rstrip("/") for o in site.origins(request.app.state.settings)}
    host = urlparse(origin).hostname
    if origin not in allowed or not host:
        raise BusinessRuleViolation(
            "ORIGIN_NOT_ALLOWED", f"Passkeys work only on {site.rp_name}", 403
        )
    return origin, host


def device_name(user_agent: str) -> str:
    ua = user_agent.lower()
    for needle, name in (
        ("iphone", "iPhone"),
        ("ipad", "iPad"),
        ("android", "Android phone"),
        ("macintosh", "Mac"),
        ("windows", "Windows PC"),
        ("cros", "Chromebook"),
        ("linux", "Linux computer"),
    ):
        if needle in ua:
            return name
    return "This device"


async def start_registration(
    request: Request,
    site: Site,
    owner: str,
    *,
    user_handle: bytes,
    user_name: str,
    display_name: str,
    existing: list[str],
) -> dict[str, Any]:
    _, rp_id = origin_for(request, site)
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=site.rp_name,
        user_id=user_handle,
        user_name=user_name,
        user_display_name=display_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c)) for c in existing
        ],
    )
    await _store(request).put(
        f"passkey:{site.key}:register:{owner}",
        {"challenge": bytes_to_base64url(options.challenge), "rp_id": rp_id},
        CHALLENGE_SECONDS,
    )
    result: dict[str, Any] = json.loads(options_to_json(options))
    return result


async def finish_registration(
    request: Request, site: Site, owner: str, credential: dict[str, Any]
) -> VerifiedRegistration:
    origin, rp_id = origin_for(request, site)
    store, key = _store(request), f"passkey:{site.key}:register:{owner}"
    pending = await store.get(key)
    await store.delete(key)  # single use, whatever happens next
    if pending is None or pending.get("rp_id") != rp_id:
        raise BusinessRuleViolation("PASSKEY_EXPIRED", "That took too long. Please try again.")
    try:
        return verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(pending["challenge"]),
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except VERIFY_ERRORS:
        raise BusinessRuleViolation(
            "PASSKEY_INVALID", "This passkey couldn't be checked. Please try again."
        ) from None


def transports_of(credential: dict[str, Any]) -> str:
    raw = credential.get("response", {}).get("transports") or []
    return ",".join(t for t in raw if isinstance(t, str))[:120]


async def start_login(request: Request, site: Site) -> dict[str, Any]:
    limit = request.app.state.settings.rate_limit_login_per_minute
    if not await hit(request, "passkey-login-ip", client_ip(request), limit, 60):
        raise HTTPException(status_code=429)
    _, rp_id = origin_for(request, site)
    # No account is named: the device offers the passkeys it holds for this site.
    options = generate_authentication_options(
        rp_id=rp_id, user_verification=UserVerificationRequirement.REQUIRED
    )
    flow = secrets.token_urlsafe(24)
    await _store(request).put(
        f"passkey:{site.key}:login:{flow}",
        {"challenge": bytes_to_base64url(options.challenge), "rp_id": rp_id},
        CHALLENGE_SECONDS,
    )
    return {"flow": flow, "options": json.loads(options_to_json(options))}


async def take_login(request: Request, site: Site, flow: str) -> tuple[str, str, bytes]:
    """Consumes the login challenge (single use); returns origin, RP ID and challenge."""
    limit = request.app.state.settings.rate_limit_login_per_minute
    if not await hit(request, "passkey-login-ip", client_ip(request), limit, 60):
        raise HTTPException(status_code=429)
    origin, rp_id = origin_for(request, site)
    store, key = _store(request), f"passkey:{site.key}:login:{flow}"
    pending = await store.get(key)
    await store.delete(key)
    if pending is None or pending.get("rp_id") != rp_id:
        raise BusinessRuleViolation("PASSKEY_EXPIRED", "That took too long. Please try again.")
    return origin, rp_id, base64url_to_bytes(pending["challenge"])


def credential_id_of(credential: dict[str, Any]) -> str:
    raw_id = credential.get("rawId") or credential.get("id")
    if not isinstance(raw_id, str) or not raw_id or len(raw_id) > 1400:
        raise Unauthenticated
    return raw_id


def check_login(
    credential: dict[str, Any],
    *,
    origin: str,
    rp_id: str,
    challenge: bytes,
    public_key: bytes,
    sign_count: int,
    user_handle: bytes,
) -> VerifiedAuthentication | None:
    """The verified assertion, or None when it doesn't check out."""
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=public_key,
            credential_current_sign_count=sign_count,
            require_user_verification=True,
        )
    except VERIFY_ERRORS:
        return None
    # The user handle the device returns must belong to the passkey's owner.
    handle = credential.get("response", {}).get("userHandle")
    if handle and base64url_to_bytes(handle) != user_handle:
        return None
    return verified


# ---- Accounts: Owner OS and the pi app ------------------------------------------------


class PasswordConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=256)


class RegisterVerify(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credential: dict[str, Any]
    name: str = Field("", max_length=80)


class LoginVerify(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flow: str = Field(min_length=16, max_length=64)
    credential: dict[str, Any]


class PasskeyRename(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)


def view(p: Any) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "created_at": p.created_at,
        "last_used_at": p.last_used_at,
        "synced": p.backed_up,
    }


def account_router(prefix: str, site: Site, audience: Audience, *, passwordless: bool) -> APIRouter:
    """Add, list, rename and remove passkeys. With `passwordless`, a passkey alone also
    signs in; without it (Owner OS), a passkey is only the optional fingerprint step
    after the password (see mfa.py)."""
    router = APIRouter(prefix=prefix, tags=["auth-passkeys"])

    async def _mine(session: Session, user_id: UUID, passkey_id: UUID) -> UserPasskey:
        passkey = await session.scalar(
            select(UserPasskey).where(UserPasskey.id == passkey_id, UserPasskey.user_id == user_id)
        )
        if passkey is None:
            raise ResourceNotFound
        return passkey

    @router.get("")
    async def passkeys(auth: Auth, session: Session) -> list[dict[str, Any]]:
        rows = await session.scalars(
            select(UserPasskey)
            .where(UserPasskey.user_id == auth.user.id)
            .order_by(UserPasskey.created_at)
        )
        return [view(p) for p in rows]

    @router.post("/register/options")
    async def register_options(
        data: PasswordConfirm, request: Request, auth: Auth, session: Session
    ) -> dict[str, Any]:
        if not await hit(request, "passkey-register", str(auth.user.id), 10, 600):
            raise HTTPException(status_code=429)
        origin_for(request, site)
        credential = await session.scalar(
            select(UserCredential).where(UserCredential.user_id == auth.user.id)
        )
        if not verify_password(credential.password_hash if credential else None, data.password):
            raise BusinessRuleViolation("PASSWORD_INCORRECT", "That password isn't right", 403)
        existing = list(
            await session.scalars(
                select(UserPasskey.credential_id).where(UserPasskey.user_id == auth.user.id)
            )
        )
        if len(existing) >= MAX_PASSKEYS:
            raise BusinessRuleViolation("TOO_MANY_PASSKEYS", "Remove a passkey before adding one")
        return await start_registration(
            request,
            site,
            str(auth.user.id),
            user_handle=auth.user.id.bytes,
            user_name=auth.user.email,
            display_name=auth.user.display_name,
            existing=existing,
        )

    @router.post("/register/verify", status_code=201)
    async def register_verify(
        data: RegisterVerify, request: Request, auth: Auth, session: Session
    ) -> dict[str, Any]:
        verified = await finish_registration(request, site, str(auth.user.id), data.credential)
        credential_id = bytes_to_base64url(verified.credential_id)
        if await session.scalar(
            select(UserPasskey.id).where(UserPasskey.credential_id == credential_id)
        ):
            raise BusinessRuleViolation("PASSKEY_EXISTS", "This passkey is already added")
        passkey = UserPasskey(
            user_id=auth.user.id,
            credential_id=credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            name=(data.name.strip() or device_name(request.headers.get("user-agent", "")))[:80],
            transports=transports_of(data.credential),
            backed_up=bool(verified.credential_backed_up),
        )
        session.add(passkey)
        await session.flush()
        await record(
            session,
            "auth.passkey_added",
            actor_user_id=auth.user.id,
            entity_type="user_passkey",
            entity_id=passkey.id,
            details={"name": passkey.name, "audience": audience},
            include_environment=False,
        )
        await session.commit()
        return view(passkey)

    @router.patch("/{passkey_id}")
    async def rename(
        passkey_id: UUID, data: PasskeyRename, auth: Auth, session: Session
    ) -> dict[str, Any]:
        passkey = await _mine(session, auth.user.id, passkey_id)
        passkey.name = data.name
        await session.commit()
        return view(passkey)

    @router.delete("/{passkey_id}", status_code=204)
    async def remove(passkey_id: UUID, auth: Auth, session: Session) -> Response:
        passkey = await _mine(session, auth.user.id, passkey_id)
        await session.delete(passkey)
        await record(
            session,
            "auth.passkey_removed",
            actor_user_id=auth.user.id,
            entity_type="user_passkey",
            entity_id=passkey_id,
            include_environment=False,
        )
        await session.commit()
        return Response(status_code=204)

    if not passwordless:
        return router

    @router.post("/login/options")
    async def login_options(request: Request) -> dict[str, Any]:
        return await start_login(request, site)

    @router.post("/login/verify")
    async def login_verify(
        data: LoginVerify, request: Request, response: Response, session: Session
    ) -> Any:
        origin, rp_id, challenge = await take_login(request, site, data.flow)
        row = (
            await session.execute(
                select(UserPasskey, PlatformUser)
                .join(PlatformUser, PlatformUser.id == UserPasskey.user_id)
                .where(UserPasskey.credential_id == credential_id_of(data.credential))
                .with_for_update(of=UserPasskey)
            )
        ).first()
        if row is None:
            raise Unauthenticated
        passkey, user = row
        verified = check_login(
            data.credential,
            origin=origin,
            rp_id=rp_id,
            challenge=challenge,
            public_key=passkey.public_key,
            sign_count=passkey.sign_count,
            user_handle=user.id.bytes,
        )
        if verified is None or user.status != "active":
            await record(
                session,
                "auth.login_failed",
                actor_user_id=user.id,
                entity_type="user",
                entity_id=user.id,
                outcome="failure",
                details={"method": "passkey", "audience": audience},
                include_environment=False,
            )
            await session.commit()
            raise Unauthenticated
        passkey.sign_count = verified.new_sign_count
        passkey.backed_up = bool(verified.credential_backed_up)
        passkey.last_used_at = datetime.now(UTC)
        settings = request.app.state.settings
        service = AuthService(session, settings)
        issued = await service._issue(user, request.headers.get("user-agent", ""), audience)
        await record(
            session,
            "auth.login",
            actor_user_id=user.id,
            entity_type="user",
            details={"audience": audience, "method": "passkey"},
            include_environment=False,
        )
        await session.commit()
        if audience == "pi":
            # The pi app's own cookies and session shape.
            from app.modules.pi_saas.app_routes import _session_view, _set_cookies

            _set_cookies(response, request, issued)
            return await _session_view(session, issued.record, user)
        set_cookies(response, settings, issued)
        context = await service.resolve(issued.token)
        return await session_view(session, context)

    return router


# Owner OS: a passkey is the optional fingerprint step after the password, never alone.
router = account_router("/auth/passkeys", OWNER_OS, "owner_os", passwordless=False)
# Mounted under /api/v1/pi-app, so it uses the pi app's session and cookies.
pi_router = account_router("/auth/passkeys", PI, "pi", passwordless=False)
