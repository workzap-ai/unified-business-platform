"""WhatsApp campaigns and customer consent for the standalone Pi product.

Rules:
- Only customers with **marketing consent** (recorded with its source) are ever in an
  audience. Replying STOP (or "band karo", "مت بھیجو", ...) withdraws it immediately and
  drops them from running campaigns.
- Campaigns send one approved, no-variable WhatsApp template (the only kind the platform
  can send outside the 24-hour customer-service window), checked against Meta before
  scheduling and again at every send.
- Sending never happens during quiet hours in the business's time zone and never exceeds
  the campaign's daily limit or recipient cap.
- Every send is re-checked just before delivery: campaign still sending, consent still
  granted, conversation not being handled by a person. Results come from the real
  message statuses (sent / delivered / read / failed) plus customer replies.
"""

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import record
from app.modules.pi.models import PiConversation, PiMessage, WhatsAppConnection
from app.modules.pi.policy import zone
from app.modules.pi_saas.models import (
    PiBusinessAccount,
    PiCampaign,
    PiCampaignRecipient,
    PiConversationTag,
    PiCustomerConsent,
    PiPlan,
    PiSubscription,
)
from app.shared.errors import BusinessRuleViolation, Conflict
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

TEMPLATE_NAME = r"^[a-z0-9_]{1,512}$"
TEMPLATE_LANGUAGE = r"^[a-z]{2,3}(_[A-Z]{2})?$"
BATCH = 50
# A short message that is only an opt-out request. Matching the whole message avoids
# treating "please don't stop the order" as an opt-out.
OPT_OUT = re.compile(
    r"^\W*(?:stop|unsubscribe|opt[\s-]?out|no more messages|band\s*karo|band\s*kar\s*do"
    r"|mat\s*bhejo|message\s*mat\s*bhejo|بند\s*کریں|مت\s*بھیجو|توقف|إلغاء)\W*$",
    re.IGNORECASE,
)


class ConsentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    purpose: str = Field(pattern=r"^(marketing|reminders)$")
    granted: bool
    # Where the customer agreed (required for opt-in): "Signed up at the shop counter".
    source: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def _evidence(self) -> "ConsentInput":
        if self.granted and len(self.source) < 5:
            raise ValueError("Say how the customer agreed")
        return self


class CampaignInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    template_name: str = Field(pattern=TEMPLATE_NAME)
    template_language: str = Field(pattern=TEMPLATE_LANGUAGE)
    audience_tag: str | None = Field(default=None, max_length=40)
    max_recipients: int = Field(default=500, ge=1, le=10_000)
    daily_limit: int = Field(default=200, ge=1, le=5_000)
    quiet_start: int = Field(default=21, ge=0, le=23)
    quiet_end: int = Field(default=9, ge=0, le=23)


class ScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scheduled_at: datetime | None = None


# ------------------------------------------------------------------------- consent


async def set_consent(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: UUID,
    purpose: str,
    granted: bool,
    source: str,
    message_id: UUID | None = None,
) -> PiCustomerConsent:
    repo = WorkspaceRepository(session, PiCustomerConsent, scope)
    row = await repo.find(
        PiCustomerConsent.customer_id == customer_id, PiCustomerConsent.purpose == purpose
    )
    if row is None:
        row = repo.new(customer_id=customer_id, purpose=purpose, status="withdrawn")
        await repo.add(row)
    before = row.status
    row.status = "granted" if granted else "withdrawn"
    row.source, row.source_message_id = source[:300], message_id
    if not granted and purpose == "marketing":
        await _drop_pending(session, scope, customer_id, "OPTED_OUT")
    if before != row.status:
        await record(
            session,
            f"pi.consent_{row.status}",
            scope=scope,
            entity_type="customer",
            entity_id=customer_id,
            details={"purpose": purpose, "source": source[:120]},
        )
    return row


async def consent_granted(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, purpose: str
) -> bool:
    row = await WorkspaceRepository(session, PiCustomerConsent, scope).find(
        PiCustomerConsent.customer_id == customer_id, PiCustomerConsent.purpose == purpose
    )
    return row is not None and row.status == "granted"


async def note_opt_out(session: AsyncSession, scope: WorkspaceScope, message: PiMessage) -> bool:
    """A customer replying only "STOP" (in any language we serve) withdraws marketing and
    reminder consent at once. Returns True when it was an opt-out."""
    body = (message.body or "").strip()
    if message.direction != "inbound" or len(body) > 40 or not OPT_OUT.match(body):
        return False
    conversation = await WorkspaceRepository(session, PiConversation, scope).get(
        message.conversation_id
    )
    if conversation.customer_id is None:
        return False
    note = f'Customer replied "{body[:40]}" on WhatsApp'
    for purpose in ("marketing", "reminders"):
        await set_consent(
            session, scope, conversation.customer_id, purpose, False, note, message.id
        )
    brief = dict(conversation.service_brief or {})
    if brief.get("reminder_consent") == "granted":
        brief["reminder_consent"] = "declined"
        conversation.service_brief = brief
    conversation.followup_due_at = None
    return True


async def _drop_pending(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, code: str
) -> None:
    rows = await session.scalars(
        WorkspaceRepository(session, PiCampaignRecipient, scope)
        .select()
        .where(
            PiCampaignRecipient.customer_id == customer_id,
            PiCampaignRecipient.status == "pending",
        )
    )
    for row in rows:
        row.status, row.error_code = "skipped", code


# ------------------------------------------------------------------------ audience


def _latest_contacts(scope: WorkspaceScope, session: AsyncSession, tag: str | None) -> Any:
    """Most recent conversation per consented customer (for the WhatsApp contact)."""
    consented = (
        WorkspaceRepository(session, PiCustomerConsent, scope)
        .select()
        .with_only_columns(PiCustomerConsent.customer_id)
        .where(PiCustomerConsent.purpose == "marketing", PiCustomerConsent.status == "granted")
    )
    query = (
        WorkspaceRepository(session, PiConversation, scope)
        .select()
        .where(
            PiConversation.customer_id.is_not(None),
            PiConversation.customer_id.in_(consented),
        )
        .distinct(PiConversation.customer_id)
        .order_by(PiConversation.customer_id, PiConversation.created_at.desc())
    )
    if tag:
        tagged = (
            WorkspaceRepository(session, PiConversationTag, scope)
            .select()
            .with_only_columns(PiConversationTag.conversation_id)
            .where(PiConversationTag.tag == tag.strip().lower()[:40])
        )
        query = query.where(PiConversation.id.in_(tagged))
    return query


async def audience_size(session: AsyncSession, scope: WorkspaceScope, tag: str | None) -> int:
    query = _latest_contacts(scope, session, tag)
    return int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)


# ------------------------------------------------------------------------ lifecycle


def view(row: PiCampaign, results: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "template_name": row.template_name,
        "template_language": row.template_language,
        "audience_tag": row.audience_tag,
        "status": row.status,
        "scheduled_at": row.scheduled_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "max_recipients": row.max_recipients,
        "daily_limit": row.daily_limit,
        "quiet_start": row.quiet_start,
        "quiet_end": row.quiet_end,
        "results": results if results is not None else row.results,
        "created_at": row.created_at,
    }


async def create(session: AsyncSession, scope: WorkspaceScope, data: CampaignInput) -> PiCampaign:
    scope.require("pi.campaigns.manage")
    repo = WorkspaceRepository(session, PiCampaign, scope)
    row = repo.new(
        **data.model_dump(),
        status="draft",
        created_by_user_id=scope.user_id,
    )
    await repo.add(row)
    await record(
        session, "pi.campaign_created", scope=scope, entity_type="pi_campaign", entity_id=row.id
    )
    return row


async def update(
    session: AsyncSession, scope: WorkspaceScope, campaign_id: UUID, data: CampaignInput
) -> PiCampaign:
    scope.require("pi.campaigns.manage")
    row = await WorkspaceRepository(session, PiCampaign, scope).get(campaign_id, for_update=True)
    if row.status != "draft":
        raise Conflict("Only a draft campaign can be edited")
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    return row


async def plan_allows_campaigns(session: AsyncSession, tenant_id: UUID) -> bool:
    account = await session.scalar(
        select(PiBusinessAccount).where(PiBusinessAccount.tenant_id == tenant_id)
    )
    if account is None:
        return True  # Owner OS edition: governed by the workspace's own product access.
    subscription = await session.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == tenant_id)
    )
    plan = (
        await session.scalar(select(PiPlan).where(PiPlan.key == subscription.plan_key))
        if subscription
        else None
    )
    return plan is not None and "campaigns" in (plan.features or [])


async def production_connection(
    session: AsyncSession, scope: WorkspaceScope
) -> WhatsAppConnection | None:
    connection: WhatsAppConnection | None = await session.scalar(
        select(WhatsAppConnection).where(
            WhatsAppConnection.tenant_id == scope.tenant_id,
            WhatsAppConnection.environment_id == scope.environment_id,
            WhatsAppConnection.status == "active",
        )
    )
    return connection


async def schedule(
    session: AsyncSession,
    scope: WorkspaceScope,
    campaign_id: UUID,
    when: datetime | None,
    check_template: Any,
) -> PiCampaign:
    """``check_template`` is an async callable (connection, template) that raises a
    BusinessRuleViolation unless the template is approved."""
    scope.require("pi.campaigns.manage")
    row = await WorkspaceRepository(session, PiCampaign, scope).get(campaign_id, for_update=True)
    if row.status != "draft":
        raise Conflict("This campaign was already scheduled")
    if not await plan_allows_campaigns(session, scope.tenant_id):
        raise BusinessRuleViolation(
            "PLAN_FEATURE_REQUIRED", "Campaigns are included in the Growth and Business plans", 402
        )
    connection = await production_connection(session, scope)
    if connection is None or not connection.business_account_id:
        raise BusinessRuleViolation(
            "WHATSAPP_NOT_CONNECTED", "Connect your WhatsApp number before sending campaigns"
        )
    if await audience_size(session, scope, row.audience_tag) == 0:
        raise BusinessRuleViolation(
            "EMPTY_AUDIENCE", "No customers have agreed to receive messages yet"
        )
    await check_template(connection, {"name": row.template_name, "language": row.template_language})
    now = datetime.now(UTC)
    if when is not None and when < now - timedelta(minutes=5):
        raise BusinessRuleViolation("SCHEDULE_IN_PAST", "Choose a time in the future")
    row.status, row.scheduled_at = "scheduled", when or now
    await record(
        session,
        "pi.campaign_scheduled",
        scope=scope,
        entity_type="pi_campaign",
        entity_id=row.id,
        details={"at": row.scheduled_at.isoformat(), "tag": row.audience_tag},
    )
    return row


async def cancel(session: AsyncSession, scope: WorkspaceScope, campaign_id: UUID) -> PiCampaign:
    scope.require("pi.campaigns.manage")
    row = await WorkspaceRepository(session, PiCampaign, scope).get(campaign_id, for_update=True)
    if row.status in {"completed", "cancelled"}:
        return row
    row.status, row.finished_at = "cancelled", datetime.now(UTC)
    rows = await session.scalars(
        WorkspaceRepository(session, PiCampaignRecipient, scope)
        .select()
        .where(PiCampaignRecipient.campaign_id == row.id, PiCampaignRecipient.status == "pending")
    )
    for recipient in rows:
        recipient.status, recipient.error_code = "skipped", "CAMPAIGN_CANCELLED"
    await record(
        session, "pi.campaign_cancelled", scope=scope, entity_type="pi_campaign", entity_id=row.id
    )
    return row


async def results(session: AsyncSession, scope: WorkspaceScope, row: PiCampaign) -> dict[str, Any]:
    """Live counts from recipients and the real message statuses."""
    recipients = list(
        await session.execute(
            WorkspaceRepository(session, PiCampaignRecipient, scope)
            .select()
            .with_only_columns(
                PiCampaignRecipient.status,
                PiCampaignRecipient.error_code,
                PiMessage.status,
                PiMessage.error_code,
                PiMessage.created_at,
                PiConversation.last_inbound_at,
            )
            .outerjoin(PiMessage, PiMessage.id == PiCampaignRecipient.message_id)
            .outerjoin(PiConversation, PiConversation.id == PiCampaignRecipient.conversation_id)
            .where(PiCampaignRecipient.campaign_id == row.id)
        )
    )
    out: dict[str, int] = dict.fromkeys(
        ("waiting", "sent", "delivered", "read", "failed", "skipped", "replied"), 0
    )
    reasons: dict[str, int] = {}
    for status, error, message_status, message_error, sent_at, last_inbound in recipients:
        error = error or message_error
        state = message_status or status
        if state in {"pending", "queued", "processing"}:
            out["waiting"] += 1
        elif state in {"sent", "delivered", "read"}:
            out["sent"] += 1
            out["delivered"] += state in {"delivered", "read"}
            out["read"] += state == "read"
            out["replied"] += bool(last_inbound and sent_at and last_inbound > sent_at)
        elif state == "failed":
            out["failed"] += 1
        else:
            out["skipped"] += 1
            reasons[error or "SKIPPED"] = reasons.get(error or "SKIPPED", 0) + 1
    return {"recipients": len(recipients), **out, "skipped_reasons": reasons}


# ------------------------------------------------------------------------ sending


def quiet_now(row: PiCampaign, timezone: str, now: datetime | None = None) -> bool:
    local = (now or datetime.now(UTC)).astimezone(zone(timezone))
    start, end = row.quiet_start, row.quiet_end
    if start == end:
        return False
    hour = local.hour
    return start <= hour or hour < end if start > end else start <= hour < end


def _local_midnight(timezone: str, now: datetime) -> datetime:
    local = now.astimezone(zone(timezone))
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


async def send_block(
    session: AsyncSession, scope: WorkspaceScope, message: PiMessage, conversation: PiConversation
) -> str | None:
    """Re-check at delivery time. None means the campaign message may be sent."""
    info = message.media.get("campaign") or {}
    campaign = await WorkspaceRepository(session, PiCampaign, scope).find(
        PiCampaign.id == UUID(str(info.get("id")))
    )
    # "completed" means every recipient is queued; only a cancellation stops a send.
    if campaign is None or campaign.status not in {"sending", "completed"}:
        return "CAMPAIGN_CANCELLED"
    if conversation.customer_id is None or not await consent_granted(
        session, scope, conversation.customer_id, "marketing"
    ):
        return "OPTED_OUT"
    recent = conversation.last_message_at and conversation.last_message_at > datetime.now(
        UTC
    ) - timedelta(hours=24)
    if conversation.mode != "ai" and recent:
        return "HUMAN_TAKEOVER"  # Don't interrupt a chat a person is handling right now.
    return None


async def _start(session: AsyncSession, scope: WorkspaceScope, row: PiCampaign) -> None:
    row.status, row.started_at = "sending", datetime.now(UTC)
    contacts = list(
        await session.scalars(
            _latest_contacts(scope, session, row.audience_tag).limit(row.max_recipients)
        )
    )
    for conversation in contacts:
        await session.execute(
            insert(PiCampaignRecipient)
            .values(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                campaign_id=row.id,
                customer_id=conversation.customer_id,
                conversation_id=conversation.id,
                status="pending",
            )
            .on_conflict_do_nothing(constraint="uq_pi_campaign_recipient")
        )


async def _conversation_for(
    session: AsyncSession,
    scope: WorkspaceScope,
    connection: WhatsAppConnection,
    recipient: PiCampaignRecipient,
) -> PiConversation | None:
    repo = WorkspaceRepository(session, PiConversation, scope)
    known = await repo.find(PiConversation.id == recipient.conversation_id)
    if known is None:
        return None
    if known.status == "open" and known.connection_id == connection.id:
        return known
    current = await repo.find(
        PiConversation.connection_id == connection.id,
        PiConversation.contact_wa_id == known.contact_wa_id,
        PiConversation.status == "open",
    )
    if current is not None:
        return current
    return await repo.add(
        repo.new(
            customer_id=recipient.customer_id,
            connection_id=connection.id,
            contact_wa_id=known.contact_wa_id,
            language=known.language,
            last_message_at=datetime.now(UTC),
        )
    )


async def dispatch(
    session: AsyncSession, scope: WorkspaceScope, row: PiCampaign, timezone: str
) -> list[str]:
    """Queue the next batch of messages; returns message ids to enqueue."""
    now = datetime.now(UTC)
    if quiet_now(row, timezone, now):
        return []
    connection = await production_connection(session, scope)
    if connection is None:
        return []
    sent_today = int(
        await session.scalar(
            select(func.count())
            .select_from(PiCampaignRecipient)
            .join(PiMessage, PiMessage.id == PiCampaignRecipient.message_id)
            .where(
                PiCampaignRecipient.tenant_id == scope.tenant_id,
                PiCampaignRecipient.environment_id == scope.environment_id,
                PiCampaignRecipient.campaign_id == row.id,
                PiMessage.created_at >= _local_midnight(timezone, now),
            )
        )
        or 0
    )
    room = min(BATCH, row.daily_limit - sent_today)
    from app.modules.pi_saas.entitlement import remaining as allowance_left

    left = await allowance_left(session, scope.tenant_id, scope.environment_id, "messages_out")
    if left is not None:
        # The plan's monthly message allowance also covers campaigns; the rest waits for
        # next month (or an upgrade) instead of being sent over the limit.
        room = min(room, int(left))
    if room <= 0:
        return []
    pending = list(
        await session.scalars(
            WorkspaceRepository(session, PiCampaignRecipient, scope)
            .select()
            .where(
                PiCampaignRecipient.campaign_id == row.id,
                PiCampaignRecipient.status == "pending",
            )
            .order_by(PiCampaignRecipient.created_at)
            .limit(room)
            .with_for_update(skip_locked=True)
        )
    )
    messages = WorkspaceRepository(session, PiMessage, scope)
    queued: list[str] = []
    for recipient in pending:
        if not await consent_granted(session, scope, recipient.customer_id, "marketing"):
            recipient.status, recipient.error_code = "skipped", "OPTED_OUT"
            continue
        conversation = await _conversation_for(session, scope, connection, recipient)
        if conversation is None:
            recipient.status, recipient.error_code = "skipped", "NO_WHATSAPP_CONTACT"
            continue
        key = f"pi-campaign:{row.id}:{recipient.customer_id}"
        message = await messages.find(PiMessage.idempotency_key == key)
        if message is None:
            message = await messages.add(
                messages.new(
                    conversation_id=conversation.id,
                    direction="outbound",
                    sender_type="system",
                    body=f"Campaign template queued: {row.template_name}",
                    status="queued",
                    idempotency_key=key,
                    media={
                        "campaign": {
                            "id": str(row.id),
                            "template": {
                                "name": row.template_name,
                                "language": row.template_language,
                            },
                        }
                    },
                )
            )
            queued.append(str(message.id))
        recipient.status, recipient.conversation_id = "queued", conversation.id
        recipient.message_id = message.id
    remaining = await session.scalar(
        WorkspaceRepository(session, PiCampaignRecipient, scope)
        .select()
        .with_only_columns(func.count())
        .where(PiCampaignRecipient.campaign_id == row.id, PiCampaignRecipient.status == "pending")
    )
    if not remaining:
        row.status, row.finished_at = "completed", now  # Results stay live (see results()).
    return queued


async def sweep_campaigns(ctx: dict[str, Any]) -> None:
    from app.modules.pi.configuration import settings_row
    from app.modules.pi.runtime import enqueue_sends, system_scope

    outgoing: list[str] = []
    async with ctx["sessions"]() as session:
        rows = list(
            await session.scalars(
                select(PiCampaign)
                .where(
                    (PiCampaign.status == "sending")
                    | (
                        (PiCampaign.status == "scheduled")
                        & (PiCampaign.scheduled_at <= datetime.now(UTC))
                    )
                )
                .order_by(PiCampaign.scheduled_at)
                .limit(20)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            connection = await session.scalar(
                select(WhatsAppConnection).where(
                    WhatsAppConnection.tenant_id == row.tenant_id,
                    WhatsAppConnection.environment_id == row.environment_id,
                    WhatsAppConnection.status == "active",
                )
            )
            scope = await system_scope(session, connection) if connection else None
            if scope is None:
                continue  # Waits (visibly "scheduled"/"sending") until WhatsApp reconnects.
            if not await plan_allows_campaigns(session, row.tenant_id):
                continue
            if row.status == "scheduled":
                await _start(session, scope, row)
            policy = await settings_row(session, scope)
            outgoing += await dispatch(session, scope, row, policy.timezone)
        await session.commit()
    await enqueue_sends(ctx, outgoing)
