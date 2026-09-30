"""send_form: send one of the business's published WhatsApp Flows (lead details,
booking request or feedback) to the current customer. Opt-in; session-window only."""

from typing import Literal

from pydantic import Field

from app.modules.pi.models import PiMessage
from app.modules.pi.tools.base import ToolContext, ToolInput, ToolOutput, ToolRefused
from app.shared.workspace_repository import WorkspaceRepository

DEFAULT_BODY = {
    "lead": "Please share a few details so we can help you properly.",
    "booking": "Choose a time that suits you and we'll confirm it.",
    "feedback": "How did we do? It takes less than a minute.",
}


class FormInput(ToolInput):
    purpose: Literal["lead", "booking", "feedback"]
    message: str = Field(default="", max_length=300)


class FormOut(ToolOutput):
    status: Literal["queued"]
    purpose: str


async def send_form(ctx: ToolContext, data: FormInput) -> FormOut:
    from app.modules.pi.configuration import settings_row
    from app.modules.pi_saas import flows

    if ctx.run is None:
        raise ToolRefused("RUN_REQUIRED", "Only available for an inbound message")
    policy = await settings_row(ctx.session, ctx.scope)
    flow = (policy.whatsapp_config.get("flows") or {}).get(data.purpose)
    if not flow:
        raise ToolRefused(
            "FORM_NOT_SET_UP", "The business hasn't connected this WhatsApp form", "error"
        )
    settings = ctx.http[0] if ctx.http else None
    signed = flows.token(settings, ctx.conversation.id, data.purpose) if settings else None
    if signed is None:
        raise ToolRefused("FORMS_NOT_CONFIGURED", "Forms are not available here", "error")
    repo = WorkspaceRepository(ctx.session, PiMessage, ctx.scope)
    key = f"pi:{ctx.run.message_id}:form:{data.purpose}"
    existing = await repo.find(PiMessage.idempotency_key == key)
    if existing is None:
        await repo.add(
            repo.new(
                conversation_id=ctx.conversation.id,
                direction="outbound",
                sender_type="ai",
                agent_key=ctx.agent_key,
                message_type="interactive",
                body=(flow.get("body") or data.message or DEFAULT_BODY[data.purpose])[:1024],
                status="queued",
                idempotency_key=key,
                media={
                    "flow": {
                        "flow": {
                            "flow_id": str(flow["flow_id"]),
                            "cta": str(flow["cta"]),
                            "screen": str(flow["screen"]),
                        },
                        "token": signed,
                        "purpose": data.purpose,
                    }
                },
            )
        )
    return FormOut(status="queued", purpose=data.purpose)
