"""PI Customer API, mounted at /api/v1/pi-app/customer-portal (the Pi app's origin and
proxy). It never uses business sessions: only the signed customer cookie from access.py."""

import hmac
import logging
import time
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.rate_limit import client_ip, hit
from app.modules.access.dependencies import Session
from app.modules.customers.schemas import normalize_phone
from app.modules.pi.whatsapp import WhatsApp
from app.modules.pi_customer import access, service
from app.modules.pi_customer.access import CustomerSession
from app.shared.errors import BusinessRuleViolation

logger = logging.getLogger("platform")
router = APIRouter(prefix="/customer-portal", tags=["pi-customer"])
Customer = Annotated[CustomerSession, Depends(access.current)]

CODE_MESSAGE = (
    "Your PI Customer code: *{code}*\n"
    "Aap ka PI Customer code: *{code}*\n\n"
    "It expires in 10 minutes. Never share this code with anyone."
)


class PhoneInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str = Field(min_length=6, max_length=32)


class VerifyInput(PhoneInput):
    code: str = Field(pattern=r"^[0-9]{6}$")


def _digits(raw: str) -> str:
    try:
        phone = normalize_phone(raw)
    except ValueError:
        phone = None
    if not phone:
        raise HTTPException(422, "Enter your WhatsApp number with country code")
    return phone[1:]


def _wa_link(display_phone: str) -> str:
    digits = "".join(ch for ch in display_phone if ch.isdigit())
    return f"https://wa.me/{digits}" if digits else ""


@router.post("/code", status_code=202)
async def send_code(body: PhoneInput, request: Request, session: Session) -> dict[str, Any]:
    """Sends a sign-in code on WhatsApp from a business this number wrote to in the last
    24 hours. The answer is the same whether or not a code was sent, so the endpoint
    never reveals who has conversations."""
    phone = _digits(body.phone)
    if not await hit(request, "pi-customer-code-ip", client_ip(request), 10, 3600) or not (
        await hit(request, "pi-customer-code-phone", phone, 3, 900)
    ):
        raise HTTPException(429, "Too many codes requested. Please wait a few minutes.")
    settings, http = request.app.state.settings, request.app.state.http
    store = access.code_store(request)
    channel = service.reply_channel(await service.conversations(session, phone))
    if channel is not None:
        from app.integrations.whatsapp_bridge import token as connection_token

        code = access.new_code()
        try:
            await store.put(
                access.code_key(settings, phone),
                {
                    "h": access.code_hash(settings, phone, code),
                    "t": 0,
                    "e": int(time.time()) + access.CODE_SECONDS,
                },
                access.CODE_SECONDS,
            )
        except Exception:  # noqa: BLE001 - no code store: fail closed
            logger.warning("pi_customer_code_store_unavailable")
            raise HTTPException(503, "Sign-in is unavailable right now") from None
        _, connection = channel
        try:
            await WhatsApp(settings, http, connection.provider).send(
                connection.phone_number_id,
                phone,
                CODE_MESSAGE.format(code=code),
                await connection_token(session, settings, connection),
            )
            logger.info("pi_customer_code_sent")
        except BusinessRuleViolation:
            logger.warning("pi_customer_code_not_sent")
    return {"sent": True, "expires_in": access.CODE_SECONDS}


@router.post("/verify")
async def verify(body: VerifyInput, request: Request, response: Response) -> dict[str, Any]:
    phone = _digits(body.phone)
    if not await hit(request, "pi-customer-verify-ip", client_ip(request), 30, 3600):
        raise HTTPException(429, "Too many attempts. Please wait a few minutes.")
    settings = request.app.state.settings
    store, key = access.code_store(request), access.code_key(settings, phone)
    wrong = HTTPException(400, "That code is wrong or has expired. Request a new code.")
    try:
        record = await store.get(key)
        if record is None:
            raise wrong
        if int(record.get("t", 0)) >= access.MAX_TRIES:
            await store.delete(key)
            raise wrong
        if not hmac.compare_digest(
            str(record.get("h", "")), access.code_hash(settings, phone, body.code)
        ):
            remaining = int(record.get("e", 0)) - int(time.time())
            if remaining > 0:
                await store.put(key, {**record, "t": int(record.get("t", 0)) + 1}, remaining)
            raise wrong
        await store.delete(key)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - no code store: fail closed
        logger.warning("pi_customer_code_store_unavailable")
        raise HTTPException(503, "Sign-in is unavailable right now") from None
    access.issue(response, settings, phone)
    logger.info("pi_customer_signed_in")
    return {"phone": access.mask(phone)}


@router.post("/sign-out", status_code=204)
async def sign_out(customer: Customer, request: Request, response: Response) -> Response:
    access.clear(response, request.app.state.settings)
    response.status_code = 204
    return response


@router.get("/me")
async def me(customer: Customer) -> dict[str, Any]:
    return {"phone": access.mask(customer.phone), "expires_at": customer.expires}


@router.get("/conversations")
async def list_conversations(customer: Customer, session: Session) -> list[dict[str, Any]]:
    items = await service.conversations(session, customer.phone)
    out = []
    for conversation, connection, business in items:
        cached = (conversation.service_brief or {}).get("customer_issues")
        issues = cached.get("issues", []) if isinstance(cached, dict) else []
        out.append(
            {
                "id": conversation.id,
                "business": business,
                "business_phone": connection.display_phone_number,
                "whatsapp_link": _wa_link(connection.display_phone_number),
                "status": conversation.status,
                "last_message_at": conversation.last_message_at,
                "preview": conversation.last_message_preview,
                "with_team": conversation.mode == "human",
                "issues_open": sum(1 for i in issues if i.get("status") != "resolved"),
                "issues_total": len(issues),
                # Open matters first, for the dashboard's request overview.
                "issues_preview": [
                    {
                        "title": i.get("title", ""),
                        "status": i.get("status", "open"),
                        "category": i.get("category", "other"),
                    }
                    for i in sorted(issues, key=lambda i: i.get("status") == "resolved")[:3]
                ],
            }
        )
    return out


async def _owned(
    session: Any, customer: CustomerSession, conversation_id: UUID
) -> tuple[Any, Any, str]:
    found = await service.one(session, customer.phone, conversation_id)
    if found is None:
        raise HTTPException(404, "Conversation not found")
    return found


@router.get("/conversations/{conversation_id}")
async def conversation_detail(
    conversation_id: UUID, customer: Customer, session: Session
) -> dict[str, Any]:
    conversation, connection, business = await _owned(session, customer, conversation_id)
    cached = (conversation.service_brief or {}).get("customer_issues")
    fresh = isinstance(cached, dict) and cached.get("at") == (
        conversation.last_message_at.isoformat()
    )
    return {
        "id": conversation.id,
        "business": business,
        "business_phone": connection.display_phone_number,
        "whatsapp_link": _wa_link(connection.display_phone_number),
        "status": conversation.status,
        "with_team": await service.handoff_open(session, conversation),
        "last_message_at": conversation.last_message_at,
        "messages": [
            service.message_view(m) for m in await service.messages(session, conversation)
        ],
        "requests": await service.open_requests(session, conversation),
        "issues": cached if fresh else None,
    }


@router.get("/conversations/{conversation_id}/issues")
async def conversation_issues(
    conversation_id: UUID, customer: Customer, request: Request, session: Session
) -> dict[str, Any]:
    """The AI list of separate requests (cached until a new message arrives)."""
    if not await hit(request, "pi-customer-issues", customer.phone, 30, 3600):
        raise HTTPException(429, "Please wait a moment and try again.")
    state = request.app.state
    conversation, connection, business = await _owned(session, customer, conversation_id)
    report = await service.analyse(
        session,
        state.settings,
        state.http,
        state.sessions,
        conversation,
        connection,
        business,
    )
    if report is None:
        return {"available": False, "issues": [], "at": None}
    return {"available": True, **report}


@router.get("/conversations/{conversation_id}/messages/{message_id}/media")
async def message_media(
    conversation_id: UUID, message_id: UUID, customer: Customer, request: Request, session: Session
) -> Response:
    from app.integrations.whatsapp_bridge import token as connection_token

    settings, http = request.app.state.settings, request.app.state.http
    conversation, connection, _ = await _owned(session, customer, conversation_id)
    message = next(
        (m for m in await service.messages(session, conversation) if m.id == message_id),
        None,
    )
    view = service.message_view(message) if message is not None else None
    if message is None or view is None or not view["has_media"]:
        raise HTTPException(404, "No file for this message")
    media = message.media or {}
    try:
        content, mime = await WhatsApp(settings, http, connection.provider).media(
            str(media.get("provider_media_id") or ""),
            await connection_token(session, settings, connection),
            url=str(media.get("media_url") or ""),
            mime=str(media.get("mime_type") or ""),
        )
    except BusinessRuleViolation:
        raise HTTPException(404, "This file is no longer available") from None
    return Response(
        content,
        media_type=mime,
        headers={"Content-Disposition": "inline", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/conversations/{conversation_id}/team")
async def ask_for_team(
    conversation_id: UUID, customer: Customer, request: Request, session: Session
) -> dict[str, Any]:
    """The customer asks for a person: the business's team gets a handoff and the
    customer gets the usual notice on WhatsApp."""
    from app.modules.pi.runtime import hand_off, system_scope

    conversation, connection, _ = await _owned(session, customer, conversation_id)
    if await service.handoff_open(session, conversation):
        return {"status": "with_team"}
    scope = await system_scope(session, connection)
    if scope is None:
        raise HTTPException(409, "This business can't take requests right now")
    notice = await hand_off(
        session,
        scope,
        conversation.id,
        "customer_request",
        "The customer asked for a person from PI Customer.",
    )
    await session.commit()
    if notice:
        await request.app.state.queue.enqueue("send_pi_message", notice, job_id=f"send:{notice}")
    return {"status": "with_team"}
