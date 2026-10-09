"""Background jobs for the Pi SaaS: provider and billing events, lifecycle sweeps.

Processing is idempotent (events are claimed with a row lock and applied once), bounded
(five attempts, then ``failed`` for operator replay) and never holds a transaction across
provider HTTP calls longer than one event.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select

from app.modules.pi_saas import billing, connections
from app.modules.pi_saas.models import PiBillingEvent, PiProviderEvent
from app.modules.pi_saas.operator import expire_grants

logger = logging.getLogger("platform")
MAX_ATTEMPTS = 5


async def process_pi_provider_event(ctx: dict[str, Any], event_id: str) -> None:
    enqueue: list[str] = []
    async with ctx["sessions"]() as session:
        row = await session.scalar(
            select(PiProviderEvent)
            .where(PiProviderEvent.id == UUID(event_id))
            .with_for_update(skip_locked=True)
        )
        if row is None or row.status not in {"received"}:
            return
        row.attempts += 1
        try:
            async with session.begin_nested():
                enqueue = await connections.process_event(
                    session, ctx["settings"], ctx["http"], row
                )
        except Exception as exc:  # noqa: BLE001 - recorded, retried, then surfaced
            code = getattr(exc, "code", type(exc).__name__)
            row.error_code = str(code)[:64]
            row.status = "failed" if row.attempts >= MAX_ATTEMPTS else "received"
            logger.warning("pi_provider_event_failed")
        await session.commit()
    for pi_event in enqueue:
        await _enqueue(ctx, "process_pi_event", pi_event, f"pi:{pi_event}")


async def process_pi_billing_event(ctx: dict[str, Any], event_id: str) -> None:
    async with ctx["sessions"]() as session:
        row = await session.scalar(
            select(PiBillingEvent)
            .where(PiBillingEvent.id == UUID(event_id))
            .with_for_update(skip_locked=True)
        )
        if row is None or row.status != "received":
            return
        row.attempts += 1
        try:
            async with session.begin_nested():
                await billing.apply_event(session, ctx["settings"], row, ctx["http"])
        except Exception as exc:  # noqa: BLE001
            row.error_code = str(getattr(exc, "code", type(exc).__name__))[:64]
            row.status = "failed" if row.attempts >= MAX_ATTEMPTS else "received"
            logger.warning("pi_billing_event_failed")
        await session.commit()


async def sweep_pi_saas(ctx: dict[str, Any]) -> None:
    """Retry stalled events, expire support grants and record lapsed grace periods."""
    stale = datetime.now(UTC) - timedelta(minutes=2)
    async with ctx["sessions"]() as session:
        providers = list(
            await session.scalars(
                select(PiProviderEvent.id)
                .where(PiProviderEvent.status == "received", PiProviderEvent.updated_at < stale)
                .limit(100)
            )
        )
        bills = list(
            await session.scalars(
                select(PiBillingEvent.id)
                .where(PiBillingEvent.status == "received", PiBillingEvent.updated_at < stale)
                .limit(100)
            )
        )
        await expire_grants(session)
        from app.modules.pi_saas.customer_payments import expire_requests

        await expire_requests(session)
        await billing.sweep_lifecycle(session)
        await session.commit()
    # Proposals pi owes a customer whose job never ran or failed.
    async with ctx["sessions"]() as session:
        try:
            proposals = await _proposals_due(session)
        except Exception:  # noqa: BLE001 - retried on the next sweep
            proposals = []
            logger.warning("pi_proposal_sweep_failed")
    for lead_id in proposals:
        await enqueue_proposal(ctx, UUID(lead_id))
    # Quiet deals: pi reminds the customer (proposal unopened/unanswered, invoice due).
    from app.modules.pi_saas import deal_followups

    nudges: list[str] = []
    async with ctx["sessions"]() as session:
        try:
            nudges = await deal_followups.sweep(session, ctx["settings"])
            await session.commit()
        except Exception:  # noqa: BLE001 - retried on the next sweep
            nudges = []
            logger.warning("pi_deal_followups_failed", exc_info=True)
    for message_id in nudges:
        await _enqueue(ctx, "send_pi_message", message_id, f"send:{message_id}")
    # Staged dunning reminders (own session/commit: a mail-transport failure here must
    # never roll back the lifecycle sweep above or block the rest of the sweep).
    async with ctx["sessions"]() as session:
        try:
            sent = await billing.send_dunning_reminders(session, ctx["settings"], ctx["http"])
            await session.commit()
            if sent:
                logger.info("pi_dunning_reminders_sent", extra={"count": sent})
        except Exception:  # noqa: BLE001 - retried on the next sweep
            await session.rollback()
            logger.warning("pi_dunning_sweep_failed")
    # Business journey: notifications, held numbers connecting once allowed, expiring holds.
    async with ctx["sessions"]() as session:
        from app.modules.pi_saas import lifecycle_notify

        try:
            await lifecycle_notify.sweep(session, ctx["settings"], ctx["http"])
            await session.commit()
        except Exception:  # noqa: BLE001 - retried on the next sweep
            await session.rollback()
            logger.warning("pi_lifecycle_sweep_failed")
    # A number can look connected while its webhook never registered with Kapso (missing
    # public URL/secret at setup time, or a transient provider failure); retry until it
    # takes, so messages start arriving without anyone clicking "Check health".
    async with ctx["sessions"]() as session:
        try:
            healed = await connections.retry_unregistered_webhooks(
                session, ctx["settings"], ctx["http"]
            )
            await session.commit()
            if healed:
                logger.info("pi_webhook_self_healed", extra={"count": healed})
        except Exception:  # noqa: BLE001 - retried on the next sweep
            await session.rollback()
            logger.warning("pi_webhook_retry_failed")
    for event_id in providers:
        await _enqueue(ctx, "process_pi_provider_event", str(event_id), f"pi-provider:{event_id}")
    for event_id in bills:
        await _enqueue(ctx, "process_pi_billing_event", str(event_id), f"pi-billing:{event_id}")


async def enqueue_proposal(ctx: dict[str, Any], lead_id: UUID) -> None:
    # A job id per minute: arq keeps finished ids for an hour, and a revised proposal
    # (changes asked, brief confirmed again) must still run. The lead lock and
    # ``proposal_due`` keep two runs from making two proposals.
    minute = int(datetime.now(UTC).timestamp() // 60)
    await _enqueue(ctx, "draft_pi_proposal", str(lead_id), f"pi-proposal:{lead_id}:{minute}")


async def draft_pi_proposal(ctx: dict[str, Any], lead_id: str) -> None:
    """The customer confirmed the brief: pi writes the proposal (model call with no
    transaction held), creates it under a lead lock and sends it on WhatsApp."""
    from app.ai.manager import build_llm_manager
    from app.modules.pi.runtime import enqueue_sends
    from app.modules.pi_saas import deals
    from app.modules.sales.models import SalesLead

    ids: list[str] = []
    async with ctx["sessions"]() as session:
        lead = await session.get(SalesLead, UUID(lead_id))
        if lead is None:
            return
        scope = await deals.system_scope_for(session, lead.tenant_id, lead.environment_id)
        if await _proposal_state(session, lead) != "due":
            return  # Already handled, or the chat never asked for one.
        try:
            if not await deals.proposal_due(session, scope, lead.id):
                await _mark_proposal(session, lead, "skipped")
                await session.commit()
                return
            written = await deals.write_proposal(
                session,
                scope,
                build_llm_manager(ctx["settings"], ctx["http"], ctx["sessions"]),
                lead.id,
            )
            # One writer per lead: a second run waits here, then finds the proposal made.
            await session.execute(
                select(SalesLead.id).where(SalesLead.id == lead.id).with_for_update()
            )
            ids = await deals.auto_proposal(session, scope, ctx["settings"], lead.id, written)
            await _mark_proposal(session, lead, "made")
            await session.commit()
        except Exception:  # noqa: BLE001 - left "due": the sweep retries a few times
            await session.rollback()
            logger.warning("pi_proposal_job_failed", exc_info=True)
            async with ctx["sessions"]() as retry:
                found = await retry.get(SalesLead, UUID(lead_id))
                if found is not None:
                    await _mark_proposal(retry, found, "due", failed=True)
                    await retry.commit()
            return
    await enqueue_sends(ctx, ids)


async def _proposal_state(session: Any, lead: Any) -> str | None:
    from app.modules.pi.models import PiConversation

    if lead.conversation_id is None:
        return None
    conversation = await session.get(PiConversation, lead.conversation_id)
    brief = (conversation.service_brief or {}) if conversation else {}
    state = (brief.get("proposals") or {}).get(str(lead.id))
    if state is None:
        legacy = brief.get("proposal")
        # Before per-lead states: the single state applies only to its own lead.
        if isinstance(legacy, dict) and legacy.get("lead_id") in (None, str(lead.id)):
            state = legacy
    return str(state.get("status")) if isinstance(state, dict) else None


async def _mark_proposal(session: Any, lead: Any, status: str, *, failed: bool = False) -> None:
    from app.modules.pi.models import PiConversation

    if lead.conversation_id is None:
        return
    conversation = await session.get(PiConversation, lead.conversation_id)
    if conversation is None:
        return
    brief = dict(conversation.service_brief or {})
    states = dict(brief.get("proposals") or {})
    legacy = dict(brief.get("proposal") or {})
    state = dict(
        states.get(str(lead.id))
        or (legacy if legacy.get("lead_id") in (None, str(lead.id)) else {})
    )
    attempts = int(state.get("attempts", 0)) + (1 if failed else 0)
    state.update(
        status="failed" if attempts >= 3 else status, attempts=attempts, lead_id=str(lead.id)
    )
    states[str(lead.id)] = state
    brief["proposals"] = states
    if legacy.get("lead_id") in (None, str(lead.id)):
        brief["proposal"] = state
    if status == "made":
        brief.pop("proposal_changes", None)  # The revision is out; the changes are in it.
    conversation.service_brief = brief


async def _proposals_due(session: Any) -> list[str]:
    """Leads whose proposal job was lost (worker restart) or failed: retried."""
    from app.modules.pi.models import PiConversation

    stale = datetime.now(UTC) - timedelta(minutes=2)
    briefs = await session.scalars(
        select(PiConversation.service_brief)
        .where(
            or_(
                PiConversation.service_brief["proposal"]["status"].astext == "due",
                PiConversation.service_brief.has_key("proposals"),
            ),
            PiConversation.updated_at < stale,
        )
        .limit(50)
    )
    due: list[str] = []
    for brief in briefs:
        states = dict(brief.get("proposals") or {})
        legacy = brief.get("proposal") or {}
        if legacy.get("lead_id") and str(legacy["lead_id"]) not in states:
            states[str(legacy["lead_id"])] = legacy
        due += [lead for lead, state in states.items() if state.get("status") == "due"]
    return list(dict.fromkeys(due))[:20]


async def pi_reply_with_team_answer(ctx: dict[str, Any], request_id: str) -> None:
    """The team answered pi's request: pi replies to the customer using it."""
    from app.modules.pi_saas.requests import reply_with_answer

    await reply_with_answer(ctx, request_id)


async def _enqueue(ctx: dict[str, Any], name: str, arg: str, job_id: str) -> None:
    if ctx.get("redis"):
        await ctx["redis"].enqueue_job(name, arg, _job_id=job_id)
    elif ctx.get("queue"):
        await ctx["queue"].enqueue(name, arg, job_id=job_id)


JOBS: dict[str, Callable[..., Awaitable[Any]]] = {
    "pi_reply_with_team_answer": pi_reply_with_team_answer,
    "process_pi_provider_event": process_pi_provider_event,
    "process_pi_billing_event": process_pi_billing_event,
    "sweep_pi_saas": sweep_pi_saas,
    "draft_pi_proposal": draft_pi_proposal,
}
