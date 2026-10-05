"""pi Customer's check after the WhatsApp code: the face on the camera, or an optional
fingerprint. Mounted at /api/v1/pi-app/customer-portal.

Customers have no password; the WhatsApp code is the first step. A customer who saved a
face or a fingerprint gets no session from the code alone: /verify answers with a
short ticket, and the cookie is issued only after the face matches or the fingerprint
signs. Neither works without a fresh code first.

- Faces: up to three per number. Adding one, or a fingerprint, needs a fresh sign-in
  (the WhatsApp code entered in the last 15 minutes). Only encrypted face codes are kept.
- Five wrong tries in a row lock the step for fifteen minutes; the count is kept in the
  database and goes back to zero after a successful sign-in.
"""

import asyncio
import json
import logging
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import generate_authentication_options, options_to_json
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement

from app.core.rate_limit import client_ip, hit
from app.integrations.crypto import CredentialManager
from app.integrations.errors import IntegrationError
from app.modules.access.dependencies import Session
from app.modules.auth import face
from app.modules.auth.passkeys import (
    MAX_PASSKEYS,
    PI_CUSTOMER,
    PasskeyRename,
    RegisterVerify,
    _store,
    check_login,
    credential_id_of,
    device_name,
    finish_registration,
    origin_for,
    start_registration,
    take_login,
    transports_of,
    view,
)
from app.modules.pi_customer import access
from app.modules.pi_customer.access import CustomerSession
from app.modules.pi_customer.models import CustomerFace, CustomerPasskey, CustomerSignInLock
from app.shared.errors import BusinessRuleViolation, ResourceNotFound

logger = logging.getLogger("platform")
router = APIRouter(prefix="/customer-portal", tags=["pi-customer"])
Customer = Annotated[CustomerSession, Depends(access.current)]

TICKET_SECONDS = 300
FRESH_SECONDS = 15 * 60
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


def _handle(request: Request, phone: str) -> bytes:
    """The WebAuthn user handle: a keyed hash, so the number never sits on the device."""
    signed = access._sign(request.app.state.settings, f"passkey-user:{phone}".encode())
    return signed.encode()[:32]


def _fresh(customer: CustomerSession) -> None:
    signed_in_at = customer.expires - access.SESSION_SECONDS
    if time.time() - signed_in_at > FRESH_SECONDS:
        raise BusinessRuleViolation(
            "SIGN_IN_AGAIN",
            "For your safety, sign in again with your WhatsApp code, then try again.",
            403,
        )


# ---- After the WhatsApp code: the ticket ---------------------------------------------


async def second_step(request: Request, session: AsyncSession, phone: str) -> dict[str, Any] | None:
    """Called once the WhatsApp code is right. None means no face or fingerprint is saved,
    so the code alone signs in."""
    try:
        # A savepoint: before migration 0023 the code alone keeps signing people in.
        async with session.begin_nested():
            faces = await session.scalar(
                select(func.count()).select_from(CustomerFace).where(CustomerFace.phone == phone)
            )
            keys = await session.scalar(
                select(func.count())
                .select_from(CustomerPasskey)
                .where(CustomerPasskey.phone == phone)
            )
    except ProgrammingError:
        logger.warning("customer_second_step_tables_missing")
        return None
    methods = [m for m, n in (("face", faces), ("fingerprint", keys)) if n]
    if not methods:
        return None
    ticket = secrets.token_urlsafe(24)
    await _store(request).put(f"customer-mfa:{ticket}", {"phone": phone}, TICKET_SECONDS)
    return {
        "mfa_required": True,
        "ticket": ticket,
        "methods": methods,
        "frames": face.FRAMES,
        "phone": access.mask(phone),
    }


async def _ticket(request: Request, ticket: str) -> str:
    found = await _store(request).get(f"customer-mfa:{ticket}")
    if found is None:
        raise BusinessRuleViolation("SIGN_IN_EXPIRED", "That took too long. Ask for a new code.")
    return str(found["phone"])


async def _lock(session: AsyncSession, phone: str) -> CustomerSignInLock:
    lock: CustomerSignInLock | None = await session.scalar(
        select(CustomerSignInLock).where(CustomerSignInLock.phone == phone).with_for_update()
    )
    if lock is None:
        lock = CustomerSignInLock(phone=phone, failures=0)
        session.add(lock)
        await session.flush()
    if lock.locked_until and lock.locked_until > _now():
        minutes = max(1, int((lock.locked_until - _now()).total_seconds() // 60) + 1)
        raise BusinessRuleViolation(
            "SECOND_STEP_LOCKED",
            f"Too many tries. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
            423,
        )
    return lock


async def _failed(
    request: Request, session: AsyncSession, lock: CustomerSignInLock, ticket: str, method: str
) -> BusinessRuleViolation:
    lock.failures += 1
    left = MAX_FAILURES - lock.failures
    if left <= 0:
        lock.locked_until = _now() + timedelta(minutes=LOCK_MINUTES)
        lock.failures = 0
        await _store(request).delete(f"customer-mfa:{ticket}")
    await session.commit()
    logger.warning("pi_customer_second_step_failed", extra={"method": method})
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
    lock: CustomerSignInLock,
    ticket: str,
    phone: str,
    method: str,
) -> dict[str, Any]:
    lock.failures = 0
    lock.locked_until = None
    await _store(request).delete(f"customer-mfa:{ticket}")
    await session.commit()
    access.issue(response, request.app.state.settings, phone)
    logger.info("pi_customer_signed_in", extra={"method": f"code+{method}"})
    return {"phone": access.mask(phone)}


class FaceCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str = Field(min_length=16, max_length=64)
    frames: list[str] = Field(min_length=face.FRAMES, max_length=face.FRAMES)


class TicketOnly(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str = Field(min_length=16, max_length=64)


class FingerprintCheck(TicketOnly):
    credential: dict[str, Any]


@router.post("/mfa/face")
async def sign_in_with_face(
    data: FaceCheck, request: Request, response: Response, session: Session
) -> dict[str, Any]:
    if not await hit(request, "customer-mfa-face", client_ip(request), 30, 600):
        raise HTTPException(status_code=429)
    phone = await _ticket(request, data.ticket)
    lock = await _lock(session, phone)
    crypto = _crypto(request)
    try:
        found = await asyncio.to_thread(face.live_frames, face.decode_frames(data.frames))
    except face.FaceError as error:
        if error.code == "FACE_NOT_LIVE":  # looks like a photo or a replay: counts
            raise await _failed(request, session, lock, data.ticket, "face") from None
        raise BusinessRuleViolation(error.code, error.message) from None
    best: tuple[float, CustomerFace | None] = (-1.0, None)
    for saved in await session.scalars(select(CustomerFace).where(CustomerFace.phone == phone)):
        score = face.similarity(found, face.unpack(crypto.decrypt(saved.code_encrypted)))
        if score > best[0]:
            best = (score, saved)
    if best[1] is None or best[0] < face.MATCH:
        raise await _failed(request, session, lock, data.ticket, "face")
    best[1].last_used_at = _now()
    return await _success(request, response, session, lock, data.ticket, phone, "face")


@router.post("/mfa/fingerprint/options")
async def fingerprint_options(data: TicketOnly, request: Request, session: Session) -> Any:
    phone = await _ticket(request, data.ticket)
    _, rp_id = origin_for(request, PI_CUSTOMER)
    keys = list(
        await session.scalars(
            select(CustomerPasskey.credential_id).where(CustomerPasskey.phone == phone)
        )
    )
    if not keys:
        raise BusinessRuleViolation("NO_FINGERPRINT", "No fingerprint is saved for this number")
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(k)) for k in keys],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    await _store(request).put(
        f"passkey:{PI_CUSTOMER.key}:login:{data.ticket}",
        {"challenge": bytes_to_base64url(options.challenge), "rp_id": rp_id},
        TICKET_SECONDS,
    )
    return {"options": json.loads(options_to_json(options))}


@router.post("/mfa/fingerprint")
async def sign_in_with_fingerprint(
    data: FingerprintCheck, request: Request, response: Response, session: Session
) -> dict[str, Any]:
    phone = await _ticket(request, data.ticket)
    lock = await _lock(session, phone)
    origin, rp_id, challenge = await take_login(request, PI_CUSTOMER, data.ticket)
    passkey = await session.scalar(
        select(CustomerPasskey)
        .where(
            CustomerPasskey.credential_id == credential_id_of(data.credential),
            CustomerPasskey.phone == phone,
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
            user_handle=_handle(request, phone),
        )
        if passkey
        else None
    )
    if passkey is None or verified is None:
        raise await _failed(request, session, lock, data.ticket, "fingerprint")
    passkey.sign_count = verified.new_sign_count
    passkey.last_used_at = _now()
    return await _success(request, response, session, lock, data.ticket, phone, "fingerprint")


# ---- Saved faces (a fresh sign-in needed to add one) ---------------------------------


class FaceAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str = Field(min_length=16, max_length=64)
    name: str = Field("", max_length=80)
    frames: list[str] = Field(min_length=face.FRAMES, max_length=face.FRAMES)


def _face_view(f: CustomerFace) -> dict[str, Any]:
    return {"id": f.id, "name": f.name, "created_at": f.created_at, "last_used_at": f.last_used_at}


@router.get("/faces")
async def faces(customer: Customer, session: Session) -> dict[str, Any]:
    rows = await session.scalars(
        select(CustomerFace)
        .where(CustomerFace.phone == customer.phone)
        .order_by(CustomerFace.created_at)
    )
    keys = await session.scalars(
        select(CustomerPasskey)
        .where(CustomerPasskey.phone == customer.phone)
        .order_by(CustomerPasskey.created_at)
    )
    return {
        "faces": [_face_view(f) for f in rows],
        "fingerprints": [view(k) for k in keys],
        "max": MAX_FACES,
        "fresh": time.time() - (customer.expires - access.SESSION_SECONDS) <= FRESH_SECONDS,
    }


@router.post("/faces/start")
async def start_adding_face(
    request: Request, customer: Customer, session: Session
) -> dict[str, Any]:
    if not await hit(request, "customer-face-add", customer.phone, 10, 600):
        raise HTTPException(status_code=429)
    _fresh(customer)
    _crypto(request)
    count = await session.scalar(
        select(func.count()).select_from(CustomerFace).where(CustomerFace.phone == customer.phone)
    )
    if int(count or 0) >= MAX_FACES:
        raise BusinessRuleViolation(
            "TOO_MANY_FACES", f"You can save up to {MAX_FACES} faces. Remove one first."
        )
    ticket = secrets.token_urlsafe(24)
    await _store(request).put(f"customer-face-add:{ticket}", {"phone": customer.phone}, 300)
    return {"ticket": ticket, "frames": face.FRAMES}


@router.post("/faces", status_code=201)
async def add_face(
    data: FaceAdd, request: Request, customer: Customer, session: Session
) -> dict[str, Any]:
    store, key = _store(request), f"customer-face-add:{data.ticket}"
    pending = await store.get(key)
    if pending is None or pending.get("phone") != customer.phone:
        raise BusinessRuleViolation("FACE_EXPIRED", "That took too long. Start again.")
    crypto = _crypto(request)
    try:
        found = await asyncio.to_thread(face.live_frames, face.decode_frames(data.frames))
    except face.FaceError as error:
        raise BusinessRuleViolation(error.code, error.message) from None
    await store.delete(key)
    count = int(
        await session.scalar(
            select(func.count())
            .select_from(CustomerFace)
            .where(CustomerFace.phone == customer.phone)
        )
        or 0
    )
    if count >= MAX_FACES:
        raise BusinessRuleViolation("TOO_MANY_FACES", f"You can save up to {MAX_FACES} faces.")
    saved = CustomerFace(
        phone=customer.phone,
        name=(data.name.strip() or f"Face {count + 1}")[:80],
        code_encrypted=crypto.encrypt(face.pack(face.face_code(found))),
    )
    session.add(saved)
    await session.commit()
    logger.info("pi_customer_face_added")
    return _face_view(saved)


@router.delete("/faces/{face_id}", status_code=204)
async def remove_face(face_id: UUID, customer: Customer, session: Session) -> Response:
    found = await session.scalar(
        select(CustomerFace).where(CustomerFace.id == face_id, CustomerFace.phone == customer.phone)
    )
    if found is None:
        raise ResourceNotFound
    await session.delete(found)
    await session.commit()
    return Response(status_code=204)


# ---- Optional fingerprint (a fresh sign-in needed to add one) ------------------------


@router.post("/fingerprints/register/options")
async def fingerprint_register_options(
    request: Request, customer: Customer, session: Session
) -> dict[str, Any]:
    if not await hit(request, "customer-passkey-register", customer.phone, 10, 600):
        raise HTTPException(status_code=429)
    _fresh(customer)
    existing = list(
        await session.scalars(
            select(CustomerPasskey.credential_id).where(CustomerPasskey.phone == customer.phone)
        )
    )
    if len(existing) >= MAX_PASSKEYS:
        raise BusinessRuleViolation("TOO_MANY_PASSKEYS", "Remove a fingerprint before adding one")
    masked = access.mask(customer.phone)
    return await start_registration(
        request,
        PI_CUSTOMER,
        customer.phone,
        user_handle=_handle(request, customer.phone),
        user_name=masked,
        display_name=f"pi Customer {masked}",
        existing=existing,
    )


@router.post("/fingerprints/register/verify", status_code=201)
async def fingerprint_register_verify(
    data: RegisterVerify, request: Request, customer: Customer, session: Session
) -> dict[str, Any]:
    _fresh(customer)
    verified = await finish_registration(request, PI_CUSTOMER, customer.phone, data.credential)
    credential_id = bytes_to_base64url(verified.credential_id)
    if await session.scalar(
        select(CustomerPasskey.id).where(CustomerPasskey.credential_id == credential_id)
    ):
        raise BusinessRuleViolation("PASSKEY_EXISTS", "This fingerprint is already added")
    passkey = CustomerPasskey(
        phone=customer.phone,
        credential_id=credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        name=(data.name.strip() or device_name(request.headers.get("user-agent", "")))[:80],
        transports=transports_of(data.credential),
        backed_up=bool(verified.credential_backed_up),
    )
    session.add(passkey)
    await session.commit()
    return view(passkey)


@router.patch("/fingerprints/{passkey_id}")
async def rename_fingerprint(
    passkey_id: UUID, data: PasskeyRename, customer: Customer, session: Session
) -> dict[str, Any]:
    passkey = await session.scalar(
        select(CustomerPasskey).where(
            CustomerPasskey.id == passkey_id, CustomerPasskey.phone == customer.phone
        )
    )
    if passkey is None:
        raise ResourceNotFound
    passkey.name = data.name
    await session.commit()
    return view(passkey)


@router.delete("/fingerprints/{passkey_id}", status_code=204)
async def remove_fingerprint(passkey_id: UUID, customer: Customer, session: Session) -> Response:
    passkey = await session.scalar(
        select(CustomerPasskey).where(
            CustomerPasskey.id == passkey_id, CustomerPasskey.phone == customer.phone
        )
    )
    if passkey is None:
        raise ResourceNotFound
    await session.delete(passkey)
    await session.commit()
    return Response(status_code=204)
