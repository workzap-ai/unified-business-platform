"""Business details: pi asks in the chat first, then sends a form.

pi asks a new customer for their name and business in the conversation, at a calm
moment. If it has asked once and they still haven't said, the next time pi asks it also
sends the "Business details" WhatsApp form (name, business, what it does, city, role),
once per chat and never to an upset customer. The answers fill the customer's profile
(and the Customer record's name and company), exactly like telling pi in the chat.
"""

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi.models import PiConversation, PiMessage, PiSettings
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

# pi's reply asks who they are / what their business is.
ASKS_BUSINESS = re.compile(
    r"\b(?:business|company|brand|shop|store|firm|kaarobaar|karobar|dukaan|dukan)\b"
    r"[^?]{0,80}\?|\bwhat (?:do|does) (?:you|your \w+) (?:do|sell)\b|\bkya (?:kaam )?karte\b",
    re.IGNORECASE,
)
FORM_BODY = {
    "en": "To save typing, you can fill in your business details here (30 seconds).",
    "roman_ur": "Asaani ke liye apni business details yahan bhar dein (sirf 30 second).",
}
# Form field -> customer profile field.
PROFILE_FIELDS = {
    "name": "name",
    "business_name": "business_name",
    "business_type": "business_type",
    "city": "location",
    "role": "role",
}


def knows_business(profile: dict[str, Any]) -> bool:
    return bool(profile.get("business_name") or profile.get("business_type"))


async def after_turn(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    message: PiMessage,
    policy: PiSettings,
    reply: str,
    mood: str,
) -> None:
    """Count pi's asks for the business; on the second unanswered ask, send the form."""
    from app.modules.pi import flow as pi_flow

    if pi_flow.brain_mode(policy.response_rules):
        return  # "No forms. Just chat." (spec 0.2 P2, R-CONV): brain mode never sends the form

    from app.core.config import get_settings
    from app.modules.notifications.service import notify
    from app.modules.pi_saas import flows

    brief = dict(conversation.service_brief or {})
    config = policy.whatsapp_config or {}
    if (
        config.get("business_form", True) is False
        or knows_business(brief.get("customer_profile") or {})
        or brief.get("business_form_sent")
        or (brief.get("forms") or {}).get("business")
        or not ASKS_BUSINESS.search(reply)
    ):
        return
    asks = int(brief.get("business_asks") or 0) + 1
    brief["business_asks"] = asks
    conversation.service_brief = brief
    if asks < 2 or mood in ("frustrated", "urgent"):
        return
    flow = (config.get("flows") or {}).get("business")
    if not flow:
        await notify(
            session,
            scope,
            "pi.business_form_missing",
            "Let pi send a Business details form",
            "Customers don't always answer pi's question about their business. Create the "
            "ready-made Business details form (one click) and pi sends it when needed.",
            link="/pi/settings/whatsapp-configuration",
            permission="pi.settings.manage",
            dedupe_key=f"pi-business-form:{scope.tenant_id}:{scope.environment_id}",
        )
        return
    signed = flows.token(get_settings(), conversation.id, "business")
    if signed is None:
        return
    repo = WorkspaceRepository(session, PiMessage, scope)
    key = f"pi:{message.id}:form:business"  # sent by the runtime with this turn's reply
    if await repo.find(PiMessage.idempotency_key == key) is None:
        language = "roman_ur" if conversation.language == "roman_ur" else "en"
        await repo.add(
            repo.new(
                conversation_id=conversation.id,
                direction="outbound",
                sender_type="ai",
                agent_key="requirement",
                message_type="interactive",
                body=str(flow.get("body") or FORM_BODY[language])[:1024],
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
                        "purpose": "business",
                    }
                },
            )
        )
    brief["business_form_sent"] = datetime.now(UTC).isoformat()
    conversation.service_brief = brief


async def save_answers(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    fields: dict[str, str],
) -> None:
    """The form's answers become the customer's profile (their own words)."""
    from app.modules.pi.service_conversation import merge_profile, remember_customer

    answers = {PROFILE_FIELDS[k]: v for k, v in fields.items() if k in PROFILE_FIELDS and v}
    brief = dict(conversation.service_brief or {})
    brief["customer_profile"] = merge_profile(brief.get("customer_profile"), answers)
    conversation.service_brief = brief
    await remember_customer(session, scope, conversation, brief["customer_profile"])
