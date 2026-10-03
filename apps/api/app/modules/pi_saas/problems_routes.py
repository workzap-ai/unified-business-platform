"""Problems board for the business: every customer problem Pi found in conversations,
sorted into the business's departments (Sales, Finance, HR, IT, Operations...).

Pi reads each conversation and lists its separate problems with a department (the same
analysis customers see in PI Customer). When the team moves a problem to another
department, that move is kept for the problem and saved as an example Pi follows next
time, so the sorting learns the business's own rules. Only conversations the member may
see are listed.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import cast, func, literal_column, select, update
from sqlalchemy.dialects.postgresql import JSONB

from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.customers.models import Customer
from app.modules.pi.models import PiConversation, WhatsAppConnection
from app.modules.pi.service import PiService
from app.modules.pi_customer.service import analyse, departments_for, norm_title, place
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/problems", tags=["pi-problems"])
WINDOW_DAYS = 30
REFRESH_BATCH = 5


class MoveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: UUID
    index: int = Field(ge=0, lt=6)
    department: str = Field(pattern=r"^[a-z0-9_]{2,40}$")


async def _rows(session: Any, scope: Any) -> list[tuple[PiConversation, str]]:
    service = PiService(session, scope)
    since = datetime.now(UTC) - timedelta(days=WINDOW_DAYS)
    rows = await session.execute(
        select(PiConversation, Customer.name)
        .join(
            Customer,
            (Customer.id == PiConversation.customer_id)
            & (Customer.tenant_id == PiConversation.tenant_id),
        )
        .where(service.conversations.predicate(), PiConversation.last_message_at >= since)
        .order_by(PiConversation.last_message_at.desc())
        .limit(200)
    )
    return [(c, name or "Customer") for c, name in rows.all()]


def _fresh(conversation: PiConversation) -> dict[str, Any] | None:
    cached = (conversation.service_brief or {}).get("customer_issues")
    if isinstance(cached, dict) and cached.get("at") == conversation.last_message_at.isoformat():
        return cached
    return None


async def _board(session: Any, scope: Any) -> dict[str, Any]:
    departments, examples = await departments_for(session, scope.tenant_id, scope.environment_id)
    rows = await _rows(session, scope)
    problems: list[dict[str, Any]] = []
    stale = 0
    for conversation, customer in rows:
        report = _fresh(conversation)
        if report is None:
            stale += 1
            cached = (conversation.service_brief or {}).get("customer_issues")
            report = cached if isinstance(cached, dict) else None
        if report is None:
            continue
        overrides = (conversation.service_brief or {}).get("issue_departments") or {}
        for index, issue in enumerate(place(report.get("issues", []), departments, overrides)):
            problems.append(
                {
                    **issue,
                    "index": index,
                    "conversation_id": conversation.id,
                    "customer_name": customer,
                    "conversation_mode": conversation.mode,
                    "last_message_at": conversation.last_message_at,
                }
            )
    counts = {d["key"]: {"open": 0, "with_team": 0, "resolved": 0} for d in departments}
    for p in problems:
        counts.setdefault(p["department"], {"open": 0, "with_team": 0, "resolved": 0})
        counts[p["department"]][p.get("status", "open")] = (
            counts[p["department"]].get(p.get("status", "open"), 0) + 1
        )
    return {
        "departments": [{**d, **counts.get(d["key"], {})} for d in departments],
        "problems": problems,
        "waiting_for_analysis": stale,
        "examples_learned": len(examples),
        "window_days": WINDOW_DAYS,
    }


@router.get("")
async def board(scope: Scope, session: Session) -> dict[str, Any]:
    scope.require("pi.read")
    return await _board(session, scope)


@router.post("/refresh")
async def refresh(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    """Let Pi read the most recent conversations it hasn't sorted yet (a few at a time)."""
    scope.require("pi.read")
    state = request.app.state
    done = 0
    for conversation, _ in await _rows(session, scope):
        if done >= REFRESH_BATCH:
            break
        if _fresh(conversation) is not None:
            continue
        connection = await WorkspaceRepository(session, WhatsAppConnection, scope).find(
            WhatsAppConnection.id == conversation.connection_id
        )
        if connection is None:
            continue
        name = connection.display_name or "the business"
        await analyse(
            session, state.settings, state.http, state.sessions, conversation, connection, name
        )
        done += 1
    session.expire_all()
    return {**await _board(session, scope), "analysed": done}


@router.post("/move")
async def move(data: MoveInput, scope: Scope, session: Session) -> dict[str, Any]:
    """The team puts a problem in the right department. Pi keeps that for the problem and
    learns from it: the move becomes an example it follows for similar problems."""
    scope.require("pi.handoffs.manage")
    service = PiService(session, scope)
    conversation = await service.conversations.get(data.conversation_id)
    departments, examples = await departments_for(session, scope.tenant_id, scope.environment_id)
    if data.department not in {d["key"] for d in departments}:
        raise HTTPException(422, "Choose one of your departments")
    cached = (conversation.service_brief or {}).get("customer_issues")
    issues = cached.get("issues", []) if isinstance(cached, dict) else []
    if data.index >= len(issues):
        raise HTTPException(404, "That problem has changed. Refresh and try again.")
    issue = issues[data.index]
    title = norm_title(str(issue.get("title", "")))
    await session.execute(
        update(PiConversation)
        .where(
            PiConversation.tenant_id == conversation.tenant_id,
            PiConversation.id == conversation.id,
        )
        .values(
            service_brief=func.coalesce(PiConversation.service_brief, cast({}, JSONB)).op("||")(
                func.jsonb_build_object(
                    literal_column("'issue_departments'"),
                    func.coalesce(
                        PiConversation.service_brief["issue_departments"], cast({}, JSONB)
                    ).op("||")(cast({title: data.department}, JSONB)),
                )
            )
        )
        .execution_options(synchronize_session=False)
    )
    # The move teaches Pi: newest examples last, one per problem text, at most 40.
    from app.modules.pi.configuration import settings_row

    row = await settings_row(session, scope)
    rules = dict(row.handoff_rules or {})
    text = f"{issue.get('title', '')}: {issue.get('summary', '')}".strip(": ")[:400]
    kept = [e for e in rules.get("department_examples", []) if e.get("text") != text]
    rules["departments"] = rules.get("departments") or departments
    rules["department_examples"] = [*kept, {"text": text, "department": data.department}][-40:]
    row.handoff_rules = rules
    await record(
        session,
        "pi.problem_moved",
        scope=scope,
        entity_type="pi_conversation",
        entity_id=conversation.id,
        details={"department": data.department},
    )
    await session.commit()
    session.expire_all()
    return await _board(session, scope)
