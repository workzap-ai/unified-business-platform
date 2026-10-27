"""The problem map and the Solution Box status on the PI Customer dashboard (pi platform spec
Book 5, 4.9). Mounted inside the portal router (see routes.py), so it has the same signed cookie,
CSRF check and the same rule that decides which conversations are the customer's.

Every read and write is limited to the customer of ONE conversation that belongs to the signed-in
number (`service.one`); no id from the request ever picks another customer. No amount is returned
anywhere: the box card says whether a document is approved or sent, never what it costs.
"""

import re
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.rate_limit import hit
from app.modules.access.dependencies import Session
from app.modules.pi import box, box_signals, map_builder
from app.modules.pi.box_models import PiMapVersion, PiSolutionBox
from app.modules.pi.brain_docs_models import PiBrainDocument
from app.modules.pi.models import PiConversation
from app.modules.pi.problem_models import PiProblem
from app.modules.pi.problems import ProblemBook, redact
from app.modules.pi_customer import access, service
from app.modules.pi_customer.access import CustomerSession
from app.shared.scope import WorkspaceScope

router = APIRouter()
Customer = Annotated[CustomerSession, Depends(access.current)]

NODE = re.compile(r"^P(\d{1,6})$")
MAX_LABEL = 60


class ProblemEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["resolve", "park", "reopen", "rename", "rank", "unrank"]
    label: str = Field(default="", max_length=MAX_LABEL * 2)
    # "rank": where this problem comes in the owner's own order, 1 is where to start (B4)
    priority: int | None = Field(default=None, ge=1, le=box_signals.MAX_RANK)


def _scope(conversation: PiConversation) -> WorkspaceScope:
    """Reads and writes on one customer's own rows; no permissions are granted."""
    return WorkspaceScope.system(
        conversation.tenant_id,
        conversation.environment_id,
        frozenset(),
        "PI customer portal",
    )


async def _owned(
    session: Any, customer: CustomerSession, conversation_id: UUID
) -> tuple[PiConversation, WorkspaceScope]:
    found = await service.one(session, customer.phone, conversation_id)
    if found is None:
        raise HTTPException(404, "Conversation not found")
    return found[0], _scope(found[0])


def _version_view(row: PiMapVersion) -> dict[str, Any]:
    body = row.map_json or {}
    return {
        "version": row.version,
        "created_at": row.created_at,
        "shared_at": row.shared_at,
        "problems": len(body.get("nodes") or []),
        "links": len(body.get("links") or []),
    }


def _map_view(row: PiMapVersion) -> dict[str, Any]:
    return {**_version_view(row), "map": {k: v for k, v in (row.map_json or {}).items()}}


async def _payload(
    session: Any, conversation: PiConversation, scope: WorkspaceScope
) -> dict[str, Any]:
    rows = await map_builder.versions(session, scope, conversation.customer_id)
    return {
        "available": bool(rows),
        "language": conversation.language,
        "latest": _map_view(rows[-1]) if rows else None,
        "versions": [_version_view(r) for r in reversed(rows)],
    }


@router.get("/conversations/{conversation_id}/map")
async def get_map(
    conversation_id: UUID,
    customer: Customer,
    request: Request,
    session: Session,
) -> dict[str, Any]:
    """The latest map version, with the list of older ones. A change to the noted problems since
    the last version becomes a new version here, so the page is always the live map."""
    if not await hit(request, "pi-customer-map", customer.phone, 240, 3600):
        raise HTTPException(429, "Please wait a moment and try again.")
    conversation, scope = await _owned(session, customer, conversation_id)
    await map_builder.save_if_changed(session, scope, conversation.customer_id)
    await session.commit()
    return await _payload(session, conversation, scope)


@router.get("/conversations/{conversation_id}/map/{version}")
async def get_map_version(
    conversation_id: UUID,
    version: int,
    customer: Customer,
    session: Session,
) -> dict[str, Any]:
    conversation, scope = await _owned(session, customer, conversation_id)
    row = await session.scalar(
        select(PiMapVersion).where(
            PiMapVersion.tenant_id == scope.tenant_id,
            PiMapVersion.environment_id == scope.environment_id,
            PiMapVersion.customer_id == conversation.customer_id,
            PiMapVersion.version == version,
        )
    )
    if row is None:
        raise HTTPException(404, "Map version not found")
    return _map_view(row)


@router.get("/conversations/{conversation_id}/box")
async def get_box(
    conversation_id: UUID,
    customer: Customer,
    session: Session,
) -> dict[str, Any]:
    """Where the Solution Box stands, and whether a document is approved or sent. No amounts."""
    conversation, scope = await _owned(session, customer, conversation_id)
    base = (
        PiSolutionBox.tenant_id == scope.tenant_id,
        PiSolutionBox.environment_id == scope.environment_id,
        PiSolutionBox.customer_id == conversation.customer_id,
    )
    box = await session.scalar(
        select(PiSolutionBox).where(*base).order_by(PiSolutionBox.version.desc())
    )
    latest = await map_builder.latest_version(session, scope, conversation.customer_id)
    if box is None:
        state, version = ("collecting" if latest is not None else None), 1
    else:
        state, version = box.state, box.version
    document = await session.scalar(
        select(PiBrainDocument)
        .where(
            PiBrainDocument.tenant_id == scope.tenant_id,
            PiBrainDocument.environment_id == scope.environment_id,
            PiBrainDocument.customer_id == conversation.customer_id,
            PiBrainDocument.kind == "solution",
            PiBrainDocument.status.in_(("approved", "sent")),
        )
        .order_by(PiBrainDocument.version.desc())
    )
    return {
        "available": state is not None,
        "state": state,
        "version": version,
        "map_version": latest.version if latest else None,
        "document": (
            {
                "ref": document.ref,
                "approved": True,
                "sent": document.status == "sent",
                "sent_at": document.sent_at,
            }
            if document is not None
            else None
        ),
    }


async def _apply(
    session: Any, scope: WorkspaceScope, problem: PiProblem, body: ProblemEdit
) -> bool:
    """The same edits the chat makes to a noted problem (resolved, parked, renamed), as the
    person, with a revision each. Returns whether anything changed."""
    book = ProblemBook(session, scope, problem.customer_id, "en")
    tags = list(problem.tags or [])
    if body.action == "resolve":
        if problem.status == "resolved":
            return False
        diff: dict[str, Any] = {"status": [problem.status, "resolved"]}
        problem.status = "resolved"
        reason = "resolved"
    elif body.action == "park":
        if map_builder.PARKED_TAG in tags:
            return False
        diff = {"tags": [tags, [*tags, map_builder.PARKED_TAG]]}
        problem.tags = [*tags, map_builder.PARKED_TAG]
        reason = "parked"
    elif body.action == "reopen":
        diff = {}
        if problem.status == "resolved":
            diff["status"] = ["resolved", "confirmed"]
            problem.status = "confirmed"
        if map_builder.PARKED_TAG in tags:
            kept = [t for t in tags if t != map_builder.PARKED_TAG]
            diff["tags"] = [tags, kept]
            problem.tags = kept
        if not diff:
            return False
        reason = "reopened"
    elif body.action in ("rank", "unrank"):
        wanted = body.priority if body.action == "rank" else None
        if body.action == "rank" and wanted is None:
            raise HTTPException(422, "Choose a priority")
        if box_signals.rank_of(tags) == wanted:
            return False
        kept = box_signals.with_rank(tags, wanted)
        diff = {"tags": [tags, kept]}
        problem.tags = kept
        reason = "ranked" if wanted else "unranked"
    else:
        label = redact(" ".join(body.label.split())[:MAX_LABEL])[0].strip()
        if not label:
            raise HTTPException(422, "Write the new name")
        if label == problem.title_local:
            return False
        diff = {"title_local": [problem.title_local, label]}
        problem.title_local = label
        reason = "renamed"
    problem.revision += 1
    await book._revise(problem, diff, reason, "person")  # noqa: SLF001  (same module family)
    return True


async def _mark_reviewed(
    session: Any, scope: WorkspaceScope, conversation: PiConversation, *, ranked: bool
) -> None:
    """The owner changed their map here: B3 holds, and B4 when they ranked a problem. Written to
    THIS conversation's brief (the one the signed-in number owns), and only when the Solution Box
    offer is on for the workspace, so other workspaces' briefs are untouched."""
    from app.modules.pi.configuration import settings_row

    if not box.box_offer_enabled((await settings_row(session, scope)).response_rules):
        return
    brief = dict(conversation.service_brief or {})
    brief["map_reviewed"] = True
    if ranked:
        brief["ranked"] = True
    conversation.service_brief = brief


@router.post("/conversations/{conversation_id}/map/problems/{node}")
async def edit_problem(
    conversation_id: UUID,
    node: str,
    body: ProblemEdit,
    request: Request,
    customer: Customer,
    session: Session,
) -> dict[str, Any]:
    """Mark a problem resolved, parked or reopened, rename it, or rank it (1 is where to start).
    Applied to the same noted problem pi keeps in the chat, so the map in WhatsApp and here never
    disagree."""
    if not await hit(request, "pi-customer-map-edit", customer.phone, 120, 3600):
        raise HTTPException(429, "Please wait a moment and try again.")
    found = NODE.match(node)
    if found is None:
        raise HTTPException(404, "Problem not found")
    conversation, scope = await _owned(session, customer, conversation_id)
    problem = await session.scalar(
        select(PiProblem)
        .where(
            PiProblem.tenant_id == scope.tenant_id,
            PiProblem.environment_id == scope.environment_id,
            PiProblem.customer_id == conversation.customer_id,
            PiProblem.number == int(found.group(1)),
            PiProblem.status.in_(map_builder.DRAWN),
        )
        .with_for_update()
    )
    if problem is None:
        raise HTTPException(404, "Problem not found")
    changed = await _apply(session, scope, problem, body)
    if changed:
        await _mark_reviewed(session, scope, conversation, ranked=body.action == "rank")
    await session.flush()
    await map_builder.save_if_changed(session, scope, conversation.customer_id)
    await session.commit()
    return await _payload(session, conversation, scope)
