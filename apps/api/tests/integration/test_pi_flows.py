"""WhatsApp Flows: signed forms sent by an opt-in tool, and replies accepted only with a
token for the same conversation."""

import json
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pi_saas_support import FakeProvider, configure
from pydantic import SecretStr
from sqlalchemy import func, select
from test_pi_connectors import conversation_with_run
from test_pi_pipeline import pi_workspace
from test_pi_saas import _kapso, _message_event, _ready_business, _run_jobs

from app.modules.audit.models import AuditEvent
from app.modules.pi.models import PiConversation, PiMessage, PiSettings
from app.modules.pi.runtime import send_pi_message
from app.modules.pi.tools.registry import ToolRegistry
from app.modules.pi_saas import flows

pytestmark = pytest.mark.integration

LEAD_FLOW = {"flow_id": "1234567890123", "cta": "Share details", "screen": "DETAILS"}


def _settings(app):
    settings = app.state.settings
    if settings.secrets_encryption_key is None:
        settings.secrets_encryption_key = SecretStr(Fernet.generate_key().decode())
    return settings


def test_tokens_configs_and_replies_are_strict(api):
    settings = _settings(api._transport.app)  # type: ignore[attr-defined]
    conversation = uuid4()
    signed = flows.token(settings, conversation, "lead")
    assert flows.verify(settings, signed, conversation) == "lead"
    assert flows.verify(settings, signed, uuid4()) is None  # another conversation
    assert (
        flows.verify(settings, signed[:-1] + ("0" if signed[-1] != "0" else "1"), conversation)
        is None
    )
    assert flows.valid_config({"lead": LEAD_FLOW})
    assert not flows.valid_config({"lead": {**LEAD_FLOW, "cta": "x" * 21}})
    assert not flows.valid_config({"survey": LEAD_FLOW})
    reply = {
        "type": "nfm_reply",
        "nfm_reply": {"response_json": json.dumps({"flow_token": signed, "name": "Sana"})},
    }
    kind, text, form = flows.interactive_reply({"interactive": reply})
    assert kind == "interactive" and text == "Form reply. name: Sana" and form["name"] == "Sana"
    tapped = {"type": "button_reply", "button_reply": {"id": "b1", "title": "Yes, book it"}}
    assert flows.interactive_reply({"interactive": tapped}) == ("text", "Yes, book it", None)
    broken = {"type": "nfm_reply", "nfm_reply": {"response_json": "{not json"}}
    assert flows.interactive_reply({"interactive": broken})[0] == "other"
    many = {f"f{i}": "v" * 900 for i in range(50)}
    cleaned = flows.clean_fields(many)
    assert len(cleaned) == flows.MAX_FIELDS and all(len(v) <= 500 for v in cleaned.values())


async def test_send_form_tool_queues_a_signed_flow(api, business_db):
    pi = await pi_workspace(api, business_db)
    settings = _settings(pi.app)
    try:
        conversation, run = await conversation_with_run(pi, "wamid.form-1")
        policy = await business_db.scalar(
            select(PiSettings).where(PiSettings.tenant_id == conversation.tenant_id)
        )
        policy.whatsapp_config = {**policy.whatsapp_config, "flows": {"lead": LEAD_FLOW}}
        enabled = await api.put("/api/v1/pi/tools/send_form/enabled", json={"enabled": True})
        assert enabled.status_code == 200, enabled.text
        registry = ToolRegistry(business_db, (settings, pi.http))
        missing = await registry.execute(
            pi.scope(), conversation, "send_form", {"purpose": "feedback"}, run=run
        )
        assert missing.error_code == "FORM_NOT_SET_UP"
        result = await registry.execute(
            pi.scope(), conversation, "send_form", {"purpose": "lead"}, run=run
        )
        assert result.ok, result
        message = await business_db.scalar(
            select(PiMessage).where(PiMessage.idempotency_key.like("pi:%:form:lead"))
        )
        form = message.media["flow"]
        assert flows.verify(settings, form["token"], conversation.id) == "lead"
        await send_pi_message(pi.ctx, str(message.id))
        await business_db.refresh(message)
        assert message.status == "sent"
        sent = pi.sent[-1]
        assert sent["type"] == "interactive" and sent["interactive"]["type"] == "flow"
        parameters = sent["interactive"]["action"]["parameters"]
        assert parameters["flow_id"] == LEAD_FLOW["flow_id"]
        assert parameters["flow_token"] == form["token"]
        assert parameters["flow_action_payload"] == {"screen": "DETAILS"}
    finally:
        await pi.close()


def _form_event(number: str, sender: str, mid: str, answers: dict) -> dict:
    event = _message_event(number, sender, "", mid)
    event["message"] = {
        "id": mid,
        "timestamp": "1730092800",
        "type": "interactive",
        "from": sender,
        "interactive": {
            "type": "nfm_reply",
            "nfm_reply": {"name": "flow", "body": "Sent", "response_json": json.dumps(answers)},
        },
    }
    return event


async def test_form_replies_need_a_token_for_the_same_conversation(api, business_db):
    app = api._transport.app  # type: ignore[attr-defined]
    provider = FakeProvider()
    provider.queue = configure(app, provider)  # type: ignore[attr-defined]
    settings = _settings(app)
    client, _ = await _ready_business(app, provider, business_db, "Forms", "9999999999")
    await _kapso(
        client,
        "whatsapp.message.received",
        _message_event("9999999999", "923007770001", "Salam", "wamid.f0"),
    )
    await _run_jobs(app, provider, business_db)
    conversation = await business_db.scalar(
        select(PiConversation).where(PiConversation.contact_wa_id == "923007770001")
    )
    good = {"flow_token": flows.token(settings, conversation.id, "lead"), "name": "Sana"}
    await _kapso(
        client,
        "whatsapp.message.received",
        _form_event("9999999999", "923007770001", "wamid.f1", {**good, "city": "Lahore"}),
    )
    forged = {"flow_token": flows.token(settings, uuid4(), "feedback"), "rating": "1"}
    await _kapso(
        client,
        "whatsapp.message.received",
        _form_event("9999999999", "923007770001", "wamid.f2", forged),
    )
    await _run_jobs(app, provider, business_db)
    await business_db.refresh(conversation)
    forms = conversation.service_brief["forms"]
    assert forms["lead"]["fields"] == {"name": "Sana", "city": "Lahore"}
    assert "feedback" not in forms
    stored = await business_db.scalar(
        select(PiMessage).where(PiMessage.provider_message_id == "wamid.f1")
    )
    assert stored.message_type == "interactive" and stored.body.startswith("Form reply.")
    rejected = await business_db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.action == "pi.form_reply_rejected")
    )
    assert rejected == 1
    await client.aclose()
