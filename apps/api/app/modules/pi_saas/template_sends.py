"""Template sends: many numbers at once, and the history of every send.

A person on the team pastes numbers (or picks existing customers or Nori numbers), chooses one
approved text template and confirms those people agreed to be messaged. The rows are saved as
``queued`` and a worker sends them a few at a time: never more than ``DAILY_CAP`` a day, never in
the business's quiet hours, never to a number that withdrew marketing consent. Each send goes
through pi's normal outbound path (a conversation and a message with ``media.template_send``), so
the reply lands in the inbox and the delivered/read/failed status is the real WhatsApp status.
The history reads those statuses back. API: whatsapp_tools.py (/pi/whatsapp/templates/...).
"""

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.pi.models import PiConversation, PiMessage, WhatsAppConnection
from app.modules.pi.policy import zone
from app.shared.models import WorkspaceRow, workspace_args
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

DAILY_CAP = 200  # sends a day per workspace (WhatsApp tiers and the number's quality)
BATCH_SIZE = 20  # sent per worker run
MAX_ROWS = 500  # rows in one batch
QUIET_START, QUIET_END = 21, 9  # business-local hours nothing is sent
STATUSES = ("queued", "sent", "failed", "skipped", "cancelled")
SOURCES = ("single", "paste", "customers", "nori")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class PiTemplateSend(WorkspaceRow):
    """One template message to one number: queued, then handed to the outbound path."""

    __tablename__ = "pi_template_sends"
    __table_args__ = workspace_args(
        "pi_template_sends",
        UniqueConstraint(
            "tenant_id", "environment_id", "batch_id", "phone", name="uq_pi_template_send_phone"
        ),
        CheckConstraint(_in("status", STATUSES), name="status"),
        CheckConstraint(_in("source", SOURCES), name="source"),
        Index("ix_pi_template_sends_created", "tenant_id", "environment_id", "created_at"),
        Index("ix_pi_template_sends_queue", "tenant_id", "environment_id", "status"),
    )
    batch_id: Mapped[UUID] = mapped_column(Uuid)
    phone: Mapped[str] = mapped_column(String(15))
    person: Mapped[str] = mapped_column(String(120), default="", server_default="")
    template_name: Mapped[str] = mapped_column(String(512))
    template_language: Mapped[str] = mapped_column(String(16))
    values: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    source: Mapped[str] = mapped_column(String(10), default="paste", server_default="paste")
    # Who said these people agreed to be messaged, and how (kept as evidence).
    consent_note: Mapped[str] = mapped_column(String(300), default="", server_default="")
    created_by: Mapped[str] = mapped_column(String(80), default="", server_default="")
    status: Mapped[str] = mapped_column(String(10), default="queued", server_default="queued")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    message_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


async def table_ready(session: AsyncSession) -> bool:
    """False until migration 0072 has run on this database (nothing here may fail before that)."""
    from sqlalchemy import text

    return (await session.scalar(text("SELECT to_regclass('pi_template_sends')"))) is not None


# --- reading what was pasted -------------------------------------------------------------------

_SPLIT = re.compile(r"[,\t;|]")


def clean_phone(value: str) -> str | None:
    """Digits with the country code, or None. A number written locally (a leading 0) is refused:
    WhatsApp needs the country code, and guessing it would message the wrong person."""
    digits = re.sub(r"\D", "", value or "")
    return digits if 7 <= len(digits) <= 15 and not digits.startswith("0") else None


def phone_problem(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    return (
        "Add the country code (for example 92…)" if digits.startswith("0") else "Not a valid number"
    )


def parse_pasted(text: str) -> list[dict[str, Any]]:
    """One person per line: `number, name, value, value`. A header line (no digits) is ignored."""
    rows = []
    for line in (text or "").splitlines():
        parts = [p.strip() for p in _SPLIT.split(line)]
        if not parts or not parts[0] or not re.search(r"\d", parts[0]):
            continue
        rows.append(
            {"phone": parts[0], "person": parts[1] if len(parts) > 1 else "", "values": parts[2:]}
        )
    return rows


async def opted_out(session: AsyncSession, scope: WorkspaceScope, phones: list[str]) -> set[str]:
    """Numbers whose customer withdrew marketing consent (a STOP, or set by the team)."""
    from app.modules.customers.models import Customer
    from app.modules.pi_saas.models import PiCustomerConsent

    if not phones:
        return set()
    # By the customer the number belongs to (a WhatsApp id or the phone on the customer record),
    # whether or not that customer ever had a chat; and by the chats of the number.
    out: set[str] = set()
    by_customer = await session.execute(
        select(Customer.whatsapp_id, Customer.phone)
        .join(
            PiCustomerConsent,
            (PiCustomerConsent.customer_id == Customer.id)
            & (PiCustomerConsent.tenant_id == Customer.tenant_id)
            & (PiCustomerConsent.environment_id == Customer.environment_id),
        )
        .where(
            Customer.tenant_id == scope.tenant_id,
            Customer.environment_id == scope.environment_id,
            Customer.whatsapp_id.in_(phones) | Customer.phone.in_(["+" + p for p in phones]),
            PiCustomerConsent.status == "withdrawn",
        )
    )
    for whatsapp_id, phone in by_customer.all():
        for value in (whatsapp_id, (phone or "").lstrip("+")):
            if value in phones:
                out.add(value)
    by_chat = await session.scalars(
        select(PiConversation.contact_wa_id)
        .join(
            PiCustomerConsent,
            (PiCustomerConsent.customer_id == PiConversation.customer_id)
            & (PiCustomerConsent.tenant_id == PiConversation.tenant_id)
            & (PiCustomerConsent.environment_id == PiConversation.environment_id),
        )
        .where(
            PiConversation.tenant_id == scope.tenant_id,
            PiConversation.environment_id == scope.environment_id,
            PiConversation.contact_wa_id.in_(phones),
            PiCustomerConsent.status == "withdrawn",
        )
    )
    return out | set(by_chat)


async def blocked(session: AsyncSession, scope: WorkspaceScope, phones: list[str]) -> set[str]:
    """Numbers an active blocklist rule covers (the blocklist's own matching, one place)."""
    from app.modules.pi_saas.blocklist import service as blocklist

    return {p for p in phones if await blocklist.match(session, scope, p) is not None}


# What a pasted or typed value may not carry: pi never sends card, ID or bank details, a price, or a
# claim that a payment arrived under this path (R-PAY).
_PAYMENT_WORDS = re.compile(
    r"\b(?:iban|account (?:no|number)|bank (?:details|account)|payment (?:received|confirmed)"
    r"|paid|rs\.?|pkr|usd)\b|\d{9,}",
    re.IGNORECASE,
)


def value_problem(values: list[str]) -> str | None:
    """Why these template values must not be sent, or None."""
    from app.modules.pi import safety

    for value in values:
        if safety.redact_pii(value).changed or _PAYMENT_WORDS.search(value):
            return "A value looks like a card, ID, bank detail, price or payment"
    return None


async def template_block(session: AsyncSession, scope: WorkspaceScope, phone: str) -> str | None:
    """Re-checked just before delivery (and at hand-over): None means the send may go out."""
    if phone in await opted_out(session, scope, [phone]):
        return "OPTED_OUT"
    if phone in await blocked(session, scope, [phone]):
        return "BLOCKED"
    return None


async def queue_batch(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    template: dict[str, Any],
    rows: list[dict[str, Any]],
    source: str,
    consent_note: str,
    created_by: str,
) -> dict[str, Any]:
    """Save the sendable rows as queued; say which were left out and why. Sends nothing."""
    batch_id = uuid4()
    seen: set[str] = set()
    rejected: list[dict[str, str]] = []
    good: list[dict[str, Any]] = []
    for row in rows[:MAX_ROWS]:
        phone = clean_phone(str(row.get("phone") or ""))
        if phone is None:
            rejected.append(
                {
                    "phone": str(row.get("phone") or "")[:24],
                    "reason": phone_problem(str(row.get("phone") or "")),
                }
            )
        elif phone in seen:
            rejected.append({"phone": phone, "reason": "Listed twice"})
        else:
            values = [str(v).strip() for v in (row.get("values") or [])]
            if len(values) != template["variables"] or any(not v for v in values):
                rejected.append(
                    {"phone": phone, "reason": f"Needs {template['variables']} value(s)"}
                )
            elif (problem := value_problem(values)) is not None:
                rejected.append({"phone": phone, "reason": problem})
            else:
                seen.add(phone)
                good.append({**row, "phone": phone, "values": values})
    out: set[str] = set()  # sendable-looking numbers that must still be left out
    for phone in await opted_out(session, scope, [r["phone"] for r in good]):
        rejected.append({"phone": phone, "reason": "Withdrew consent (STOP)"})
        out.add(phone)
    for phone in await blocked(session, scope, [r["phone"] for r in good]):
        if phone not in out:
            rejected.append({"phone": phone, "reason": "On the blocklist"})
        out.add(phone)
    repo = WorkspaceRepository(session, PiTemplateSend, scope)
    queued = 0
    for row in good:
        if row["phone"] in out:
            continue
        await repo.add(
            repo.new(
                batch_id=batch_id,
                phone=row["phone"],
                person=str(row.get("person") or "")[:120],
                template_name=template["name"],
                template_language=template["language"],
                values=row["values"],
                source=source,
                consent_note=consent_note[:300],
                created_by=created_by[:80],
                status="queued",
            )
        )
        queued += 1
    if len(rows) > MAX_ROWS:
        rejected.append({"phone": "", "reason": f"Only the first {MAX_ROWS} rows were taken"})
    return {"batch_id": str(batch_id), "queued": queued, "rejected": rejected}


async def cancel_batch(session: AsyncSession, scope: WorkspaceScope, batch_id: UUID) -> int:
    rows = list(
        await session.scalars(
            WorkspaceRepository(session, PiTemplateSend, scope)
            .select()
            .where(PiTemplateSend.batch_id == batch_id, PiTemplateSend.status == "queued")
        )
    )
    for row in rows:
        row.status, row.error_code = "cancelled", "CANCELLED_BY_TEAM"
    return len(rows)


async def cancel_for_template(
    session: AsyncSession, scope: WorkspaceScope, name: str, language: str
) -> int:
    """A template was edited: what the recipients agreed to receive changed, so rows still queued
    for it are cancelled (the team queues them again once it is approved)."""
    rows = list(
        await session.scalars(
            WorkspaceRepository(session, PiTemplateSend, scope)
            .select()
            .where(
                PiTemplateSend.status == "queued",
                PiTemplateSend.template_name == name,
                PiTemplateSend.template_language == language,
            )
        )
    )
    for row in rows:
        row.status, row.error_code = "cancelled", "TEMPLATE_EDITED"
    return len(rows)


async def sent_today(session: AsyncSession, scope: WorkspaceScope, timezone: str) -> int:
    """Template messages handed to WhatsApp since local midnight (the daily cap counts these)."""
    local = datetime.now(UTC).astimezone(zone(timezone))
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    return int(
        await session.scalar(
            select(func.count())
            .select_from(PiTemplateSend)
            .where(
                PiTemplateSend.tenant_id == scope.tenant_id,
                PiTemplateSend.environment_id == scope.environment_id,
                PiTemplateSend.dispatched_at >= midnight,
            )
        )
        or 0
    )


# --- history -----------------------------------------------------------------------------------


def live_status(row: PiTemplateSend, message: PiMessage | None) -> str:
    """What the person sees: the real WhatsApp status once the message exists."""
    if message is None or row.status != "sent":
        return row.status
    if message.status in {"failed", "skipped"}:
        return message.status
    if message.read_at:
        return "read"
    if message.delivered_at or message.status == "delivered":
        return "delivered"
    return "sent" if message.status in {"sent", "read"} else "queued"


async def history(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    template: str | None = None,
    phone: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    full: bool = False,
) -> dict[str, Any]:
    """`full` (people who can send) sees whole numbers and the values; anyone else sees the last
    four digits and no values."""
    from app.modules.pi.staff_review import mask_phone

    query = (
        select(PiTemplateSend, PiMessage)
        .outerjoin(
            PiMessage,
            (PiMessage.id == PiTemplateSend.message_id)
            & (PiMessage.tenant_id == PiTemplateSend.tenant_id)
            & (PiMessage.environment_id == PiTemplateSend.environment_id),
        )
        .where(
            PiTemplateSend.tenant_id == scope.tenant_id,
            PiTemplateSend.environment_id == scope.environment_id,
        )
        .order_by(PiTemplateSend.created_at.desc())
    )
    if template:
        query = query.where(PiTemplateSend.template_name == template)
    digits = re.sub(r"\D", "", phone or "")
    if digits and full:  # searching by number would let a read-only person probe who was messaged
        query = query.where(PiTemplateSend.phone.like(f"%{digits}%"))
    found = (
        await session.execute(query.limit(limit * 3 if status else limit).offset(offset))
    ).all()
    items = []
    for row, message in found:
        state = live_status(row, message)
        if status and state != status:
            continue
        items.append(
            {
                "id": str(row.id),
                "batch_id": str(row.batch_id),
                "phone": row.phone if full else mask_phone(row.phone),
                "person": row.person if full else "",
                "template": row.template_name,
                "language": row.template_language,
                "values": row.values if full else [],
                "source": row.source,
                "status": state,
                "error": (message.error_code if message and message.error_code else row.error_code),
                "created_at": row.created_at.isoformat(),
                "sent_at": row.dispatched_at.isoformat() if row.dispatched_at else None,
                "conversation_id": str(row.conversation_id) if row.conversation_id else None,
            }
        )
    return {"items": items[:limit]}


async def record_single(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    phone: str,
    template: dict[str, Any],
    values: list[str],
    created_by: str,
    consent_note: str,
) -> None:
    """The one-number send also leaves a history row (it is already sent)."""
    repo = WorkspaceRepository(session, PiTemplateSend, scope)
    await repo.add(
        repo.new(
            batch_id=uuid4(),
            phone=phone,
            template_name=template["name"],
            template_language=template["language"],
            values=values,
            source="single",
            consent_note=consent_note[:300],
            created_by=created_by[:80],
            status="sent",
            dispatched_at=datetime.now(UTC),
        )
    )


# --- sending -----------------------------------------------------------------------------------


def quiet_now(timezone: str, now: datetime | None = None) -> bool:
    hour = (now or datetime.now(UTC)).astimezone(zone(timezone)).hour
    return hour >= QUIET_START or hour < QUIET_END


async def _conversation(
    session: AsyncSession,
    scope: WorkspaceScope,
    connection: WhatsAppConnection,
    row: PiTemplateSend,
) -> PiConversation:
    from app.modules.customers.service import CustomerService

    repo = WorkspaceRepository(session, PiConversation, scope)
    known = await repo.find(
        PiConversation.connection_id == connection.id,
        PiConversation.contact_wa_id == row.phone,
        PiConversation.status == "open",
    )
    if known is not None:
        return known
    customer, _ = await CustomerService(session, scope).resolve_whatsapp(
        row.phone, row.person or None
    )
    return await repo.add(
        repo.new(
            customer_id=customer.id,
            connection_id=connection.id,
            contact_wa_id=row.phone,
            last_message_at=datetime.now(UTC),
        )
    )


async def dispatch(
    session: AsyncSession, scope: WorkspaceScope, connection: WhatsAppConnection, timezone: str
) -> list[str]:
    """Hand the next few queued rows to the outbound path; returns message ids to enqueue."""
    now = datetime.now(UTC)
    if quiet_now(timezone, now):
        return []
    local = now.astimezone(zone(timezone))
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    sent_today = int(
        await session.scalar(
            select(func.count())
            .select_from(PiTemplateSend)
            .where(
                PiTemplateSend.tenant_id == scope.tenant_id,
                PiTemplateSend.environment_id == scope.environment_id,
                PiTemplateSend.dispatched_at >= midnight,
            )
        )
        or 0
    )
    room = min(BATCH_SIZE, DAILY_CAP - sent_today)
    from app.modules.pi_saas.entitlement import remaining as allowance_left

    left = await allowance_left(session, scope.tenant_id, scope.environment_id, "messages_out")
    if left is not None:
        room = min(room, int(left))
    if room <= 0:
        return []
    pending = list(
        await session.scalars(
            WorkspaceRepository(session, PiTemplateSend, scope)
            .select()
            .where(PiTemplateSend.status == "queued")
            .order_by(PiTemplateSend.created_at)
            .limit(room)
            .with_for_update(skip_locked=True)
        )
    )
    messages = WorkspaceRepository(session, PiMessage, scope)
    queued: list[str] = []
    for row in pending:
        # Days can pass between queueing and sending: consent and the blocklist are checked again.
        if (why := await template_block(session, scope, row.phone)) is not None:
            row.status, row.error_code = "skipped", why
            continue
        conversation = await _conversation(session, scope, connection, row)
        message = await messages.add(
            messages.new(
                conversation_id=conversation.id,
                direction="outbound",
                sender_type="system",
                body=f"Template: {row.template_name}",
                status="queued",
                idempotency_key=f"pi-template-send:{row.id}",
                media={
                    "template_send": {
                        "template": {
                            "name": row.template_name,
                            "language": row.template_language,
                        },
                        "values": list(row.values),
                    }
                },
            )
        )
        row.status, row.dispatched_at = "sent", now
        row.conversation_id, row.message_id = conversation.id, message.id
        queued.append(str(message.id))
    return queued


async def sweep_template_sends(ctx: dict[str, Any]) -> None:
    from app.modules.pi.configuration import settings_row
    from app.modules.pi.runtime import enqueue_sends, system_scope

    outgoing: list[str] = []
    async with ctx["sessions"]() as session:
        try:
            waiting = (
                await session.execute(
                    select(PiTemplateSend.tenant_id, PiTemplateSend.environment_id)
                    .where(
                        PiTemplateSend.status == "queued",
                        PiTemplateSend.created_at < datetime.now(UTC) + timedelta(seconds=1),
                    )
                    .group_by(PiTemplateSend.tenant_id, PiTemplateSend.environment_id)
                    .order_by(func.min(PiTemplateSend.created_at))  # the longest waiting first
                    .limit(200)
                )
            ).all()
        except ProgrammingError:
            # The table does not exist yet (migration 0072 not applied here): nothing to send.
            await session.rollback()
            return
        for tenant_id, environment_id in waiting:
            connection = await session.scalar(
                select(WhatsAppConnection).where(
                    WhatsAppConnection.tenant_id == tenant_id,
                    WhatsAppConnection.environment_id == environment_id,
                    WhatsAppConnection.status == "active",
                )
            )
            scope = await system_scope(session, connection) if connection else None
            if connection is None or scope is None:
                continue  # waits, visibly "queued", until WhatsApp reconnects
            policy = await settings_row(session, scope)
            outgoing += await dispatch(session, scope, connection, policy.timezone)
        await session.commit()
    await enqueue_sends(ctx, outgoing)
