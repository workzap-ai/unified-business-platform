"""WhatsApp templates and ready-made forms (Flows) through Kapso, for the Pi app and Owner OS.

- **Templates:**
  - Listed and created through Kapso's Meta proxy for the connected number's WhatsApp
    Business Account.
  - Only plain text templates without variables or buttons can be sent by campaigns and
    reminders, and the list says which ones.
  - Meta reviews every new template (PENDING until approved).
- **Forms:**
  - Three ready-made designs (customer details, booking request, feedback).
  - Created and published on the connected number with one click.
  - The Flow id is saved in ``whatsapp_config.flows``, so the owner never opens WhatsApp
    Manager.
  - Replies still need the signed token checked in ``flows.py``.
"""

from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi.models import PiSettings, WhatsAppConnection
from app.modules.pi.service import require_pi
from app.modules.pi_saas.kapso import Kapso
from app.shared.errors import BusinessRuleViolation
from app.shared.workspace_repository import WorkspaceRepository

Purpose = Literal["lead", "booking", "feedback"]

FORMS: dict[str, dict[str, Any]] = {
    "lead": {
        "name": "Customer details",
        "cta": "Share details",
        "title": "Your details",
        "fields": [
            ("name", "Your name", "text", True),
            ("need", "What do you need?", "text", True),
            ("budget", "Budget (optional)", "text", False),
            ("city", "City", "text", False),
        ],
    },
    "booking": {
        "name": "Booking request",
        "cta": "Request a time",
        "title": "Book a time",
        "fields": [
            ("service", "Which service?", "text", True),
            ("preferred_day", "Preferred day", "text", True),
            ("preferred_time", "Preferred time", "text", False),
            ("notes", "Anything else?", "text", False),
        ],
    },
    "feedback": {
        "name": "Feedback",
        "cta": "Give feedback",
        "title": "How did we do?",
        "fields": [
            ("rating", "Rating from 1 to 5", "number", True),
            ("comment", "Tell us more (optional)", "text", False),
        ],
    },
}


def flow_json(purpose: str) -> dict[str, Any]:
    """A single-screen WhatsApp Flow (Flow JSON 6.x) whose answers come back as a reply."""
    form = FORMS[purpose]
    inputs = [
        {
            "type": "TextInput",
            "name": key,
            "label": label,
            "input-type": kind,
            "required": required,
        }
        for key, label, kind, required in form["fields"]
    ]
    payload = {key: f"${{form.{key}}}" for key, *_ in form["fields"]}
    return {
        "version": "6.3",
        "screens": [
            {
                "id": "DETAILS",
                "title": form["title"],
                "terminal": True,
                "success": True,
                "layout": {
                    "type": "SingleColumnLayout",
                    "children": [
                        {
                            "type": "Form",
                            "name": "form",
                            "children": [
                                *inputs,
                                {
                                    "type": "Footer",
                                    "label": "Send",
                                    "on-click-action": {"name": "complete", "payload": payload},
                                },
                            ],
                        }
                    ],
                },
            }
        ],
    }


class TemplateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(pattern=r"^[a-z0-9_]{1,512}$")
    language: str = Field(pattern=r"^[a-z]{2,3}(_[A-Z]{2})?$")
    category: Literal["MARKETING", "UTILITY"]
    body: str = Field(min_length=1, max_length=1024)


async def _number(session: Any, scope: Any) -> WhatsAppConnection:
    row: WhatsAppConnection | None = await session.scalar(
        WorkspaceRepository(session, WhatsAppConnection, scope)
        .select()
        .where(WhatsAppConnection.status == "active")
        .limit(1)
    )
    if row is None:
        raise BusinessRuleViolation("WHATSAPP_NOT_CONNECTED", "Connect a WhatsApp number first")
    if row.provider != "kapso":
        raise BusinessRuleViolation(
            "KAPSO_ONLY",
            "Templates and forms are managed here for Kapso numbers. For a Meta number, use "
            "WhatsApp Manager.",
        )
    return row


def build() -> APIRouter:
    router = APIRouter(prefix="/pi/whatsapp", tags=["pi-whatsapp-tools"])

    @router.get("/templates")
    async def templates(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
        await require_pi(session, scope, "pi.read")
        try:
            number = await _number(session, scope)
        except BusinessRuleViolation:
            # Nothing to list until a number is connected; the page explains that.
            return {"templates": [], "number": None, "connected": False}
        items = await Kapso(request.app.state.settings, request.app.state.http).list_templates(
            number.business_account_id or ""
        )
        return {"templates": items, "number": number.display_phone_number, "connected": True}

    @router.post("/templates", status_code=201)
    async def create_template(
        data: TemplateInput, request: Request, scope: Scope, session: Session
    ) -> dict[str, Any]:
        await require_pi(session, scope, "pi.settings.manage")
        number = await _number(session, scope)
        if "{{" in data.body:
            raise BusinessRuleViolation(
                "INVALID_TEMPLATE", "Variables aren't supported yet; write the full text"
            )
        state = await Kapso(request.app.state.settings, request.app.state.http).create_template(
            number.business_account_id or "", data.name, data.language, data.category, data.body
        )
        await record(
            session,
            "pi.whatsapp_template_created",
            scope=scope,
            entity_type="whatsapp_connection",
            entity_id=number.id,
            details={"name": data.name, "language": data.language, "category": data.category},
        )
        await session.commit()
        return {"name": data.name, "status": state}

    @router.get("/forms")
    async def forms(scope: Scope, session: Session) -> dict[str, Any]:
        await require_pi(session, scope, "pi.read")
        policy = await session.scalar(
            WorkspaceRepository(session, PiSettings, scope).select().limit(1)
        )
        current = (policy.whatsapp_config.get("flows") if policy else None) or {}
        return {
            "forms": [
                {
                    "purpose": purpose,
                    "name": form["name"],
                    "fields": [label for _, label, *_ in form["fields"]],
                    "flow_id": (current.get(purpose) or {}).get("flow_id"),
                }
                for purpose, form in FORMS.items()
            ]
        }

    @router.post("/forms/{purpose}/create")
    async def create_form(
        purpose: Purpose, request: Request, scope: Scope, session: Session
    ) -> dict[str, Any]:
        """Create and publish a ready-made form on the connected number, then save it."""
        await require_pi(session, scope, "pi.settings.manage")
        from app.modules.pi.configuration import settings_row

        number = await _number(session, scope)
        form = FORMS[purpose]
        flow_id = await Kapso(request.app.state.settings, request.app.state.http).create_flow(
            number.phone_number_id, f"Pi {form['name']}", flow_json(purpose)
        )
        policy = await settings_row(session, scope)
        flows = dict(policy.whatsapp_config.get("flows") or {})
        flows[purpose] = {"flow_id": flow_id, "cta": form["cta"], "screen": "DETAILS"}
        policy.whatsapp_config = {**policy.whatsapp_config, "flows": flows}
        await record(
            session,
            "pi.whatsapp_form_created",
            scope=scope,
            entity_type="whatsapp_connection",
            entity_id=number.id,
            details={"purpose": purpose, "flow_id": flow_id},
        )
        await session.commit()
        return {"purpose": purpose, "flow_id": flow_id}

    return router


router = build()
