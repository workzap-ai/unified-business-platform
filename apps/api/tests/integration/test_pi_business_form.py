"""Business details: pi asks in the chat; on the second unanswered ask it sends the
Business details form once, and the answers fill the customer's profile and record."""

from uuid import UUID

import pytest
from sqlalchemy import select
from test_pi_deals import _customer_in_chat
from test_pi_pipeline import pi_workspace

from app.modules.customers.models import Customer
from app.modules.pi.business_form import after_turn
from app.modules.pi.configuration import settings_row
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi.service_conversation import without_filler
from app.modules.pi_saas import flows
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration
ASK = "Noted. What's your business called, and what does it do?"


def _inbound(pi, conversation, body: str, media: dict | None = None) -> PiMessage:
    return PiMessage(
        tenant_id=UUID(pi.tenant_id),
        environment_id=UUID(pi.environment_id),
        conversation_id=conversation.id,
        direction="inbound",
        sender_type="customer",
        message_type="interactive" if media else "text",
        body=body,
        status="processed",
        media=media or {},
    )


async def test_second_unanswered_ask_sends_the_form_and_answers_fill_the_profile(
    api, business_db, monkeypatch
):
    import app.core.config as config

    settings = api._transport.app.state.settings
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    pi = await pi_workspace(api, business_db, business_type="service_business")
    customer_id, conversation = await _customer_in_chat(pi)
    from app.modules.pi_saas.deals import system_scope_for

    scope = await system_scope_for(pi.db, UUID(pi.tenant_id), UUID(pi.environment_id))
    policy = await settings_row(pi.db, scope)
    policy.whatsapp_config = {
        **policy.whatsapp_config,
        "flows": {"business": {"flow_id": "1234567", "cta": "Share details", "screen": "DETAILS"}},
    }
    row = await pi.db.get(PiConversation, conversation.id)
    for n in range(3):
        message = _inbound(pi, conversation, f"Need an ERP {n}")
        pi.db.add(message)
        await pi.db.flush()
        await after_turn(pi.db, scope, row, message, policy, ASK, "calm")
    await pi.db.commit()
    forms = list(
        await pi.db.scalars(
            select(PiMessage).where(
                PiMessage.conversation_id == conversation.id,
                PiMessage.idempotency_key.like("pi:%:form:business"),
            )
        )
    )
    assert len(forms) == 1  # only on the second ask, and only once
    assert forms[0].media["flow"]["purpose"] == "business"
    assert row.service_brief["business_asks"] == 2

    token = flows.token(settings, conversation.id, "business")
    reply = _inbound(
        pi,
        conversation,
        "Form reply",
        {
            "form_response": {
                "flow_token": token,
                "name": "Mukarram Hazari",
                "business_name": "Hazari Impex",
                "business_type": "FMCG distribution",
                "city": "Karachi",
            }
        },
    )
    pi.db.add(reply)
    await pi.db.flush()
    assert await flows.note_form_reply(pi.db, settings, scope, reply)
    await pi.db.commit()
    await pi.db.refresh(row)
    profile = row.service_brief["customer_profile"]
    assert profile["business_name"] == "Hazari Impex" and profile["location"] == "Karachi"
    customer = await pi.db.get(Customer, UUID(customer_id))
    await pi.db.refresh(customer)
    assert customer.company == "Hazari Impex"
    await pi.close()


async def test_no_form_for_an_upset_customer_and_admins_are_told_when_missing(api, business_db):
    from app.modules.notifications.models import Notification

    pi = await pi_workspace(api, business_db, business_type="service_business")
    _, conversation = await _customer_in_chat(pi)
    scope = WorkspaceScope.system(
        UUID(pi.tenant_id), UUID(pi.environment_id), frozenset({"pi.read"}), "PI"
    )
    policy = await settings_row(pi.db, scope)
    row = await pi.db.get(PiConversation, conversation.id)
    for _ in range(2):
        message = _inbound(pi, conversation, "where is my link")
        pi.db.add(message)
        await pi.db.flush()
        await after_turn(pi.db, scope, row, message, policy, ASK, "frustrated")
    await pi.db.commit()
    assert "business_form_sent" not in row.service_brief
    message = _inbound(pi, conversation, "ok")
    pi.db.add(message)
    await pi.db.flush()
    await after_turn(pi.db, scope, row, message, policy, ASK, "calm")  # no form set up
    await pi.db.commit()
    told = await pi.db.scalar(
        select(Notification).where(Notification.kind == "pi.business_form_missing")
    )
    assert told is not None
    await pi.close()


def test_generic_closing_lines_are_dropped():
    assert (
        without_filler(
            "Your link will be shared here. If you have any other questions, feel free to ask."
        )
        == "Your link will be shared here."
    )
    assert without_filler("Theek hai. Agar aapko aur koi madad chahiye, to zaroor batayein.") == (
        "Theek hai."
    )
    assert without_filler("Feel free to ask.") == "Feel free to ask."  # nothing else to send
