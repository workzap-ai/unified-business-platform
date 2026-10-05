"""Passkeys: sign in with Face ID, Touch ID, Windows Hello or a phone fingerprint.

WebAuthn does the work. The device checks the face or fingerprint and signs a one-time
challenge with a key that never leaves it. We store only the public key, and we verify
three things: the signature, the website the browser says it is on, and that the person
was actually verified (user_verification "required").

- Adding a passkey needs a signed-in session and the account password, so a stolen
  session alone can't plant a way back in.
- Challenges are single use and expire after five minutes.
- Signing in with a passkey issues the same server-side session as a password sign-in,
  and is rate limited and audited the same way.
"""

import json
import secrets
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

from app.core.rate_limit import client_ip, hit
from app.modules.audit.service import record
from app.modules.auth.crypto import verify_password
from app.modules.auth.dependencies import Auth
from app.modules.auth.models import UserCredential, UserPasskey
from app.modules.auth.routes import Session, session_view, set_cookies
from app.modules.auth.schemas import SessionView
from app.modules.auth.service import AuthService
from app.modules.pi_customer.access import CodeStore, MemoryCodeStore, RedisCodeStore
from app.modules.users.models import PlatformUser
from app.shared.errors import BusinessRuleViolation, ResourceNotFound, Unauthenticated

router = APIRouter(prefix="/auth/passkeys", tags=["auth-passkeys"])

CHALLENGE_SECONDS = 300
MAX_PASSKEYS = 10
RP_NAME = "Owner OS"
VERIFY_ERRORS = (
    InvalidRegistrationResponse,
    InvalidAuthenticationResponse,
    InvalidCBORData,
    InvalidJSONStructure,
    ValueError,
    KeyError,
    TypeError,
)


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


def _origin(request: Request) -> tuple[str, str]:
    """The Owner OS origin the browser is on, and its host as the WebAuthn RP ID.
    Only configured Owner OS origins are accepted, so a passkey made for this site
    can't be used anywhere else."""
    settings = request.app.state.settings
    origin = request.headers.get("origin", "").rstrip("/")
    allowed = {o.rstrip("/") for o in [*settings.cors_origins, settings.web_public_url]}
    host = urlparse(origin).hostname
    if origin not in allowed or not host:
        raise BusinessRuleViolation("ORIGIN_NOT_ALLOWED", "Passkeys work only on Owner OS", 403)
    return origin, host


def _device(user_agent: str) -> str:
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


def _view(p: UserPasskey) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "created_at": p.created_at,
        "last_used_at": p.last_used_at,
        "synced": p.backed_up,
    }


@router.get("")
async def passkeys(auth: Auth, session: Session) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(UserPasskey)
        .where(UserPasskey.user_id == auth.user.id)
        .order_by(UserPasskey.created_at)
    )
    return [_view(p) for p in rows]


@router.post("/register/options")
async def register_options(
    data: PasswordConfirm, request: Request, auth: Auth, session: Session
) -> dict[str, Any]:
    if not await hit(request, "passkey-register", str(auth.user.id), 10, 600):
        raise HTTPException(status_code=429)
    _, rp_id = _origin(request)
    credential = await session.scalar(
        select(UserCredential).where(UserCredential.user_id == auth.user.id)
    )
    if not verify_password(credential.password_hash if credential else None, data.password):
        raise BusinessRuleViolation("PASSWORD_INCORRECT", "That password isn't right", 403)
    existing = list(
        await session.scalars(select(UserPasskey).where(UserPasskey.user_id == auth.user.id))
    )
    if len(existing) >= MAX_PASSKEYS:
        raise BusinessRuleViolation("TOO_MANY_PASSKEYS", "Remove a passkey before adding one")
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=RP_NAME,
        user_id=auth.user.id.bytes,
        user_name=auth.user.email,
        user_display_name=auth.user.display_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(p.credential_id)) for p in existing
        ],
    )
    await _store(request).put(
        f"passkey:register:{auth.user.id}",
        {"challenge": bytes_to_base64url(options.challenge), "rp_id": rp_id},
        CHALLENGE_SECONDS,
    )
    result: dict[str, Any] = json.loads(options_to_json(options))
    return result


@router.post("/register/verify", status_code=201)
async def register_verify(
    data: RegisterVerify, request: Request, auth: Auth, session: Session
) -> dict[str, Any]:
    origin, rp_id = _origin(request)
    store = _store(request)
    key = f"passkey:register:{auth.user.id}"
    pending = await store.get(key)
    await store.delete(key)  # single use, whatever happens next
    if pending is None or pending.get("rp_id") != rp_id:
        raise BusinessRuleViolation("PASSKEY_EXPIRED", "That took too long. Please try again.")
    try:
        verified = verify_registration_response(
            credential=data.credential,
            expected_challenge=base64url_to_bytes(pending["challenge"]),
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except VERIFY_ERRORS:
        raise BusinessRuleViolation(
            "PASSKEY_INVALID", "This passkey couldn't be checked. Please try again."
        ) from None
    credential_id = bytes_to_base64url(verified.credential_id)
    if await session.scalar(
        select(UserPasskey.id).where(UserPasskey.credential_id == credential_id)
    ):
        raise BusinessRuleViolation("PASSKEY_EXISTS", "This passkey is already added")
    transports = data.credential.get("response", {}).get("transports") or []
    passkey = UserPasskey(
        user_id=auth.user.id,
        credential_id=credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        name=(data.name.strip() or _device(request.headers.get("user-agent", "")))[:80],
        transports=",".join(str(t) for t in transports if isinstance(t, str))[:120],
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
        details={"name": passkey.name},
        include_environment=False,
    )
    await session.commit()
    return _view(passkey)


@router.patch("/{passkey_id}")
async def rename(
    passkey_id: UUID, data: PasskeyRename, auth: Auth, session: Session
) -> dict[str, Any]:
    passkey = await session.scalar(
        select(UserPasskey).where(UserPasskey.id == passkey_id, UserPasskey.user_id == auth.user.id)
    )
    if passkey is None:
        raise ResourceNotFound
    passkey.name = data.name
    await session.commit()
    return _view(passkey)


@router.delete("/{passkey_id}", status_code=204)
async def remove(passkey_id: UUID, auth: Auth, session: Session) -> Response:
    passkey = await session.scalar(
        select(UserPasskey).where(UserPasskey.id == passkey_id, UserPasskey.user_id == auth.user.id)
    )
    if passkey is None:
        raise ResourceNotFound
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


@router.post("/login/options")
async def login_options(request: Request) -> dict[str, Any]:
    limit = request.app.state.settings.rate_limit_login_per_minute
    if not await hit(request, "passkey-login-ip", client_ip(request), limit, 60):
        raise HTTPException(status_code=429)
    _, rp_id = _origin(request)
    # No account is named: the device offers the passkeys it holds for this site.
    options = generate_authentication_options(
        rp_id=rp_id, user_verification=UserVerificationRequirement.REQUIRED
    )
    flow = secrets.token_urlsafe(24)
    await _store(request).put(
        f"passkey:login:{flow}",
        {"challenge": bytes_to_base64url(options.challenge), "rp_id": rp_id},
        CHALLENGE_SECONDS,
    )
    return {"flow": flow, "options": json.loads(options_to_json(options))}


@router.post("/login/verify", response_model=SessionView)
async def login_verify(
    data: LoginVerify, request: Request, response: Response, session: Session
) -> SessionView:
    settings = request.app.state.settings
    if not await hit(
        request, "passkey-login-ip", client_ip(request), settings.rate_limit_login_per_minute, 60
    ):
        raise HTTPException(status_code=429)
    origin, rp_id = _origin(request)
    store = _store(request)
    pending = await store.get(f"passkey:login:{data.flow}")
    await store.delete(f"passkey:login:{data.flow}")
    if pending is None or pending.get("rp_id") != rp_id:
        raise BusinessRuleViolation("PASSKEY_EXPIRED", "That took too long. Please try again.")
    raw_id = data.credential.get("rawId") or data.credential.get("id")
    if not isinstance(raw_id, str) or len(raw_id) > 1400:
        raise Unauthenticated
    row = (
        await session.execute(
            select(UserPasskey, PlatformUser)
            .join(PlatformUser, PlatformUser.id == UserPasskey.user_id)
            .where(UserPasskey.credential_id == raw_id)
            .with_for_update(of=UserPasskey)
        )
    ).first()
    if row is None:
        raise Unauthenticated
    passkey, user = row
    try:
        verified = verify_authentication_response(
            credential=data.credential,
            expected_challenge=base64url_to_bytes(pending["challenge"]),
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except VERIFY_ERRORS:
        await record(
            session,
            "auth.login_failed",
            actor_user_id=user.id,
            entity_type="user",
            entity_id=user.id,
            outcome="failure",
            details={"method": "passkey"},
            include_environment=False,
        )
        await session.commit()
        raise Unauthenticated from None
    # The user handle the device returns must belong to the passkey's owner.
    handle = data.credential.get("response", {}).get("userHandle")
    if handle and base64url_to_bytes(handle) != user.id.bytes:
        raise Unauthenticated
    if user.status != "active":
        raise Unauthenticated
    passkey.sign_count = verified.new_sign_count
    passkey.backed_up = bool(verified.credential_backed_up)
    passkey.last_used_at = datetime.now(UTC)
    service = AuthService(session, settings)
    issued = await service._issue(user, request.headers.get("user-agent", ""))
    await record(
        session,
        "auth.login",
        actor_user_id=user.id,
        entity_type="user",
        details={"audience": "owner_os", "method": "passkey"},
        include_environment=False,
    )
    await session.commit()
    set_cookies(response, settings, issued)
    context = await service.resolve(issued.token)
    return await session_view(session, context)
