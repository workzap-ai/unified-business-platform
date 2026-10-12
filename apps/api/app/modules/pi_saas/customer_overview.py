"""The whole picture of one customer for the team (Owner OS and the pi app).

    GET /customers/{id}/pi-overview

- profile: who they are. Their record, plus what they told pi in any chat (business,
  what it does, where, their role), the language they use, and when they first came.
- projects: each deal with its journey (steps done of all) and the next step.
- requests + links: what pi understood they need, and how those requests connect (the
  Problem Map), the same data the customer sees on their own dashboard.
- counts: every number counts requests (waiting on them / on us / done / paused).

Read-only and cheap: it uses saved records and pi's cached analysis, never an AI call.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy.exc import DBAPIError

from app.modules.access.dependencies import Scope, Session
from app.modules.customers.models import Customer
from app.modules.pi.models import PiConversation
from app.modules.pi.service_conversation import PLACEHOLDER_NAME, merge_profile
from app.modules.sales.models import SalesLead
from app.shared.errors import BusinessRuleViolation
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/customers", tags=["customer-overview"])
LINK_FIELDS = ("a", "b", "a_title", "b_title", "type", "reason", "benefit", "confidence")


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
    return issues, links, headline


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
        }
        try:
            async with session.begin_nested():
                path = await journey(lead.id, scope, session)
            steps = path["steps"]
            item |= {
                "steps_done": sum(1 for s in steps if s["done"]),
                "steps_total": len(steps),
                "current_step": next((s["label"] for s in steps if not s["done"]), "Paid"),
                "next": path["next"],
                "meeting": path.get("meeting"),
            }
        except (BusinessRuleViolation, DBAPIError):
            pass  # Without the deal journey (pi off, older database) the lead still shows.
        projects.append(item)
    return projects


@router.get("/{customer_id}/pi-overview")
async def overview(customer_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    scope.require("customers.read")
    customer = await WorkspaceRepository(session, Customer, scope).get(customer_id)
    conversations = list(
        await session.scalars(
            WorkspaceRepository(session, PiConversation, scope)
            .select()
            .where(PiConversation.customer_id == customer_id)
            .order_by(PiConversation.last_message_at.desc().nulls_last())
            .limit(10)
        )
    )
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
    issues, links, headline = await _requests(session, conversations)
    projects: list[dict[str, Any]] = []
    if scope.can("sales.read"):
        projects = await _projects(session, scope, customer_id)
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
