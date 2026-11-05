"""Where an approved insight goes: the existing brain writers, nothing new.

A reviewer approves an insight, and only then does it reach the shared brain, through the paths the
chat already uses:

* a stated `problem`            -> the Problem Map (`problems.apply_ops`), with the customer's own
                                   words from the cited lines as evidence, and only when the cited
                                   speaker is confirmed as the customer;
* a stated `decision` or
  `commitment`                  -> the memory ledger (`memory_ledger.record_decision`), subject_ref
                                   `meeting:<meeting>:<insight>` (the kind column is fixed in
                                   production, so meeting facts are namespaced instead);
* an `action`, `next_step`,
  `question`, `commitment`      -> a staff request (`requests.raise_request`) on the customer's
                                   latest conversation;
* an inferred or recommended action, next step or question -> a staff request too, but headed
  "AI suggestion (unconfirmed)" so nobody reads it as something the customer said;
* anything else the model inferred, estimated or recommended -> approved as reviewed information
  only. It is never written to the brain as something the customer said.

A reviewer's own wording may not carry a price (pi does not price), and an edit that redaction
empties is refused, not dropped quietly. A memory row from a meeting says it came from a meeting,
and says so when the cited speaker is not confirmed as the customer.

Approval is idempotent: an insight that was already written is returned as it is, so a double click
or a replay never writes twice. A meeting not linked to a customer cannot write to the brain.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import memory_ledger, problems
from app.modules.pi.models import PiConversation
from app.modules.pi_meetings.insight_rules import PRICE
from app.modules.pi_meetings.models import (
    PiMeeting,
    PiMeetingInsight,
    PiMeetingParticipant,
    PiMeetingSegment,
)
from app.modules.pi_saas import requests
from app.shared.scope import WorkspaceScope

PROBLEM_KINDS = frozenset({"problem"})
DECISION_KINDS = frozenset({"decision", "commitment"})
REQUEST_KINDS = {
    "action": "other",
    "next_step": "other",
    "question": "question",
    "commitment": "other",
}
TITLE_WORDS = 8


class NotLinked(Exception):
    """The meeting has no customer yet: link it before approving what it says."""


class PriceInEdit(Exception):
    """The reviewer's wording carries a price: pi does not price, the quote does."""


class EditRefused(Exception):
    """The reviewer's wording was emptied by redaction, so it cannot be stored."""


class NotPending(Exception):
    """The insight was already reviewed the other way (it was rejected)."""


@dataclass
class Outcome:
    insight: PiMeetingInsight
    wrote: str = ""  # problem | decision | request | "" (reviewed information only)
    note: str = ""  # why nothing was written, when that is not obvious


def _ref(meeting_id: UUID, insight_id: UUID) -> str:
    # 60 characters is the ledger limit: "meeting:" + 12 + ":" + 12
    return f"meeting:{meeting_id.hex[:12]}:{insight_id.hex[:12]}"


def _title(text: str) -> str:
    return " ".join(text.split()[:TITLE_WORDS])


async def _quotes(
    session: AsyncSession, scope: WorkspaceScope, meeting_id: UUID, refs: list[int]
) -> list[str]:
    if not refs:
        return []
    rows = await session.scalars(
        select(PiMeetingSegment.text)
        .where(
            PiMeetingSegment.tenant_id == scope.tenant_id,
            PiMeetingSegment.environment_id == scope.environment_id,
            PiMeetingSegment.meeting_id == meeting_id,
            PiMeetingSegment.ordinal.in_(refs),
        )
        .order_by(PiMeetingSegment.ordinal)
    )
    return [t for t in rows if t][:4]


async def _customer_said(
    session: AsyncSession, scope: WorkspaceScope, meeting_id: UUID, refs: list[int]
) -> bool:
    """True only when every cited line was spoken by a participant confirmed as the customer."""
    if not refs:
        return False
    roles = list(
        await session.scalars(
            select(PiMeetingParticipant.role)
            .join(
                PiMeetingSegment,
                (PiMeetingSegment.participant_id == PiMeetingParticipant.id)
                & (PiMeetingSegment.tenant_id == PiMeetingParticipant.tenant_id)
                & (PiMeetingSegment.environment_id == PiMeetingParticipant.environment_id),
            )
            .where(
                PiMeetingSegment.tenant_id == scope.tenant_id,
                PiMeetingSegment.environment_id == scope.environment_id,
                PiMeetingSegment.meeting_id == meeting_id,
                PiMeetingSegment.ordinal.in_(refs),
            )
        )
    )
    return bool(roles) and all(r == "customer" for r in roles)


async def _conversation(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> UUID | None:
    found: UUID | None = await session.scalar(
        select(PiConversation.id)
        .where(
            PiConversation.tenant_id == scope.tenant_id,
            PiConversation.environment_id == scope.environment_id,
            PiConversation.customer_id == customer_id,
        )
        .order_by(PiConversation.last_message_at.desc())
        .limit(1)
    )
    return found


async def approve(
    session: AsyncSession,
    scope: WorkspaceScope,
    meeting: PiMeeting,
    insight: PiMeetingInsight,
    *,
    reviewer_id: UUID | None,
    edited_text: str = "",
    now: datetime | None = None,
) -> Outcome:
    """Approve one insight (optionally in the reviewer's own words) and write it to the brain."""
    if insight.review_status == "rejected":
        raise NotPending
    if insight.written_at is not None:
        return Outcome(insight, wrote=insight.brain_ref.split(":", 1)[0])  # replay: already done
    if meeting.customer_id is None:
        raise NotLinked
    stamp = now or datetime.now(UTC)
    clean = memory_ledger.redacted(edited_text, 600) if edited_text else ""
    if edited_text.strip() and not clean:
        raise EditRefused
    if clean and PRICE.search(clean):
        raise PriceInEdit
    text = clean or insight.text
    out = Outcome(insight)
    stated = insight.basis == "stated"
    customer_id = meeting.customer_id

    if stated and insight.kind in PROBLEM_KINDS:
        refs = list(insight.segment_refs)
        quotes = await _quotes(session, scope, meeting.id, refs)
        if not await _customer_said(session, scope, meeting.id, refs):
            # the Problem Map records the customer's own words: another speaker's are not them
            out.note = "not written: the speaker is not confirmed as the customer"
        else:
            note = problems.ProblemNote(
                title=_title(text),
                summary=text,
                user_words=quotes,
                confidence=min(1.0, max(0.0, insight.confidence / 100)),
            )
            applied = await problems.apply_ops(
                session,
                scope,
                customer_id,
                None,
                None,
                [problems.ProblemOp(op="create", note=note)],
                meeting.language or "en",
                owner_text=" ".join(quotes),
            )
            touched = [*applied.created, *applied.updated]
            if touched:
                insight.brain_ref = f"problem:{touched[0].id}"[:60]
                out.wrote = "problem"
            else:
                out.note = "the Problem Map did not take it: " + "; ".join(applied.rejected)[:200]
    elif stated and insight.kind in DECISION_KINDS:
        said = await _customer_said(session, scope, meeting.id, list(insight.segment_refs))
        source = "In a meeting" if said else "In a meeting (speaker not confirmed as the customer)"
        wording = " (reviewer's wording)" if clean and clean != insight.text else ""
        row = await memory_ledger.record_decision(
            session,
            scope,
            customer_id=customer_id,
            kind="other",
            subject_ref=_ref(meeting.id, insight.id),
            actor="staff",
            owner_words=f"{source}{wording}: {text}",
            now=stamp,
        )
        if row is not None:
            insight.brain_ref = f"decision:{row.id}"[:60]
            out.wrote = "decision"
        else:
            out.note = "the memory ledger did not record it"
    if not out.wrote and insight.kind in REQUEST_KINDS and (stated or insight.basis != "estimate"):
        conversation_id = await _conversation(session, scope, customer_id)
        if conversation_id is None:
            out.note = out.note or "the customer has no conversation to attach a request to"
        else:
            due = f" (due: {insight.due_text})" if insight.due_text else ""
            who = f" Owner: {insight.owner_label}." if insight.owner_label else ""
            head = "From the meeting" if stated else "AI suggestion (unconfirmed)"
            req = await requests.raise_request(
                session,
                scope,
                conversation_id=conversation_id,
                customer_id=customer_id,
                kind=REQUEST_KINDS[insight.kind],
                question=f"{head}: {text}{due}.{who}"[:900],
                title="Meeting follow-up",
            )
            insight.brain_ref = f"request:{req.id}"[:60]
            out.wrote = "request"

    insight.edited_text = clean
    insight.review_status = "edited" if clean and clean != insight.text else "approved"
    insight.reviewed_by = reviewer_id
    insight.reviewed_at = stamp
    if out.wrote:
        insight.written_at = stamp
    await session.flush()
    return out


async def reject(
    session: AsyncSession,
    insight: PiMeetingInsight,
    *,
    reviewer_id: UUID | None,
    now: datetime | None = None,
) -> PiMeetingInsight:
    """Reject an insight. One that was already written to the brain cannot be un-written here: the
    brain's own supersede and withdraw paths do that, with their history."""
    if insight.written_at is not None:
        raise NotPending
    insight.review_status = "rejected"
    insight.reviewed_by = reviewer_id
    insight.reviewed_at = now or datetime.now(UTC)
    await session.flush()
    return insight
