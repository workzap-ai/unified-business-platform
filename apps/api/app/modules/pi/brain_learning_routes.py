"""Staff controls for pi's learning (pi Brain spec 8.10, 8.11.1): see what it learned, retire
what is wrong, teach it with a real message or a better question wording, run it now.

Everything a person adds goes through the same never-learn and redaction gates as anything pi
finds itself. Nothing here can touch the rules: an example is reference material and a question
wording is one of several ways to ask what the question policy already says to ask.
"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi import (
    learning,
    learning_arms,
    learning_bank,
    learning_lessons,
    learning_miner,
    learning_nightly,
    learning_packs,
)
from app.modules.pi.configuration import settings_row
from app.modules.pi.learning_embed import make_embedder
from app.modules.pi.learning_models import (
    PiLearnedPack,
    PiLearningChange,
    PiLearningExample,
    PiLearningLesson,
    PiLearningRun,
    PiQuestionArm,
)
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi.service import require_pi
from app.shared.errors import BusinessRuleViolation, ResourceNotFound

router = APIRouter(prefix="/pi/brain-learning", tags=["pi-brain-learning"])
PERMISSION = "pi.settings.manage"


def _example(e: PiLearningExample) -> dict[str, Any]:
    return {
        "id": e.id,
        "status": e.status,
        "language": e.language,
        "situation": e.situation,
        "person": e.person_text,
        "reply": e.reply_text,
        "reward": e.reward,
        "uses": e.uses,
        "redaction_confidence": float(e.redaction_confidence),
        "retired_reason": e.retired_reason,
        "created_at": e.created_at,
    }


def _arm(a: PiQuestionArm) -> dict[str, Any]:
    return {
        "id": a.id,
        "slot": a.slot,
        "language": a.language,
        "text": a.text,
        "status": a.status,
        "uses": a.uses,
        "success_rate": round(a.alpha / (a.alpha + a.beta), 3),
        "traffic_cap": a.traffic_cap,
        "created_by": a.created_by,
    }


@router.get("/runs")
async def runs(scope: Scope, session: Session, limit: int = 14) -> dict[str, Any]:
    """The nightly digests, newest first."""
    await require_pi(session, scope, PERMISSION)
    rows = await session.scalars(
        select(PiLearningRun)
        .where(
            PiLearningRun.tenant_id == scope.tenant_id,
            PiLearningRun.environment_id == scope.environment_id,
        )
        .order_by(PiLearningRun.started_at.desc())
        .limit(max(1, min(60, limit)))
    )
    return {
        "items": [
            {"id": r.id, "started_at": r.started_at, "frozen": r.frozen, "digest": r.digest}
            for r in rows
        ]
    }


@router.post("/run")
async def run_now(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    """Run the learning now for this workspace. Does nothing while learning is frozen."""
    await require_pi(session, scope, PERMISSION)
    policy = await settings_row(session, scope)
    state = request.app.state
    run = await learning_nightly.run_workspace(
        session,
        policy,
        embedder=make_embedder(state.settings, state.http),
        pack_writer=lambda s: learning_packs.make_writer(state.settings, state.http, s),
        question_writer=lambda s: learning_miner.make_writer(state.settings, state.http, s),
    )
    await record(
        session,
        "pi.brain_learning_run",
        scope=scope,
        entity_type="pi_learning_run",
        entity_id=run.id,
        details={"frozen": run.frozen},
    )
    await session.commit()
    return {"id": run.id, "frozen": run.frozen, "digest": run.digest}


@router.get("/changes")
async def changes(scope: Scope, session: Session, limit: int = 50) -> dict[str, Any]:
    """The change log: everything learning changed, with the reason."""
    await require_pi(session, scope, PERMISSION)
    rows = await session.scalars(
        select(PiLearningChange)
        .where(
            PiLearningChange.tenant_id == scope.tenant_id,
            PiLearningChange.environment_id == scope.environment_id,
        )
        .order_by(PiLearningChange.created_at.desc())
        .limit(max(1, min(200, limit)))
    )
    return {
        "items": [
            {
                "id": c.id,
                "kind": c.kind,
                "risk": c.risk,
                "status": c.status,
                "before": c.before,
                "after": c.after,
                "reason": c.reason,
                "created_at": c.created_at,
            }
            for c in rows
        ]
    }


@router.get("/examples")
async def examples(
    scope: Scope, session: Session, status: str | None = None, limit: int = 100
) -> dict[str, Any]:
    await require_pi(session, scope, PERMISSION)
    query = (
        select(PiLearningExample)
        .where(
            PiLearningExample.tenant_id == scope.tenant_id,
            PiLearningExample.environment_id == scope.environment_id,
        )
        .order_by(PiLearningExample.created_at.desc())
        .limit(max(1, min(300, limit)))
    )
    if status:
        query = query.where(PiLearningExample.status == status)
    return {"items": [_example(e) for e in await session.scalars(query)]}


class RetireInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="retired by staff", max_length=200)


@router.post("/examples/{example_id}/retire")
async def retire_example(
    example_id: UUID, data: RetireInput, scope: Scope, session: Session
) -> dict[str, Any]:
    """One click: stop using this example."""
    await require_pi(session, scope, PERMISSION)
    row = await session.get(PiLearningExample, example_id)
    if (
        row is None
        or row.tenant_id != scope.tenant_id
        or row.environment_id != scope.environment_id
    ):
        raise ResourceNotFound
    before = row.status
    row.status, row.retired_reason = "retired", data.reason
    session.add(
        PiLearningChange(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            kind="example_retired",
            target_id=row.id,
            before={"status": before},
            after={"status": "retired"},
            reason=data.reason,
            status="live",
            decided_by=scope.user_id,
        )
    )
    await session.commit()
    return _example(row)


@router.post("/examples/from-message/{message_id}", status_code=201)
async def great_reply(message_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    """ "This was great": turn one of pi's real replies into an example. It still has to pass the
    redaction gate and the never-learn list, so a reply with a name, a number or a rule break is
    refused with the reasons. It starts as a candidate and goes live with the next run."""
    await require_pi(session, scope, PERMISSION)
    reply = await session.get(PiMessage, message_id)
    if (
        reply is None
        or reply.tenant_id != scope.tenant_id
        or reply.environment_id != scope.environment_id
        or reply.sender_type != "ai"
    ):
        raise ResourceNotFound
    already = await session.scalar(
        select(PiLearningExample.id).where(
            PiLearningExample.tenant_id == scope.tenant_id,
            PiLearningExample.environment_id == scope.environment_id,
            PiLearningExample.message_id == reply.id,
        )
    )
    if already is not None:
        raise BusinessRuleViolation("ALREADY_AN_EXAMPLE", "This reply is already an example", 409)
    conversation = await session.get(PiConversation, reply.conversation_id)
    asked = await learning_bank._answered(session, reply)
    person = asked.body if asked is not None else ""
    said = learning_bank.strip_opening(reply.body)
    confidence = min(
        learning_bank.redaction_confidence(said), learning_bank.redaction_confidence(person)
    )
    why = learning.never_learn(said)
    if not person.strip():
        why.append("there is no customer message this was an answer to")
    if confidence < 0.98:
        why.append("it may still hold personal details (a name, number, link or contact)")
    state = conversation.flow_state if conversation is not None else ""
    if state not in learning_bank.LISTENING_STATES:
        why.append("only replies from the listening loop (S1 to S3) can be examples")
    if why:
        raise BusinessRuleViolation("EXAMPLE_REFUSED", "; ".join(why), 422)
    example = PiLearningExample(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        message_id=reply.id,
        situation={
            "state": state or "",
            "language": conversation.language if conversation is not None else "en",
            "turn_kind": "question" if said.rstrip().endswith(("?", "؟")) else "statement",
        },
        language=(conversation.language if conversation is not None else None) or "en",
        person_text=person[:500],
        reply_text=said[:500],
        reward=3,
        status="candidate",
        source_contacts=[str(conversation.customer_id)]
        if conversation is not None and conversation.customer_id
        else [],
        redaction_confidence=Decimal(str(confidence)),
    )
    session.add(example)
    await session.flush()
    session.add(
        PiLearningChange(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            kind="example_added_by_staff",
            target_id=example.id,
            before={},
            after={"status": "candidate"},
            reason="marked as great by staff",
            status="live",
            decided_by=scope.user_id,
        )
    )
    await session.commit()
    return _example(example)


@router.get("/arms")
async def arms(scope: Scope, session: Session, slot: str | None = None) -> dict[str, Any]:
    """Every question wording with its success rate (the question leaderboard)."""
    await require_pi(session, scope, PERMISSION)
    await learning_arms.ensure_seeded(session, scope)
    query = select(PiQuestionArm).where(
        PiQuestionArm.tenant_id == scope.tenant_id,
        PiQuestionArm.environment_id == scope.environment_id,
    )
    if slot:
        query = query.where(PiQuestionArm.slot == slot)
    rows = list(await session.scalars(query.order_by(PiQuestionArm.slot, PiQuestionArm.language)))
    await session.commit()
    return {"items": [_arm(a) for a in rows]}


class ArmInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot: str = Field(max_length=24)
    language: str = Field(default="en", max_length=12)
    text: str = Field(max_length=300)


@router.post("/arms", status_code=201)
async def add_arm(data: ArmInput, scope: Scope, session: Session) -> dict[str, Any]:
    """A better way to ask a question. It must be one question, free of personal-data requests
    and pitching; it is tried on 10% of the traffic until it has proved itself."""
    await require_pi(session, scope, PERMISSION)
    arm, why = await learning_arms.propose(
        session, scope, data.slot, data.language, data.text, "staff"
    )
    if arm is None:
        raise BusinessRuleViolation("WORDING_REFUSED", "; ".join(why), 422)
    await session.commit()
    return _arm(arm)


@router.post("/arms/{arm_id}/retire")
async def retire_arm(arm_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, PERMISSION)
    row = await session.get(PiQuestionArm, arm_id)
    if (
        row is None
        or row.tenant_id != scope.tenant_id
        or row.environment_id != scope.environment_id
    ):
        raise ResourceNotFound
    row.status = "retired"
    session.add(
        PiLearningChange(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            kind="question_arm_retired",
            target_id=row.id,
            before={},
            after={"status": "retired"},
            reason="retired by staff",
            status="live",
            decided_by=scope.user_id,
        )
    )
    await session.commit()
    return _arm(row)


def _lesson(row: PiLearningLesson) -> dict[str, Any]:
    return {
        "id": row.id,
        "text": row.text,
        "scope": row.scope,
        "risk": row.risk,
        "status": row.status,
        "created_by": row.created_by,
        "author_id": row.author_id,
        "decided_by": row.decided_by,
        "reason": row.reason,
        "uses": row.uses,
        "created_at": row.created_at,
    }


async def _own_lesson(session: Session, scope: Scope, lesson_id: UUID) -> PiLearningLesson:
    row = await session.get(PiLearningLesson, lesson_id)
    if (
        row is None
        or row.tenant_id != scope.tenant_id
        or row.environment_id != scope.environment_id
    ):
        raise ResourceNotFound
    return row


@router.get("/lessons")
async def lessons(scope: Scope, session: Session, status: str | None = None) -> dict[str, Any]:
    """Teach pi: every lesson, with the ones waiting for a second person first."""
    await require_pi(session, scope, PERMISSION)
    query = select(PiLearningLesson).where(
        PiLearningLesson.tenant_id == scope.tenant_id,
        PiLearningLesson.environment_id == scope.environment_id,
    )
    if status:
        query = query.where(PiLearningLesson.status == status)
    rows = list(
        await session.scalars(query.order_by(PiLearningLesson.created_at.desc()).limit(200))
    )
    rows.sort(key=lambda r: r.status != "review")
    return {"items": [_lesson(r) for r in rows]}


class LessonInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=400)
    state: str | None = Field(default=None, max_length=32)
    language: str | None = Field(default=None, max_length=12)
    category: str | None = Field(default=None, max_length=40)


@router.post("/lessons", status_code=201)
async def teach(data: LessonInput, scope: Scope, session: Session) -> dict[str, Any]:
    """Teach pi something in plain words. Low-risk tips go live; anything touching money, privacy,
    the offer, follow-ups, approval or advice waits for a different person to approve it."""
    await require_pi(session, scope, PERMISSION)
    row = await learning_lessons.propose(
        session,
        scope,
        data.text,
        {
            "state": data.state or "",
            "language": data.language or "",
            "category": data.category or "",
        },
        scope.user_id,
    )
    await session.commit()
    return _lesson(row)


class NeverSayInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phrase: str = Field(max_length=120)
    state: str | None = Field(default=None, max_length=32)
    language: str | None = Field(default=None, max_length=12)


@router.post("/never-say", status_code=201)
async def never_say(data: NeverSayInput, scope: Scope, session: Session) -> dict[str, Any]:
    """ "Never say this": pi's replies in this situation may not contain the phrase."""
    await require_pi(session, scope, PERMISSION)
    row = await learning_lessons.add_never_say(
        session,
        scope,
        data.phrase,
        {"state": data.state or "", "language": data.language or ""},
        scope.user_id,
    )
    await session.commit()
    return _lesson(row)


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="", max_length=300)


@router.post("/lessons/{lesson_id}/approve")
async def approve_lesson(
    lesson_id: UUID, data: DecisionInput, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, PERMISSION)
    row = await _own_lesson(session, scope, lesson_id)
    await learning_lessons.decide(session, scope, row, True, scope.user_id, data.reason)
    await session.commit()
    return _lesson(row)


@router.post("/lessons/{lesson_id}/reject")
async def reject_lesson(
    lesson_id: UUID, data: DecisionInput, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, PERMISSION)
    row = await _own_lesson(session, scope, lesson_id)
    await learning_lessons.decide(session, scope, row, False, scope.user_id, data.reason)
    await session.commit()
    return _lesson(row)


@router.post("/lessons/{lesson_id}/retire")
async def retire_lesson(
    lesson_id: UUID, data: DecisionInput, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, PERMISSION)
    row = await _own_lesson(session, scope, lesson_id)
    await learning_lessons.retire(
        session, scope, row, scope.user_id, data.reason or "retired by staff"
    )
    await session.commit()
    return _lesson(row)


def _pack(row: PiLearnedPack) -> dict[str, Any]:
    return {
        "id": row.id,
        "key": row.key,
        "title": row.title,
        "status": row.status,
        "care_approved": row.care_approved,
        "content": row.content,
        "businesses": (row.evidence or {}).get("businesses", 0),
        "descriptions": (row.evidence or {}).get("descriptions", []),
        "shadow_conversations": len((row.evidence or {}).get("shadow_ids") or []),
        "created_at": row.created_at,
    }


async def _own_pack(session: Session, scope: Scope, pack_id: UUID) -> PiLearnedPack:
    row = await session.get(PiLearnedPack, pack_id)
    if (
        row is None
        or row.tenant_id != scope.tenant_id
        or row.environment_id != scope.environment_id
    ):
        raise ResourceNotFound
    return row


@router.get("/packs")
async def packs(scope: Scope, session: Session) -> dict[str, Any]:
    """Industry packs pi drafted for trades no built-in pack covers."""
    await require_pi(session, scope, PERMISSION)
    rows = await session.scalars(
        select(PiLearnedPack)
        .where(
            PiLearnedPack.tenant_id == scope.tenant_id,
            PiLearnedPack.environment_id == scope.environment_id,
        )
        .order_by(PiLearnedPack.created_at.desc())
        .limit(100)
    )
    return {"items": [_pack(r) for r in rows]}


@router.post("/packs/{pack_id}/approve-listening")
async def approve_pack_listening(pack_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    """The listening sections look right: the pack runs in shadow (counted, never shown)."""
    await require_pi(session, scope, PERMISSION)
    row = await _own_pack(session, scope, pack_id)
    await learning_packs.approve_listening(session, scope, row, scope.user_id)
    await session.commit()
    return _pack(row)


class CareInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    care: list[str] = Field(min_length=1, max_length=6)
    scope_rule: str = Field(max_length=600)


@router.post("/packs/{pack_id}/approve-care")
async def approve_pack_care(
    pack_id: UUID, data: CareInput, scope: Scope, session: Session
) -> dict[str, Any]:
    """A person writes what pi must refuse or protect in this trade. A pack never goes live
    without it."""
    await require_pi(session, scope, PERMISSION)
    row = await _own_pack(session, scope, pack_id)
    await learning_packs.approve_care(
        session, scope, row, scope.user_id, data.care, data.scope_rule
    )
    await session.commit()
    return _pack(row)


@router.post("/packs/{pack_id}/reject")
async def reject_pack(pack_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, PERMISSION)
    row = await _own_pack(session, scope, pack_id)
    await learning_packs.close(session, scope, row, scope.user_id, "rejected")
    await session.commit()
    return _pack(row)


@router.post("/packs/{pack_id}/retire")
async def retire_pack(pack_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, PERMISSION)
    row = await _own_pack(session, scope, pack_id)
    await learning_packs.close(session, scope, row, scope.user_id, "retired")
    await session.commit()
    return _pack(row)


@router.get("/queue")
async def review_queue(scope: Scope, session: Session) -> dict[str, Any]:
    """The weekly human queue (spec 8.6): everything that waits for a person, with the reason."""
    await require_pi(session, scope, PERMISSION)
    lessons_waiting = await session.scalars(
        select(PiLearningLesson).where(
            PiLearningLesson.tenant_id == scope.tenant_id,
            PiLearningLesson.environment_id == scope.environment_id,
            PiLearningLesson.status == "review",
        )
    )
    packs_waiting = await session.scalars(
        select(PiLearnedPack).where(
            PiLearnedPack.tenant_id == scope.tenant_id,
            PiLearnedPack.environment_id == scope.environment_id,
            PiLearnedPack.status.in_(("draft", "shadow")),
            PiLearnedPack.care_approved.is_(False),
        )
    )
    flagged = await session.scalars(
        select(PiLearningChange)
        .where(
            PiLearningChange.tenant_id == scope.tenant_id,
            PiLearningChange.environment_id == scope.environment_id,
            PiLearningChange.status == "review",
        )
        .order_by(PiLearningChange.created_at.desc())
        .limit(50)
    )
    return {
        "lessons": [_lesson(r) for r in lessons_waiting],
        "packs": [_pack(r) for r in packs_waiting],
        "flagged_changes": [
            {"id": c.id, "kind": c.kind, "reason": c.reason, "created_at": c.created_at}
            for c in flagged
        ],
    }
