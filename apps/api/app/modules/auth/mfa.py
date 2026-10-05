"""The second sign-in step: after the password, your face (camera) or your fingerprint.

People who saved a face or a fingerprint (passkey) don't get a session from the
password alone. The login answers with a short-lived ticket, and the session is issued
only after the face matches or the fingerprint signs. Neither step works without the
password first.

- Face: up to three saved faces per person. Adding one needs a signed-in session plus
  the password, then a live camera check. Only encrypted face codes are stored.
- Fingerprint: a passkey on this device (Touch ID, Windows Hello, Android fingerprint).
  Optional, and only usable after the password.
- Five wrong face or fingerprint tries in a row lock this step for fifteen minutes. The
  count is kept in the database and goes back to zero after a successful sign-in.
"""

import asyncio
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer
from webauthn import generate_authentication_options, options_to_json
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement

from app.core.audience import Audience
from app.core.rate_limit import client_ip, hit
from app.integrations.crypto import CredentialManager
from app.integrations.errors import IntegrationError
from app.modules.audit.service import record
from app.modules.auth import face
from app.modules.auth.crypto import verify_password
from app.modules.auth.dependencies import Auth
from app.modules.auth.models import UserCredential, UserFace, UserPasskey
from app.modules.auth.passkeys import (
    OWNER_OS,
    PI,
    Site,
    _store,
    check_login,
    credential_id_of,
    origin_for,
    take_login,
)
from app.modules.auth.routes import Session, session_view, set_cookies
from app.modules.auth.service import AuthService
from app.modules.users.models import PlatformUser
from app.shared.errors import BusinessRuleViolation, ResourceNotFound

logger = logging.getLogger("platform")
# The lock columns are deferred on the model; load them where this step needs them.
_LOCK_COLUMNS = (
    undefer(UserCredential.second_factor_failures),
    undefer(UserCredential.second_factor_locked_until),
)

TICKET_SECONDS = 300
MAX_FAILURES = 5
LOCK_MINUTES = 15
MAX_FACES = 3


def _now() -> datetime:
    return datetime.now(UTC)


def _crypto(request: Request) -> CredentialManager:
    try:
        manager = CredentialManager(request.app.state.settings)
    except IntegrationError:
        manager = None
    if manager is None or not manager.configured:
        raise BusinessRuleViolation("FACE_UNAVAILABLE", "Face sign-in isn't switched on yet", 503)
    return manager


async def methods_for(session: AsyncSession, user_id: UUID, rp_id: str) -> list[str]:
    """Second steps this person can use here: saved faces work everywhere; a fingerprint
    only on the website (RP ID) it was added on."""
    faces = await session.scalar(
        select(func.count()).select_from(UserFace).where(UserFace.user_id == user_id)
    )
    keys = await session.scalar(
        select(func.count())
        .select_from(UserPasskey)
        .where(UserPasskey.user_id == user_id, UserPasskey.rp_id.in_([rp_id, ""]))
    )
    return [m for m, n in (("face", faces), ("fingerprint", keys)) if n]


def rp_id_of(request: Request) -> str:
    """The website's host, as passkeys know it (blank when there is no Origin)."""
    return urlparse(request.headers.get("origin", "")).hostname or ""


async def second_step(
    request: Request, session: AsyncSession, user: PlatformUser, audience: Audience
) -> dict[str, Any] | None:
    """After a correct password: the ticket for the second step, or None if this person
    hasn't saved a face or a fingerprint (then the password alone signs in)."""
    try:
        # A savepoint: if this database hasn't got the sign-in tables yet (a deploy ran
        # ahead of its migration), the password still signs people in as before.
        async with session.begin_nested():
            methods = await methods_for(session, user.id, rp_id_of(request))
    except ProgrammingError:
        logger.warning("second_step_tables_missing")
        return None
    return await open_ticket(request, user, methods, audience) if methods else None


async def open_ticket(
    request: Request, user: PlatformUser, methods: list[str], audience: Audience = "owner_os"
) -> dict[str, Any]:
    ticket = secrets.token_urlsafe(24)
    await _store(request).put(
        f"mfa:{ticket}",
        {"user": str(user.id), "methods": methods, "audience": audience},
        TICKET_SECONDS,
    )
    return {
        "mfa_required": True,
        "ticket": ticket,
        "methods": methods,
        "frames": face.FRAMES,
        "name": user.display_name,
    }


async def _ticket(request: Request, ticket: str, audience: Audience) -> UUID:
    found = await _store(request).get(f"mfa:{ticket}")
    # A ticket from one app's password step can't finish a sign-in in the other.
    if found is None or found.get("audience", "owner_os") != audience:
        raise BusinessRuleViolation(
            "SIGN_IN_EXPIRED", "That took too long. Enter your password again."
        )
    return UUID(found["user"])


async def _credential(session: AsyncSession, user_id: UUID) -> UserCredential:
    credential: UserCredential | None = await session.scalar(
        select(UserCredential)
        .options(*_LOCK_COLUMNS)
        .where(UserCredential.user_id == user_id)
        .with_for_update()
    )
    if credential is None:
        raise BusinessRuleViolation(
            "SIGN_IN_EXPIRED", "That took too long. Enter your password again."
        )
    locked = credential.second_factor_locked_until
    if locked and locked > _now():
        minutes = max(1, int((locked - _now()).total_seconds() // 60) + 1)
        raise BusinessRuleViolation(
            "SECOND_STEP_LOCKED",
            f"Too many tries. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
            423,
        )
    return credential


async def _failed(
    request: Request, session: AsyncSession, credential: UserCredential, ticket: str, method: str
) -> BusinessRuleViolation:
    credential.second_factor_failures += 1
    left = MAX_FAILURES - credential.second_factor_failures
    if left <= 0:
        credential.second_factor_locked_until = _now() + timedelta(minutes=LOCK_MINUTES)
        credential.second_factor_failures = 0
        await _store(request).delete(f"mfa:{ticket}")
    await record(
        session,
        "auth.login_failed",
        actor_user_id=credential.user_id,
        entity_type="user",
        entity_id=credential.user_id,
        outcome="failure",
        details={"method": method, "locked": left <= 0},
        include_environment=False,
    )
    await session.commit()
    if left <= 0:
        return BusinessRuleViolation(
            "SECOND_STEP_LOCKED", f"Too many tries. Try again in {LOCK_MINUTES} minutes.", 423
        )
    what = "That doesn't look like you" if method == "face" else "That fingerprint didn't work"
    return BusinessRuleViolation(
        "SECOND_STEP_FAILED", f"{what}. {left} {'try' if left == 1 else 'tries'} left.", 401
    )


async def _success(
    request: Request,
    response: Response,
    session: AsyncSession,
    credential: UserCredential,
    ticket: str,
    method: str,
    audience: Audience,
) -> Any:
    credential.second_factor_failures = 0
    credential.second_factor_locked_until = None
    await _store(request).delete(f"mfa:{ticket}")
    user = await session.get(PlatformUser, credential.user_id)
    if user is None or user.status != "active":
        raise BusinessRuleViolation("SIGN_IN_EXPIRED", "Enter your password again.")
    settings = request.app.state.settings
    service = AuthService(session, settings)
    issued = await service.finish_login(
        user, request.headers.get("user-agent", ""), audience, f"password+{method}"
    )
    await session.commit()
    if audience == "pi":
        from app.modules.pi_saas.app_routes import _session_view, _set_cookies

        _set_cookies(response, request, issued)
        return await _session_view(session, issued.record, user)
    set_cookies(response, settings, issued)
    context = await service.resolve(issued.token)
    return await session_view(session, context)


# ---- Signing in: step two -----------------------------------------------------------


class FaceCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str = Field(min_length=16, max_length=64)
    frames: list[str] = Field(min_length=face.FRAMES, max_length=face.FRAMES)


async def _read(frames: list[str]) -> list[face.FaceFrame]:
    try:
        return await asyncio.to_thread(face.live_frames, face.decode_frames(frames))
    except face.FaceError as error:
        raise BusinessRuleViolation(error.code, error.message) from None


class TicketOnly(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str = Field(min_length=16, max_length=64)


class FingerprintCheck(TicketOnly):
    credential: dict[str, Any]


# ---- Managing saved faces -----------------------------------------------------------


class Password(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=256)


class FaceAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str = Field(min_length=16, max_length=64)
    name: str = Field("", max_length=80)
    frames: list[str] = Field(min_length=face.FRAMES, max_length=face.FRAMES)


class FaceRename(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)


def _view(f: UserFace) -> dict[str, Any]:
    return {"id": f.id, "name": f.name, "created_at": f.created_at, "last_used_at": f.last_used_at}


async def _mine(session: AsyncSession, user_id: UUID, face_id: UUID) -> UserFace:
    found: UserFace | None = await session.scalar(
        select(UserFace).where(UserFace.id == face_id, UserFace.user_id == user_id)
    )
    if found is None:
        raise ResourceNotFound
    return found


def second_step_router(audience: Audience, site: Site) -> APIRouter:
    """The second step and face management for one app (Owner OS or the pi app). Both
    mount it at /auth under their own prefix, so each uses its own session cookie."""
    router = APIRouter(prefix="/auth", tags=["auth-second-step"])

    @router.post("/mfa/face")
    async def sign_in_with_face(
        data: FaceCheck, request: Request, response: Response, session: Session
    ) -> Any:
        if not await hit(request, "mfa-face-ip", client_ip(request), 30, 600):
            raise HTTPException(status_code=429)
        user_id = await _ticket(request, data.ticket, audience)
        credential = await _credential(session, user_id)
        crypto = _crypto(request)
        try:
            found = await asyncio.to_thread(face.live_frames, face.decode_frames(data.frames))
        except face.FaceError as error:
            if error.code == "FACE_NOT_LIVE":  # looks like a photo or a replay: counts
                raise await _failed(request, session, credential, data.ticket, "face") from None
            raise BusinessRuleViolation(error.code, error.message) from None
        best: tuple[float, UserFace | None] = (-1.0, None)
        for saved in await session.scalars(select(UserFace).where(UserFace.user_id == user_id)):
            score = face.similarity(found, face.unpack(crypto.decrypt(saved.code_encrypted)))
            if score > best[0]:
                best = (score, saved)
        if best[1] is None or best[0] < face.MATCH:
            raise await _failed(request, session, credential, data.ticket, "face")
        best[1].last_used_at = _now()
        return await _success(request, response, session, credential, data.ticket, "face", audience)

    @router.post("/mfa/fingerprint/options")
    async def fingerprint_options(data: TicketOnly, request: Request, session: Session) -> Any:
        user_id = await _ticket(request, data.ticket, audience)
        _, rp_id = origin_for(request, site)
        keys = list(
            await session.scalars(
                select(UserPasskey.credential_id).where(
                    UserPasskey.user_id == user_id, UserPasskey.rp_id.in_([rp_id, ""])
                )
            )
        )
        if not keys:
            raise BusinessRuleViolation("NO_FINGERPRINT", "Add a fingerprint in Account first")
        options = generate_authentication_options(
            rp_id=rp_id,
            allow_credentials=[
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(k)) for k in keys
            ],
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        await _store(request).put(
            f"passkey:{site.key}:login:{data.ticket}",
            {"challenge": bytes_to_base64url(options.challenge), "rp_id": rp_id},
            TICKET_SECONDS,
        )
        return JSONResponse(content={"options": json.loads(options_to_json(options))})

    @router.post("/mfa/fingerprint")
    async def sign_in_with_fingerprint(
        data: FingerprintCheck, request: Request, response: Response, session: Session
    ) -> Any:
        user_id = await _ticket(request, data.ticket, audience)
        credential = await _credential(session, user_id)
        origin, rp_id, challenge = await take_login(request, site, data.ticket)
        passkey = await session.scalar(
            select(UserPasskey)
            .where(
                UserPasskey.credential_id == credential_id_of(data.credential),
                UserPasskey.user_id == user_id,
            )
            .with_for_update()
        )
        verified = (
            check_login(
                data.credential,
                origin=origin,
                rp_id=rp_id,
                challenge=challenge,
                public_key=passkey.public_key,
                sign_count=passkey.sign_count,
                user_handle=user_id.bytes,
            )
            if passkey
            else None
        )
        if passkey is None or verified is None:
            raise await _failed(request, session, credential, data.ticket, "fingerprint")
        passkey.sign_count = verified.new_sign_count
        passkey.last_used_at = _now()
        return await _success(
            request, response, session, credential, data.ticket, "fingerprint", audience
        )

    @router.get("/faces")
    async def faces(auth: Auth, session: Session) -> dict[str, Any]:
        rows = await session.scalars(
            select(UserFace).where(UserFace.user_id == auth.user.id).order_by(UserFace.created_at)
        )
        credential = await session.scalar(
            select(UserCredential)
            .options(*_LOCK_COLUMNS)
            .where(UserCredential.user_id == auth.user.id)
        )
        locked = credential.second_factor_locked_until if credential else None
        return {
            "faces": [_view(f) for f in rows],
            "max": MAX_FACES,
            "locked_until": locked if locked and locked > _now() else None,
        }

    @router.post("/faces/start")
    async def start_adding_face(
        data: Password, request: Request, auth: Auth, session: Session
    ) -> dict[str, Any]:
        """Only the signed-in person's own password opens the camera step."""
        if not await hit(request, "face-add", str(auth.user.id), 10, 600):
            raise HTTPException(status_code=429)
        _crypto(request)
        credential = await session.scalar(
            select(UserCredential).where(UserCredential.user_id == auth.user.id)
        )
        if not verify_password(credential.password_hash if credential else None, data.password):
            raise BusinessRuleViolation("PASSWORD_INCORRECT", "That password isn't right", 403)
        count = await session.scalar(
            select(func.count()).select_from(UserFace).where(UserFace.user_id == auth.user.id)
        )
        if int(count or 0) >= MAX_FACES:
            raise BusinessRuleViolation(
                "TOO_MANY_FACES", f"You can save up to {MAX_FACES} faces. Remove one first."
            )
        ticket = secrets.token_urlsafe(24)
        await _store(request).put(f"face-add:{ticket}", {"user": str(auth.user.id)}, TICKET_SECONDS)
        return {"ticket": ticket, "frames": face.FRAMES}

    @router.post("/faces", status_code=201)
    async def add_face(
        data: FaceAdd, request: Request, auth: Auth, session: Session
    ) -> dict[str, Any]:
        store, key = _store(request), f"face-add:{data.ticket}"
        pending = await store.get(key)
        if pending is None or pending.get("user") != str(auth.user.id):
            raise BusinessRuleViolation("FACE_EXPIRED", "That took too long. Start again.")
        crypto = _crypto(request)
        found = await _read(data.frames)
        await store.delete(key)  # used once the frames were good
        count = await session.scalar(
            select(func.count()).select_from(UserFace).where(UserFace.user_id == auth.user.id)
        )
        if int(count or 0) >= MAX_FACES:
            raise BusinessRuleViolation("TOO_MANY_FACES", f"You can save up to {MAX_FACES} faces.")
        saved = UserFace(
            user_id=auth.user.id,
            name=(data.name.strip() or f"Face {int(count or 0) + 1}")[:80],
            code_encrypted=crypto.encrypt(face.pack(face.face_code(found))),
        )
        session.add(saved)
        await session.flush()
        await record(
            session,
            "auth.face_added",
            actor_user_id=auth.user.id,
            entity_type="user_face",
            entity_id=saved.id,
            include_environment=False,
        )
        await session.commit()
        return _view(saved)

    @router.patch("/faces/{face_id}")
    async def rename_face(
        face_id: UUID, data: FaceRename, auth: Auth, session: Session
    ) -> dict[str, Any]:
        found = await _mine(session, auth.user.id, face_id)
        found.name = data.name
        await session.commit()
        return _view(found)

    @router.delete("/faces/{face_id}", status_code=204)
    async def remove_face(face_id: UUID, auth: Auth, session: Session) -> Response:
        found = await _mine(session, auth.user.id, face_id)
        await session.delete(found)
        await record(
            session,
            "auth.face_removed",
            actor_user_id=auth.user.id,
            entity_type="user_face",
            entity_id=face_id,
            include_environment=False,
        )
        await session.commit()
        return Response(status_code=204)

    return router


router = second_step_router("owner_os", OWNER_OS)
pi_router = second_step_router("pi", PI)
