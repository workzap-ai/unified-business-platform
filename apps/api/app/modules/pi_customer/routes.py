"""PI Customer API, mounted at /api/v1/pi-app/customer-portal (the Pi app's origin and
proxy). It never uses business sessions: only the signed customer cookie from access.py."""

import hashlib
import hmac
import logging
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.rate_limit import client_ip, hit
from app.modules.access.dependencies import Session
from app.modules.customers.schemas import normalize_phone
from app.modules.pi.whatsapp import WhatsApp
from app.modules.pi_customer import access, service
from app.modules.pi_customer.access import CustomerSession
from app.modules.pi_customer.models import CustomerPrefs, CustomerShareLink
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


LANGUAGES = ("auto", "en", "roman_ur", "ur", "ar")
SHARE_DAYS = 7


class WaitingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # 0 clears it: "I'm back, carry on".
    days: int = Field(default=5, ge=0, le=14)


class PrefsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Literal["auto", "en", "roman_ur", "ur", "ar"]


class ShareInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: UUID | None = None


async def _prefs(session: Any, phone: str) -> CustomerPrefs | None:
    prefs: CustomerPrefs | None = await session.scalar(
        select(CustomerPrefs).where(CustomerPrefs.phone == phone)
    )
    return prefs


async def _language(session: Any, phone: str) -> str:
    prefs = await _prefs(session, phone)
    return prefs.language if prefs and prefs.language in LANGUAGES else "auto"


def _waiting_until(conversation: Any) -> datetime | None:
    raw = (conversation.service_brief or {}).get("customer_waiting_until")
    try:
        return datetime.fromisoformat(raw) if raw else None
    except ValueError:
        return None


async def _views(
    session: Any, conversation: Any, report: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Each issue as the customer sees it, with the business's department name (and the
    team's own moves), whose turn it is and when the team's next update is due."""
    if not isinstance(report, dict):
        return []
    departments, _ = await service.departments_for(
        session, conversation.tenant_id, conversation.environment_id
    )
    overrides = (conversation.service_brief or {}).get("issue_departments") or {}
    names = {d["key"]: d["name"] for d in departments}
    hours = await service.team_update_hours(session, conversation)
    until = _waiting_until(conversation)
    return [
        service.issue_view(
            {**i, "department_name": names.get(i["department"], "")}, report, until, hours
        )
        for i in service.place(report.get("issues", []), departments, overrides)
    ]


LINK_FIELDS = ("a", "b", "a_title", "b_title", "type", "reason", "benefit", "confidence")


def _links(report: Any) -> list[dict[str, Any]]:
    """Links the customer may see: automatic or team-confirmed, never ones under review."""
    if not isinstance(report, dict):
        return []
    return [
        {key: link.get(key) for key in LINK_FIELDS}
        for link in report.get("links") or []
        if isinstance(link, dict) and link.get("status") in ("auto", "confirmed")
    ]


def _counts(issues: list[dict[str, Any]]) -> dict[str, int]:
    """Every number on the dashboard counts requests, in the same four buckets."""
    out = {"waiting_on_you": 0, "waiting_on_other": 0, "waiting_on_us": 0, "done": 0, "paused": 0}
    for i in issues:
        if i["stage"] in ("live", "closed"):
            out["done"] += 1
        elif i["stage"] == "paused":
            out["paused"] += 1
        elif i["waiting_on_other_until"]:
            out["waiting_on_other"] += 1
        elif i["ball_with"] == "client":
            out["waiting_on_you"] += 1
        else:
            out["waiting_on_us"] += 1
    return out


def _fresh(conversation: Any) -> bool:
    cached = (conversation.service_brief or {}).get("customer_issues")
    return isinstance(cached, dict) and cached.get("at") == conversation.last_message_at.isoformat()


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
async def verify(
    body: VerifyInput, request: Request, response: Response, session: Session
) -> dict[str, Any]:
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
    # Saved a face or a fingerprint? Then the code alone isn't enough.
    from app.modules.pi_customer.second_step import second_step

    step = await second_step(request, session, phone)
    if step is not None:
        return step
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
        issues = await _views(session, conversation, cached)
        counts = _counts(issues)
        headline = cached.get("headline", "") if isinstance(cached, dict) else ""
        out.append(
            {
                "id": conversation.id,
                "business": business,
                "business_phone": connection.display_phone_number,
                "whatsapp_link": _wa_link(connection.display_phone_number),
                "status": conversation.status,
                "last_message_at": conversation.last_message_at,
                # pi's one line about where things stand, not the last raw message.
                "headline": headline,
                "preview": conversation.last_message_preview,
                "with_team": conversation.mode == "human",
                "issues_fresh": _fresh(conversation),
                "issues_total": len(issues),
                "issues_open": len(issues) - counts["done"],
                "counts": counts,
                "waiting_on_other_until": _waiting_until(conversation),
                # Every request, so the dashboard's numbers always add up.
                "issues": issues,
                "links": _links(cached),
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
    fresh = (
        _fresh(conversation)
        and isinstance(cached, dict)
        and cached.get("language", "auto") == await _language(session, customer.phone)
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
        "waiting_on_other_until": _waiting_until(conversation),
        "issues": (
            {
                **cached,
                "issues": await _views(session, conversation, cached),
                "links": _links(cached),
            }
            if fresh and isinstance(cached, dict)
            else None
        ),
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
        await _language(session, customer.phone),
    )
    if report is None:
        return {"available": False, "issues": [], "at": None}
    report.pop("new_events", None)
    return {
        "available": True,
        **report,
        "issues": await _views(session, conversation, report),
        "links": _links(report),
    }


@router.post("/conversations/{conversation_id}/waiting")
async def waiting_on_someone(
    conversation_id: UUID, body: WaitingInput, customer: Customer, session: Session
) -> dict[str, Any]:
    """ "I'm waiting on someone else" (a boss, a partner): pi stops reminding them about
    this chat for a few days. days=0 means they are back."""
    from sqlalchemy import cast, func, update
    from sqlalchemy.dialects.postgresql import JSONB

    from app.modules.pi.models import PiConversation

    conversation, _, _ = await _owned(session, customer, conversation_id)
    until = datetime.now(UTC) + timedelta(days=body.days) if body.days else None
    await session.execute(
        update(PiConversation)
        .where(
            PiConversation.tenant_id == conversation.tenant_id,
            PiConversation.id == conversation.id,
        )
        .values(
            service_brief=func.coalesce(PiConversation.service_brief, cast({}, JSONB)).op("||")(
                cast({"customer_waiting_until": until.isoformat() if until else None}, JSONB)
            )
        )
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    await session.refresh(conversation)  # later reads in this session see the change
    return {"waiting_on_other_until": until}


@router.get("/prefs")
async def get_prefs(customer: Customer, session: Session) -> dict[str, Any]:
    prefs = await _prefs(session, customer.phone)
    return {
        "language": prefs.language if prefs else "auto",
        "last_seen_at": prefs.last_seen_at if prefs else None,
    }


@router.put("/prefs")
async def put_prefs(body: PrefsInput, customer: Customer, session: Session) -> dict[str, Any]:
    prefs = await _prefs(session, customer.phone)
    if prefs is None:
        prefs = CustomerPrefs(phone=customer.phone)
        session.add(prefs)
    prefs.language = body.language
    await session.commit()
    return {"language": prefs.language, "last_seen_at": prefs.last_seen_at}


@router.post("/seen")
async def seen(customer: Customer, session: Session) -> dict[str, Any]:
    """Marks the dashboard as looked at; returns the previous time, for "since you last
    looked"."""
    prefs = await _prefs(session, customer.phone)
    if prefs is None:
        prefs = CustomerPrefs(phone=customer.phone)
        session.add(prefs)
    previous = prefs.last_seen_at
    prefs.last_seen_at = datetime.now(UTC)
    await session.commit()
    return {"previous": previous}


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _share_view(link: CustomerShareLink) -> dict[str, Any]:
    return {
        "id": link.id,
        "conversation_id": link.conversation_id,
        "expires_at": link.expires_at,
        "views": link.views,
        "created_at": link.created_at,
    }


@router.post("/share", status_code=201)
async def create_share(
    body: ShareInput, customer: Customer, request: Request, session: Session
) -> dict[str, Any]:
    """A view-only link to forward (to a boss, a partner): requests and next steps only,
    no chat, files or prices. It opens without signing in and expires in seven days."""
    if not await hit(request, "pi-customer-share", customer.phone, 20, 3600):
        raise HTTPException(429, "Too many links. Please wait a little.")
    if body.conversation_id is not None:
        await _owned(session, customer, body.conversation_id)
    token = secrets.token_urlsafe(24)
    link = CustomerShareLink(
        phone=customer.phone,
        token_hash=_token_hash(token),
        conversation_id=body.conversation_id,
        expires_at=datetime.now(UTC) + timedelta(days=SHARE_DAYS),
    )
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return {**_share_view(link), "token": token}


@router.get("/share")
async def list_shares(customer: Customer, session: Session) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(CustomerShareLink)
        .where(
            CustomerShareLink.phone == customer.phone,
            CustomerShareLink.revoked_at.is_(None),
            CustomerShareLink.expires_at > datetime.now(UTC),
        )
        .order_by(CustomerShareLink.created_at.desc())
        .limit(20)
    )
    return [_share_view(link) for link in rows]


@router.delete("/share/{link_id}", status_code=204)
async def revoke_share(link_id: UUID, customer: Customer, session: Session) -> Response:
    link = await session.scalar(
        select(CustomerShareLink).where(
            CustomerShareLink.id == link_id, CustomerShareLink.phone == customer.phone
        )
    )
    if link is None:
        raise HTTPException(404, "Link not found")
    link.revoked_at = datetime.now(UTC)
    await session.commit()
    return Response(status_code=204)


@router.get("/shared/{token}")
async def open_share(token: str, request: Request, session: Session) -> dict[str, Any]:
    """What a shared link shows: each business, its requests, whose turn and next step.
    Never the chat, files, prices or the customer's number."""
    if not await hit(request, "pi-customer-shared-ip", client_ip(request), 60, 3600):
        raise HTTPException(429, "Please wait a moment and try again.")
    link = await session.scalar(
        select(CustomerShareLink).where(CustomerShareLink.token_hash == _token_hash(token[:64]))
    )
    now = datetime.now(UTC)
    if link is None or link.revoked_at is not None or link.expires_at <= now:
        raise HTTPException(404, "This link has expired or was turned off.")
    link.views += 1
    items = await service.conversations(session, link.phone)
    if link.conversation_id is not None:
        items = [item for item in items if item[0].id == link.conversation_id]
    out = []
    for conversation, _, business in items:
        cached = (conversation.service_brief or {}).get("customer_issues")
        issues = await _views(session, conversation, cached)
        if not issues:
            continue
        out.append(
            {
                "business": business,
                "counts": _counts(issues),
                "links": _links(cached),
                "issues": [
                    {
                        key: i.get(key)
                        for key in (
                            "title",
                            "category",
                            "stage",
                            "ball_with",
                            "summary",
                            "next_step",
                            "next_step_owner",
                            "open_question",
                            "next_update_by",
                            "waiting_on_other_until",
                            "journey_steps",
                            "area",
                            "urgency",
                            "impact",
                            "solution_id",
                            "linked",
                        )
                    }
                    for i in issues
                ],
            }
        )
    await session.commit()
    return {"expires_at": link.expires_at, "businesses": out}


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


class NotRelatedInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a_title: str = Field(min_length=1, max_length=120)
    b_title: str = Field(min_length=1, max_length=120)


@router.get("/conversations/{conversation_id}/timeline")
async def conversation_timeline(
    conversation_id: UUID, customer: Customer, session: Session
) -> list[dict[str, Any]]:
    conversation, _, _ = await _owned(session, customer, conversation_id)
    return await service.timeline(session, conversation)


@router.post("/conversations/{conversation_id}/links/not-related")
async def not_related(
    conversation_id: UUID, body: NotRelatedInput, customer: Customer, session: Session
) -> dict[str, Any]:
    """The customer says two requests aren't connected: the line goes and pi never links
    that pair again (the team sees it, to tune what pi links)."""
    from sqlalchemy import cast, func, update
    from sqlalchemy.dialects.postgresql import JSONB

    from app.modules.pi.models import PiConversation

    conversation, _, _ = await _owned(session, customer, conversation_id)
    brief = dict(conversation.service_brief or {})
    key = service.pair_key(body.a_title, body.b_title)
    feedback = {**(brief.get("link_feedback") or {}), key: "rejected"}
    report = brief.get("customer_issues")
    patch: dict[str, Any] = {"link_feedback": feedback}
    if isinstance(report, dict):
        links = [
            x
            for x in report.get("links") or []
            if service.pair_key(x.get("a_title", ""), x.get("b_title", "")) != key
        ]
        base = [
            {k: v for k, v in i.items() if k not in ("solution_id", "linked")}
            for i in report.get("issues", [])
        ]
        patch["customer_issues"] = {
            **report,
            "links": links,
            "issues": service.with_solutions(base, links),
        }
    await session.execute(
        update(PiConversation)
        .where(
            PiConversation.tenant_id == conversation.tenant_id,
            PiConversation.id == conversation.id,
        )
        .values(
            service_brief=func.coalesce(PiConversation.service_brief, cast({}, JSONB)).op("||")(
                cast(patch, JSONB)
            )
        )
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    await session.refresh(conversation)
    return {"removed": key}


@router.get("/stream")
async def stream(customer: Customer, request: Request) -> Any:
    """Server-sent events: "update" whenever any of the customer's chats changes (a new
    message, or pi's map of their requests), so an open dashboard redraws within
    seconds. Each stream ends after five minutes; the browser reconnects."""
    import asyncio

    from fastapi.responses import StreamingResponse

    sessions = request.app.state.sessions
    phone = customer.phone

    async def signature() -> str:
        async with sessions() as db:
            items = await service.conversations(db, phone)
        parts = []
        for conversation, _, _ in items:
            cached = (conversation.service_brief or {}).get("customer_issues")
            stamp = cached.get("at") if isinstance(cached, dict) else ""
            parts.append(f"{conversation.id}:{conversation.last_message_at}:{stamp}")
        return "|".join(parts)

    async def events() -> Any:
        last = await signature()
        yield "retry: 5000\n\n"
        for tick in range(100):  # about five minutes
            if await request.is_disconnected():
                return
            await asyncio.sleep(3)
            try:
                now = await signature()
            except Exception:  # noqa: BLE001 - the browser falls back to polling
                return
            if now != last:
                last = now
                yield "event: update\ndata: {}\n\n"
            elif tick % 5 == 4:
                yield ": keep-alive\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/card/{token}")
async def card_data(token: str, request: Request, session: Session) -> dict[str, Any]:
    """What a WhatsApp card shows, for the pi app that draws it. The signed token is the
    only key; it names one chat and expires in seven days. No chat text, no number."""
    from app.modules.pi_customer.cards import read_card

    claims = read_card(request.app.state.settings, token)
    if claims is None:
        raise HTTPException(404, "This card has expired.")
    from app.modules.pi.models import PiConversation

    conversation = await session.scalar(
        select(PiConversation).where(PiConversation.id == claims["conversation_id"])
    )
    if conversation is None:
        raise HTTPException(404, "This card has expired.")
    cached = (conversation.service_brief or {}).get("customer_issues")
    issues = await _views(session, conversation, cached)
    keep = (
        "title",
        "stage",
        "ball_with",
        "area",
        "urgency",
        "impact",
        "open_question",
        "next_step",
        "next_update_by",
        "journey_steps",
        "root_cause",
        "solution_outline",
        "outcome",
        "solution_id",
        "linked",
    )
    return {
        "kind": claims["kind"],
        "index": claims["index"],
        "language": (cached or {}).get("language", "auto") if isinstance(cached, dict) else "auto",
        "issues": [{k: i.get(k) for k in keep} for i in issues],
        "links": _links(cached),
    }
