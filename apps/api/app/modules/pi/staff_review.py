"""The staff review of one pi conversation (architecture vision sections 4, 5, 9; spec 8.11.1,
10.7 and 6.5): the problem map as the briefing, the four dials, the cached diagnosis and the idea
budget, why pi handed over, the Solution Box and its offer log, and the labels and live alerts.

Everything here is a read. The pure helpers (`classify_origin`, `node_status`, `alerts_for`,
`idea_budget`, `mask_phone`, `label_of_move`) take plain values so they can be tested without a
database. The loaders only select, always through `WorkspaceRepository`, and nothing calls a model.
Text that came from the owner is redacted again on the way out (card, ID, account, email, phone),
the customer is shown by a short reference and a masked number, never by name.
"""

import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from app.modules.pi import box, box_signals, dials, map_builder, solution_ask, taxonomy
from app.modules.pi.box_models import PiMapVersion, PiOfferLog, PiSolutionBox
from app.modules.pi.models import PiAgentRun, PiConversation, PiHandoff, PiMessage
from app.modules.pi.problem_models import PiProblem
from app.modules.pi.problems import redact
from app.modules.pi.think_models import PiHypothesis, PiMoveLog
from app.modules.pi_saas.models import PiStaffRequest
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

PER_PROBLEM = box.IDEAS_PER_PROBLEM
PER_BUSINESS = 8  # Book 5 decision 5: two ideas per problem, up to eight per business
DIAL_MESSAGES = 60  # the dials replay at most this many of the owner's latest messages
SIGNAL_MESSAGES = 10  # alerts read the owner's latest messages
MOVES_SHOWN = 10
OFFERS_SHOWN = 20
TEXT_LIMIT = 400

# Alert levels, most urgent first (spec 10.7: red, amber, yellow; a plain open handoff is blue).
LEVELS = ("red", "amber", "yellow", "blue")
# Staff requests that stand for "a solution or price request" in spec 10.7.
ASK_KINDS = frozenset({"price", "price_request", "review_document", "approve", "quote_expired"})

# Where each way of handing over comes from (spec 6.5): the five a staff member needs to tell apart.
FAILURE_REASONS = frozenset({"provider_failure", "tool_failure", "low_confidence"})
POLICY_REASONS = frozenset({"policy", "sensitive", "complaint"})

# The spec 10.7 label of a message, read from the move that wrote it (None: no label of its own).
MOVE_LABELS = {
    "ask": "Listening",
    "invite": "Listening",
    "M16_hold_space": "Listening",
    "M1_reflect": "Listening",
    "summarise": "Noted",
    "give_ideas": "Ideas",
}


def mask_phone(phone: str | None) -> str:
    """Only the last four digits of a number are ever shown."""
    digits = re.sub(r"\D", "", phone or "")
    return f"•••• {digits[-4:]}" if len(digits) >= 4 else "••••"


def clean(text: str | None, limit: int = TEXT_LIMIT) -> str:
    """Owner-derived text, redacted once more and shortened. Never raises."""
    return redact(str(text or ""))[0][:limit]


def classify_origin(reason: str, run_intent: str | None, created_by: str | None) -> str:
    """Why pi handed over: keyword | owner_asked | failure | operator_review | policy | other."""
    if reason == "customer_request":
        return "keyword" if run_intent == "human_request" else "owner_asked"
    if reason in FAILURE_REASONS:
        return "failure"
    if reason == "manual":
        return "operator_review" if (created_by or "").lower() != "system" else "other"
    if reason in POLICY_REASONS:
        return "policy"
    return "other"


ORIGIN_TEXT = {
    "keyword": "A handoff word in the owner's message (kept to whole words that ask for someone)",
    "owner_asked": "The owner asked for a person",
    "failure": "pi could not answer (model, tool or low confidence)",
    "operator_review": "A team member handed the chat over",
    "policy": "A safety or policy rule stopped pi",
    "other": "Handed over",
}


def node_status(status: str, tags: list[str] | None, stale: bool) -> str:
    """open | confirmed | in_box | parked | resolved | stale for one problem row (spec 4.2)."""
    if status == "resolved":
        return "resolved"
    if status == map_builder.PARKED or map_builder.PARKED_TAG in (tags or []):
        return "parked"
    if stale:
        return "stale"
    if status in ("in_document", "quoted", "in_build"):
        return "in_box"
    if status in ("confirmed", "corrected"):
        return "confirmed"
    return "open"


def idea_budget(
    given: int, rounds_by_problem: dict[str, int], customer_given: int | None = None
) -> dict[str, Any]:
    """The idea caps: PER_PROBLEM per problem and PER_BUSINESS per business (Book 5 decision 5)."""
    total = max(given, customer_given or 0)
    return {
        "given_in_chat": given,
        "given_for_business": customer_given if customer_given is not None else given,
        "per_problem_cap": PER_PROBLEM,
        "per_business_cap": PER_BUSINESS,
        "business_remaining": max(0, PER_BUSINESS - total),
        "rounds_by_problem": rounds_by_problem,
    }


def alerts_for(
    inbound: list[str],
    *,
    handoff_open: bool,
    asks_open: int,
    asks_unanswered: int,
    fatigue: bool = False,
) -> list[dict[str, str]]:
    """Live alerts (spec 10.7), most urgent first. `inbound` is the owner's latest messages."""
    found: list[dict[str, str]] = []
    if any(solution_ask.churn_risk(t) for t in inbound):
        found.append(
            {
                "level": "red",
                "key": "churn_risk",
                "label": "Churn risk",
                "detail": "The owner said they may look elsewhere.",
            }
        )
    if asks_unanswered:
        found.append(
            {
                "level": "amber",
                "key": "request_unanswered",
                "label": "Request unanswered",
                "detail": "A solution or price request has stayed open for more than one pi turn.",
            }
        )
    impatient = sum(1 for t in inbound if solution_ask.impatient(t))
    if impatient >= 2 or (impatient >= 1 and fatigue):
        found.append(
            {
                "level": "yellow",
                "key": "frustration",
                "label": "Frustration",
                "detail": "Impatience detected more than once.",
            }
        )
    if handoff_open:
        found.append(
            {
                "level": "blue",
                "key": "handoff_open",
                "label": "Human handoff open",
                "detail": "A person was asked to take this chat.",
            }
        )
    if asks_open and not asks_unanswered:
        found.append(
            {
                "level": "blue",
                "key": "request_open",
                "label": "Request open",
                "detail": "The team has a request to answer.",
            }
        )
    return found


def alert_rank(alerts: list[dict[str, str]]) -> int:
    return min((LEVELS.index(a["level"]) for a in alerts), default=len(LEVELS))


# --- loaders -----------------------------------------------------------------------------------


async def inbound_texts(
    session: Any, scope: WorkspaceScope, conversation_id: UUID, limit: int
) -> list[str]:
    """The owner's latest messages, oldest first."""
    rows = await session.scalars(
        WorkspaceRepository(session, PiMessage, scope)
        .select()
        .where(
            PiMessage.conversation_id == conversation_id,
            PiMessage.direction == "inbound",
            PiMessage.message_type == "text",
        )
        .order_by(PiMessage.created_at.desc())
        .limit(limit)
    )
    return [m.body for m in reversed(list(rows))]


async def unanswered_counts(
    session: Any, scope: WorkspaceScope, conversation_ids: list[UUID]
) -> dict[UUID, tuple[int, int]]:
    """Per conversation: (open staff requests, those that are a solution or price request with
    two or more pi replies since they were raised)."""
    if not conversation_ids:
        return {}
    requests = list(
        await session.scalars(
            WorkspaceRepository(session, PiStaffRequest, scope)
            .select()
            .where(
                PiStaffRequest.conversation_id.in_(conversation_ids),
                PiStaffRequest.status == "open",
            )
        )
    )
    out: dict[UUID, tuple[int, int]] = {}
    for request in requests:
        turns = (
            await session.scalar(
                select(func.count())
                .select_from(PiMessage)
                .where(
                    PiMessage.tenant_id == scope.tenant_id,
                    PiMessage.environment_id == scope.environment_id,
                    PiMessage.conversation_id == request.conversation_id,
                    PiMessage.sender_type == "ai",
                    PiMessage.created_at > request.created_at,
                )
            )
            or 0
        )
        open_, late = out.get(request.conversation_id, (0, 0))
        out[request.conversation_id] = (
            open_ + 1,
            late + int(request.kind in ASK_KINDS and turns >= 2),
        )
    return out


async def map_section(
    session: Any, scope: WorkspaceScope, customer_id: UUID, now: datetime
) -> dict[str, Any]:
    problems, links = await map_builder.current_inputs(session, scope, customer_id)
    latest = await map_builder.latest_version(session, scope, customer_id)
    shared = await map_builder.last_shared(session, scope, customer_id)
    number = {p.id: p.number for p in problems}
    nodes = []
    for p in problems:
        if p.merged_into is not None:
            continue
        stale = map_builder.is_stale(p, now) and str(p.status) != "resolved"
        category = p.category if p.category in taxonomy.KEYS else taxonomy.OTHER
        nodes.append(
            {
                "id": f"P{p.number}",
                "number": p.number,
                "title": clean(p.title, 120),
                "category": category,
                "category_label": taxonomy.label(category),
                "subtype": p.subtype or None,
                "goal_verb": p.goal_verb,
                "status": node_status(str(p.status), p.tags, stale),
                "rank": box_signals.rank_of(p.tags),
                "raised_voluntarily": bool(p.raised_voluntarily),
            }
        )
    drawn = []
    for link in links:
        a, b = number.get(link.from_id), number.get(link.to_id)
        if a is None or b is None or str(link.status) == "rejected":
            continue
        confirmed = str(link.status) == "confirmed" or str(link.evidence) == "confirmed"
        drawn.append(
            {
                "from": f"P{a}",
                "to": f"P{b}",
                "type": str(link.type),
                "evidence": "confirmed" if confirmed else str(link.evidence),
            }
        )
    return {
        "version": latest.version if latest else None,
        "shared_version": shared.version if shared else None,
        "shared_at": shared.shared_at if shared else None,
        "up_to_date_with_owner": bool(latest and shared and shared.version == latest.version),
        "nodes": nodes,
        "links": drawn,
    }


async def dials_section(
    session: Any, scope: WorkspaceScope, conversation: PiConversation
) -> dict[str, Any]:
    texts = await inbound_texts(session, scope, conversation.id, DIAL_MESSAGES)
    state = dials.estimate(texts)
    moves = list(
        await session.scalars(
            WorkspaceRepository(session, PiMoveLog, scope)
            .select()
            .where(PiMoveLog.conversation_id == conversation.id)
            .order_by(PiMoveLog.created_at.desc())
            .limit(MOVES_SHOWN)
        )
    )
    hypotheses = list(
        await session.scalars(
            WorkspaceRepository(session, PiHypothesis, scope)
            .select()
            .where(PiHypothesis.conversation_id == conversation.id, PiHypothesis.ignored.is_(False))
            .order_by(PiHypothesis.created_at.desc())
            .limit(20)
        )
    )
    return {
        "dials": state.as_dict(),
        "posture": dials.posture(state),
        "messages_read": state.messages_seen,
        "recomputed": True,  # replayed from the owner's messages now; nothing is stored
        "moves": [
            {
                "move": m.move,
                "reason": clean(m.reason, 200),
                "had_question": bool(m.had_question),
                "at": m.created_at,
            }
            for m in moves
        ],
        "hypotheses": [
            {
                "text": clean(h.text, 300),
                "confidence": h.confidence,
                "status": h.status,
                "confirmed_by_owner": h.status == "confirmed",
                "evidence_for": len(h.evidence_for or []),
                "evidence_against": len(h.evidence_against or []),
                "cheapest_test": clean(h.cheapest_test, 300),
            }
            for h in hypotheses
            if h.status != "dropped"
        ],
    }


async def diagnosis_section(
    session: Any,
    scope: WorkspaceScope,
    conversation: PiConversation,
    titles: dict[str, str],
) -> dict[str, Any]:
    brief = conversation.service_brief or {}
    diag = brief.get("expert_diag")
    cached = None
    if isinstance(diag, dict):
        cached = {
            "main_problem": clean(diag.get("problem"), 200),
            "likely_causes": [clean(c, 200) for c in (diag.get("causes") or [])[:5]],
            "suggested_next_question": clean(diag.get("question"), 300),
            "at": diag.get("at"),
        }
    given = int(brief.get("ideas_given") or 0)
    rounds = Counter(str(p) for p in brief.get("ideas_problems") or [])
    siblings = await session.scalars(
        WorkspaceRepository(session, PiConversation, scope)
        .select()
        .where(PiConversation.customer_id == conversation.customer_id)
    )
    business_given = sum(int((c.service_brief or {}).get("ideas_given") or 0) for c in siblings)
    return {
        "diagnosis": cached,
        "ideas": idea_budget(
            given, {titles.get(pid, pid[:8]): n for pid, n in rounds.items()}, business_given
        ),
    }


async def handover_section(
    session: Any, scope: WorkspaceScope, conversation: PiConversation
) -> dict[str, Any]:
    handoff = await session.scalar(
        WorkspaceRepository(session, PiHandoff, scope)
        .select()
        .where(PiHandoff.conversation_id == conversation.id)
        .order_by(PiHandoff.created_at.desc())
        .limit(1)
    )
    requests = list(
        await session.scalars(
            WorkspaceRepository(session, PiStaffRequest, scope)
            .select()
            .where(PiStaffRequest.conversation_id == conversation.id)
            .order_by(PiStaffRequest.created_at.desc())
            .limit(10)
        )
    )
    out: dict[str, Any] = {"mode": conversation.mode, "handoff": None, "requests": []}
    if handoff is not None:
        run = (
            await session.scalar(
                WorkspaceRepository(session, PiAgentRun, scope)
                .select()
                .where(PiAgentRun.id == handoff.run_id)
            )
            if handoff.run_id
            else None
        )
        origin = classify_origin(
            handoff.reason, run.intent if run else None, handoff.created_by_label
        )
        if origin == "other" and any(r.kind == "human_requested" for r in requests):
            origin = "owner_asked"
        out["handoff"] = {
            "id": handoff.id,
            "status": handoff.status,
            "reason": handoff.reason,
            "priority": handoff.priority,
            "summary": clean(handoff.summary, 1000),
            "origin": origin,
            "origin_text": ORIGIN_TEXT[origin],
            "assigned_label": handoff.assigned_label,
            "created_at": handoff.created_at,
        }
    out["requests"] = [
        {
            "id": r.id,
            "kind": r.kind,
            "status": r.status,
            "priority": r.priority,
            "question": clean(r.question, 500),
            "context_summary": clean(r.context_summary, 500),
            "created_at": r.created_at,
        }
        for r in requests
    ]
    return out


async def box_section(
    session: Any, scope: WorkspaceScope, conversation: PiConversation
) -> dict[str, Any]:
    box = await session.scalar(
        WorkspaceRepository(session, PiSolutionBox, scope)
        .select()
        .where(PiSolutionBox.customer_id == conversation.customer_id)
        .order_by(PiSolutionBox.version.desc())
        .limit(1)
    )
    offers = list(
        await session.scalars(
            WorkspaceRepository(session, PiOfferLog, scope)
            .select()
            .where(PiOfferLog.conversation_id == conversation.id)
            .order_by(PiOfferLog.created_at.desc())
            .limit(OFFERS_SHOWN)
        )
    )
    version = None
    if box is not None and box.map_version_id is not None:
        version = await session.scalar(
            WorkspaceRepository(session, PiMapVersion, scope)
            .select()
            .where(PiMapVersion.id == box.map_version_id)
        )
    return {
        "box": None
        if box is None
        else {
            "state": box.state,
            "version": box.version,
            "reviewer": box.reviewer,
            "owner_ranking": box.owner_ranking or [],
            "map_version": version.version if version else None,
            "updated_at": box.updated_at,
        },
        "offers": [
            {
                "rule": o.rule,
                "allowed": bool(o.allowed),
                "blocked_reason": clean(o.blocked_reason, 300) or None,
                "at": o.created_at,
            }
            for o in offers
        ],
    }


async def labels_section(
    session: Any, scope: WorkspaceScope, conversation: PiConversation, moves: list[dict[str, Any]]
) -> dict[str, Any]:
    runs = list(
        await session.scalars(
            WorkspaceRepository(session, PiAgentRun, scope)
            .select()
            .where(PiAgentRun.conversation_id == conversation.id, PiAgentRun.intent.is_not(None))
            .order_by(PiAgentRun.created_at.desc())
            .limit(20)
        )
    )
    return {
        "intents": dict(Counter(str(r.intent) for r in runs)),
        "message_labels": [
            {"label": MOVE_LABELS[m["move"]], "at": m["at"]}
            for m in moves
            if m["move"] in MOVE_LABELS
        ],
    }


async def review(
    session: Any, scope: WorkspaceScope, conversation: PiConversation, customer_phone: str | None
) -> dict[str, Any]:
    """The whole review of one conversation."""
    now = datetime.now(UTC)
    the_map = await map_section(session, scope, conversation.customer_id, now)
    titles = {}
    for p in await session.scalars(
        WorkspaceRepository(session, PiProblem, scope)
        .select()
        .where(PiProblem.customer_id == conversation.customer_id)
    ):
        titles[str(p.id)] = clean(p.title, 80)
    thinking = await dials_section(session, scope, conversation)
    diagnosis = await diagnosis_section(session, scope, conversation, titles)
    handover = await handover_section(session, scope, conversation)
    box = await box_section(session, scope, conversation)
    labels = await labels_section(session, scope, conversation, thinking["moves"])
    inbound = await inbound_texts(session, scope, conversation.id, SIGNAL_MESSAGES)
    counts = (await unanswered_counts(session, scope, [conversation.id])).get(
        conversation.id, (0, 0)
    )
    handoff = handover["handoff"]
    labels["alerts"] = alerts_for(
        inbound,
        handoff_open=bool(handoff and handoff["status"] in ("open", "assigned", "in_progress")),
        asks_open=counts[0],
        asks_unanswered=counts[1],
        fatigue=bool(thinking["dials"]["fatigue"]),
    )
    return {
        "conversation": {
            "id": conversation.id,
            "customer_ref": str(conversation.customer_id)[:8],
            "phone": mask_phone(customer_phone or conversation.contact_wa_id),
            "language": conversation.language,
            "mode": conversation.mode,
            "status": conversation.status,
            "flow_state": conversation.flow_state,
            "last_message_at": conversation.last_message_at,
        },
        "map": the_map,
        "thinking": thinking,
        **diagnosis,
        "handover": handover,
        "box": box,
        "labels": labels,
    }
