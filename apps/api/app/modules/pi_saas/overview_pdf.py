"""A customer's picture from pi as a PDF to share with the team ("Share with my team").

    GET /customers/{id}/pi-overview.pdf

The same data as the pi overview (who they are, projects, requests, connections), as a
dated snapshot: plain text, one or more A4 pages.
"""

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote as quote_name
from uuid import UUID

from fastapi import APIRouter, Request, Response

from app.modules.access.dependencies import Scope, Session
from app.modules.customers.models import Customer
from app.modules.pi_saas.customer_overview import overview
from app.shared.pdf import MARGIN, WIDTH, Document, wrap
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/customers", tags=["customer-overview"])

INK = (0.1, 0.1, 0.12)
MUTED = (0.42, 0.44, 0.48)
BRAND = (0.05, 0.37, 0.31)
BOTTOM = 770.0
LANGUAGE = {"en": "English", "roman_ur": "Roman Urdu", "ar": "Arabic"}
LEAD_STAGE = {
    "new": "New",
    "qualified": "Brief confirmed",
    "proposal": "Proposal",
    "won": "Won",
    "lost": "Lost",
}
TURN = {"client": "Waiting on them", "team": "Waiting on us", "pi": "pi is on it", "none": ""}


class _Writer:
    """Flowing text down the page; a new page when it runs out."""

    def __init__(self, doc: Document) -> None:
        self.doc, self.y = doc, 0.0

    def room(self, need: float) -> None:
        if self.y + need > BOTTOM:
            self.doc.new_page()
            self.y = MARGIN + 12

    def heading(self, text: str) -> None:
        self.room(40)
        self.y += 10
        self.doc.text(MARGIN, self.y, text, 12, True, BRAND)
        self.y += 6
        self.doc.line(MARGIN, self.y, WIDTH - MARGIN, self.y)
        self.y += 18

    def para(
        self, text: str, size: float = 10, bold: bool = False, color: Any = INK, indent: float = 0
    ) -> None:
        for line in wrap(text, size, WIDTH - 2 * MARGIN - indent, bold)[:8]:
            self.room(size + 4)
            self.doc.text(MARGIN + indent, self.y, line, size, bold, color)
            self.y += size + 4

    def fact(self, label: str, value: str) -> None:
        lines = wrap(value, 10, WIDTH - 2 * MARGIN - 110)[:4]
        self.room(14 * len(lines))
        self.doc.text(MARGIN, self.y, label, 9, False, MUTED)
        for line in lines:
            self.doc.text(MARGIN + 110, self.y, line, 10)
            self.y += 14


def _day(value: Any) -> str:
    if isinstance(value, datetime):
        return f"{value:%d %b %Y}"
    return str(value or "")


def render(customer: str, data: dict[str, Any]) -> bytes:
    doc = Document(title=f"{customer} - pi picture")
    out = _Writer(doc)
    right = WIDTH - MARGIN
    doc.box(0, 0, WIDTH, 84, BRAND)
    doc.text(MARGIN, 42, f"{customer} — picture from pi", 18, True, (1, 1, 1))
    doc.text(MARGIN, 62, f"{datetime.now(UTC):%d %b %Y}", 10, False, (0.85, 0.94, 0.9))
    out.y = 112.0
    if data.get("headline"):
        out.para(str(data["headline"]), 11, True)
        out.y += 4

    p = data.get("profile") or {}
    out.heading("Who they are")
    facts = [
        ("Name", p.get("name")),
        ("Business", p.get("business_name")),
        ("What they do", p.get("business_type")),
        ("Location", p.get("location")),
        ("Their role", p.get("role")),
        ("Phone", p.get("phone")),
        ("Email", p.get("email")),
        ("Language", LANGUAGE.get(p.get("language") or "", p.get("language"))),
        ("First chat", _day(p.get("first_chat_at"))),
        ("Last message", _day(p.get("last_message_at"))),
        ("Chats with pi", str(p.get("chats") or 0)),
    ]
    for label, value in facts:
        if value:
            out.fact(label, str(value))

    projects = data.get("projects") or []
    if projects:
        out.heading("Projects")
        for project in projects:
            out.room(60)
            out.para(str(project.get("title") or "Project"), 11, True)
            stage = LEAD_STAGE.get(project.get("stage") or "", project.get("stage") or "")
            out.fact("Stage", stage)
            if project.get("steps_total"):
                out.fact("Steps", f"{project.get('steps_done', 0)} of {project['steps_total']}")
            if project.get("current_step"):
                out.fact("Current step", str(project["current_step"]))
            following = project.get("next") or {}
            if isinstance(following, dict) and following.get("title"):
                out.fact("Next step", str(following["title"]))
            out.y += 8

    issues = data.get("issues") or []
    if issues:
        out.heading("Requests")
        for issue in issues:
            out.room(50)
            out.para(str(issue.get("title") or "Request"), 11, True)
            problem = " ".join(
                str(issue.get(k) or "").strip() for k in ("summary", "root_cause")
            ).strip()
            if problem:
                out.fact("Problem", problem)
            if issue.get("next_step"):
                out.fact("Next", str(issue["next_step"]))
            turn = TURN.get(str(issue.get("ball_with") or ""), "")
            if turn:
                out.fact("Whose turn", turn)
            out.y += 8

    links = data.get("links") or []
    if links:
        out.heading("Connections")
        for link in links:
            # Helvetica (WinAnsi) has no two-way arrow.
            line = f"{link.get('a_title') or '?'} <-> {link.get('b_title') or '?'}"
            if link.get("reason"):
                line += f": {link['reason']}"
            out.para(line)
            out.y += 2

    doc.line(MARGIN, 800, right, 800)
    doc.text(MARGIN, 814, "For the team: a snapshot of what pi knows today.", 9, False, MUTED)
    return doc.render()


@router.get("/{customer_id}/pi-overview.pdf")
async def overview_pdf(
    customer_id: UUID, request: Request, scope: Scope, session: Session
) -> Response:
    scope.require("customers.read")
    customer = await WorkspaceRepository(session, Customer, scope).get(customer_id)
    data = await overview(customer_id, request, scope, session)
    name = customer.name or "Customer"
    return Response(
        render(name, data),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{quote_name(f'{name} - pi picture.pdf')}"
            ),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
