"""The whole picture of one customer for the team (Owner OS and the pi app).

    GET /customers/{id}/pi-overview

- profile: who they are. Their record, plus what they told pi in any chat (business,
  what it does, where, their role), the language they use, and when they first came.
- projects: each deal with its journey (steps done of all) and the next step.
- requests + links: what pi understood they need, and how those requests connect (the
  Problem Map), the same data the customer sees on their own dashboard.
- counts: every number counts requests (waiting on them / on us / done / paused).

Cheap: it uses saved records and pi's cached analysis. Only a chat whose analysis is
out of date (a new message, or older analysis rules) is analysed again, at most a few
per view, so the Problem Map never waits for the customer's next message.
"""

import logging
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy.exc import DBAPIError

from app.modules.access.dependencies import Scope, Session
from app.modules.customers.models import Customer
from app.modules.pi.models import PiConversation
from app.modules.pi.service_conversation import PLACEHOLDER_NAME, STATUS_TEXT, merge_profile
from app.modules.sales.models import SalesLead
from app.shared.errors import BusinessRuleViolation
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/customers", tags=["customer-overview"])
LINK_FIELDS = ("a", "b", "a_title", "b_title", "type", "reason", "benefit", "confidence")


# Words that don't tell two requests apart ("Website request" vs "Website project").
GENERIC = {
    "request",
    "requests",
    "project",
    "projects",
    "inquiry",
    "system",
    "details",
    "requirement",
    "requirements",
    "new",
    "the",
    "for",
    "and",
    "with",
    "your",
    "my",
}
# Not a project: the customer asking for their map, a meeting, an invoice...
NOT_A_PROJECT = re.compile(
    r"\b(?:map|meeting|meet|invoice|receipt|payment method|status|link)\b", re.IGNORECASE
)
PROJECT_STAGE = {
    "collecting": ("noted", "pi", "pi: collecting the remaining details"),
    "awaiting_confirmation": ("need_answer", "client", ""),
    "confirmed": ("on_it", "team", "Team: prepare the proposal"),
    "with_team": ("on_it", "team", "Team: working on it"),
}


def _words(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", title.lower()) if w not in GENERIC}


def _same(a: str, b: str) -> bool:
    return bool(_words(a) & _words(b)) or a.strip().lower() == b.strip().lower()


def brief_projects(
    conversation: PiConversation, issues: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Projects in the chat's brief that pi's latest analysis left out (it reads recent
    messages, so older projects fall off): on the map too, with their status."""
    out: list[dict[str, Any]] = []
    for project in (conversation.service_brief or {}).get("projects") or []:
        title = str(project.get("title") or "").strip()
        if (
            not title
            or NOT_A_PROJECT.search(title)
            or any(_same(title, str(i.get("title", ""))) for i in [*issues, *out])
        ):
            continue
        stage, ball, step = PROJECT_STAGE.get(
            str(project.get("status") or "collecting"), PROJECT_STAGE["collecting"]
        )
        missing = [str(m) for m in project.get("missing") or [] if m]
        out.append(
            {
                "title": title[:120],
                "stage": stage,
                "ball_with": ball,
                # A status line is not the customer's problem: fall back to the service.
                "summary": (
                    str(project.get("service") or "")
                    if STATUS_TEXT.search(str(project.get("details") or ""))
                    else str(project.get("details") or project.get("service") or "")
                )[:400],
                "next_step": step,
                "open_question": (
                    "Confirm the brief so the team can start"
                    if stage == "need_answer"
                    else (f"Still needed: {', '.join(missing)[:200]}" if missing else "")
                ),
                "area": str(project.get("service") or "")[:40],
                "impact": 3,
                "urgency": 3,
                "conversation_id": str(conversation.id),
                "from_brief": True,
            }
        )
    return out


def follow_deals(issues: list[dict[str, Any]], projects: list[dict[str, Any]]) -> None:
    """A request whose deal is won (agreed and paid) is never "the team prepares the
    proposal" again: it's being built, or done once every step of the deal is."""
    for issue in issues:
        deal = next(
            (
                p
                for p in projects
                if p.get("stage") == "won" and _same(str(issue.get("title", "")), p["title"])
            ),
            None,
        )
        if deal is None:
            continue
        finished = bool(deal.get("steps_total")) and deal.get("steps_done") == deal.get(
            "steps_total"
        )
        issue["stage"] = "live" if finished else "building"
        issue["ball_with"] = "team" if not finished else "none"
        issue["open_question"] = ""
        nxt = (deal.get("next") or {}).get("title") or "Deliver the work"
        issue["next_step"] = "Nothing, it's done" if finished else f"Team: {nxt}"


def _counts(issues: list[dict[str, Any]]) -> dict[str, int]:
    out = {"waiting_on_them": 0, "waiting_on_us": 0, "done": 0, "paused": 0}
    for issue in issues:
        stage = issue.get("stage")
        if stage in ("live", "closed"):
            out["done"] += 1
        elif stage == "paused":
            out["paused"] += 1
        elif issue.get("ball_with") == "client":
            out["waiting_on_them"] += 1
        else:
            out["waiting_on_us"] += 1
    return out


async def _requests(
    session: Any, conversations: list[PiConversation]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Requests and links from pi's latest analysis of each chat (newest chat first)."""
    from app.modules.pi_customer import service as portal

    issues: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    headline = ""
    for conversation in conversations:
        report = (conversation.service_brief or {}).get("customer_issues")
        if not isinstance(report, dict) or not report.get("issues"):
            issues += brief_projects(conversation, issues)
            continue
        departments, _ = await portal.departments_for(
            session, conversation.tenant_id, conversation.environment_id
        )
        names = {d["key"]: d["name"] for d in departments}
        overrides = (conversation.service_brief or {}).get("issue_departments") or {}
        hours = await portal.team_update_hours(session, conversation)
        for issue in portal.place(report.get("issues", []), departments, overrides):
            view = portal.issue_view(
                {**issue, "department_name": names.get(issue.get("department", ""), "")},
                report,
                None,
                hours,
            )
            issues.append({**view, "conversation_id": str(conversation.id)})
        links += [
            {key: link.get(key) for key in LINK_FIELDS}
            for link in report.get("links") or []
            if isinstance(link, dict) and link.get("status") in ("auto", "confirmed")
        ]
        headline = headline or str(report.get("headline") or "")
        issues += brief_projects(conversation, issues)
    return issues, links, headline


NOTE_TEXT = ("problem", "goal", "audience", "target_date")
NOTE_LISTS = ("features", "references", "decisions", "questions")


def project_notes(requirements: dict[str, Any]) -> dict[str, Any]:
    """pi's deep notes on one project (from its deal): why, for whom, what it must do,
    what's decided and what's still open. Budget stays out of this view."""
    notes: dict[str, Any] = {
        key: str(requirements.get(key) or "")[:500] for key in NOTE_TEXT if requirements.get(key)
    }
    for key in NOTE_LISTS:
        value = requirements.get(key)
        if isinstance(value, list) and value:
            notes[key] = [str(v)[:200] for v in value][:20]
    return notes


def _documents_for(
    title: str, documents: list[dict[str, Any]], only_project: bool = False
) -> list[dict[str, str]]:
    """The documents the customer sent for this project (by title words; every document
    when it is their only project)."""
    return [
        {"file_id": str(d["file_id"]), "name": str(d.get("name") or "Document")}
        for d in documents
        if d.get("file_id") and (only_project or _same(title, str(d.get("title") or "")))
    ][:5]


async def _projects(session: Any, scope: Any, customer_id: UUID) -> list[dict[str, Any]]:
    """Each deal with its journey (steps done / total) and the next step."""
    from app.modules.pi_saas.deal_routes import journey

    leads = list(
        await session.scalars(
            WorkspaceRepository(session, SalesLead, scope)
            .select()
            .where(SalesLead.customer_id == customer_id)
            .order_by(SalesLead.created_at.desc())
            .limit(12)
        )
    )
    from app.modules.pi.models import PiConversation as Chat

    documents: list[dict[str, Any]] = []
    feedback: list[dict[str, Any]] = []
    for brief in await session.scalars(
        WorkspaceRepository(session, Chat, scope)
        .select()
        .with_only_columns(Chat.service_brief)
        .where(Chat.customer_id == customer_id)
    ):
        documents += (brief or {}).get("documents") or []
        feedback += [f for f in (brief or {}).get("feedback") or [] if isinstance(f, dict)]
    projects = []
    for lead in leads:
        item: dict[str, Any] = {
            "lead_id": lead.id,
            "title": lead.title,
            "stage": lead.stage,
            "value": str(lead.estimated_value) if lead.estimated_value is not None else None,
            "currency": lead.currency,
            "created_at": lead.created_at,
            "service": str((lead.requirements or {}).get("service") or ""),
            "scope": str((lead.requirements or {}).get("scope") or "")[:300],
            "documents": _documents_for(lead.title, documents, len(leads) == 1),
            "notes": project_notes(lead.requirements or {}),
            "feedback": [f for f in feedback if _same(lead.title, str(f.get("project") or ""))][
                -3:
            ],
        }
        try:
            async with session.begin_nested():
                path = await journey(lead.id, scope, session)
            steps = path["steps"]
            item |= {
                "steps_done": sum(1 for s in steps if s["done"]),
                "steps_total": len(steps),
                # Where it really is: the last step done ("Next" says what comes after).
                "current_step": next(
                    (s["label"] for s in reversed(steps) if s["done"]), steps[0]["label"]
                ),
                "next": path["next"],
                "meeting": path.get("meeting"),
                # Every step with its date: the "what's been done" view.
                "steps": [
                    {k: s[k] for k in ("key", "label", "at", "done", "detail")} for s in steps
                ],
            }
        except (BusinessRuleViolation, DBAPIError):
            pass  # Without the deal journey (pi off, older database) the lead still shows.
        projects.append(item)
    return projects


REFRESH_PER_VIEW = 3


async def _refresh(request: Request, session: Any, conversations: list[PiConversation]) -> None:
    """Re-analyse out-of-date chats (best effort: a failure keeps the saved analysis)."""
    from app.modules.pi.models import WhatsAppConnection
    from app.modules.pi_customer import service as portal
    from app.modules.tenants.models import Tenant

    state = request.app.state
    done = 0
    for conversation in conversations:
        if done >= REFRESH_PER_VIEW or conversation.last_message_at is None:
            break
        if portal.report_current(conversation):
            continue
        connection = await session.get(WhatsAppConnection, conversation.connection_id)
        tenant = await session.get(Tenant, conversation.tenant_id)
        if connection is None:
            continue
        done += 1
        try:
            await portal.analyse(
                session,
                state.settings,
                state.http,
                getattr(state, "sessions", None),
                conversation,
                connection,
                tenant.name if tenant else "us",
            )
            await session.refresh(conversation)
        except Exception:  # noqa: BLE001 - the saved analysis is shown instead
            logger.warning("pi_overview_refresh_failed", exc_info=True)
            await session.rollback()
            break  # The rollback expired the loaded rows: the caller reloads them.


@router.get("/{customer_id}/pi-overview")
async def overview(
    customer_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    scope.require("customers.read")
    customer = await WorkspaceRepository(session, Customer, scope).get(customer_id)
    chats = (
        WorkspaceRepository(session, PiConversation, scope)
        .select()
        .where(PiConversation.customer_id == customer_id)
        .order_by(PiConversation.last_message_at.desc().nulls_last())
        .limit(10)
    )
    conversations = list(await session.scalars(chats))
    profile: dict[str, str] = {}
    for conversation in reversed(conversations):  # oldest first, newest facts win
        profile = merge_profile(
            profile, (conversation.service_brief or {}).get("customer_profile") or {}
        )
    if customer.name and not PLACEHOLDER_NAME.search(customer.name):
        profile.setdefault("name", customer.name)
    if customer.company:
        profile.setdefault("business_name", customer.company)
    first: datetime | None = min((c.created_at for c in conversations), default=None)
    last: datetime | None = next((c.last_message_at for c in conversations), None)
    await _refresh(request, session, conversations)
    # Fresh rows: a refresh commits (or rolls back), which expires what was loaded.
    customer = await WorkspaceRepository(session, Customer, scope).get(customer_id)
    conversations = list(await session.scalars(chats))
    issues, links, headline = await _requests(session, conversations)
    projects: list[dict[str, Any]] = []
    if scope.can("sales.read"):
        projects = await _projects(session, scope, customer_id)
    follow_deals(issues, projects)
    return {
        "profile": {
            **profile,
            "phone": customer.phone,
            "email": customer.email,
            "language": next((c.language for c in conversations if c.language), None),
            "first_chat_at": first,
            "last_message_at": last,
            "chats": len(conversations),
            "returning": len(conversations) > 1,
        },
        "projects": projects,
        "issues": issues,
        "links": links,
        "headline": headline,
        "counts": _counts(issues),
    }
