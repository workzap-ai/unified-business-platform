"""Real database/webhook/worker tests; external AI and WhatsApp are mocked."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select
from test_pi_pipeline import CaptureQueue, pi_workspace
from test_service_lifecycle import create

from app.ai.errors import GatewayUnavailable
from app.ai.manager import LLMManager
from app.modules.notifications.models import Notification
from app.modules.orders.models import Order
from app.modules.pi.followups import sweep_followups
from app.modules.pi.models import PiMessage, PiSettings, WhatsAppConnection
from app.modules.pi.runtime import send_pi_message
from app.modules.pi.service_conversation import Requirements, ServiceTurn
from app.modules.quotes.models import Quote
from app.modules.sales.models import SalesLead

pytestmark = pytest.mark.integration


def turn(**changes):
    data = dict(
        reply="Aapki website ka main maqsad kya hai?",
        language="roman_ur",
        summary="Customer wants a website. Scope and timing need clarification.",
        requirements=Requirements(service="Website"),
        missing=["scope", "target_date"],
        awaiting_customer=True,
        ready_for_team=False,
    )
    data.update(changes)
    return ServiceTurn(**data)


def mock_turns(monkeypatch, *turns):
    replies = iter(turns)
    contexts = []

    async def complete(self, scope, output, **kwargs):
        assert scope is not None and kwargs["purpose"] == "pi_service"
        contexts.append(kwargs["messages"][-1].text())
        value = next(replies)
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(value=value, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    return contexts


async def test_service_discovers_without_prices_and_saves_team_brief(api, business_db, monkeypatch):
    contexts = mock_turns(
        monkeypatch,
        turn(),
        turn(
            reply="Gracias. ¿Tienes contenido o ejemplos de sitios que te gusten?",
            language="es",
            requirements=Requirements(
                service="Website", scope="Online shop", customer_budget="5000 USD"
            ),
            summary=(
                "Customer wants an online shop, with a customer-stated budget of 5000 USD. "
                "Team must price."
            ),
            missing=["existing_assets"],
            ready_for_team=True,
        ),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await create(
        api,
        "catalog/products",
        {
            "name": "Website",
            "offering_type": "service",
            "variants": [{"sku": "WEB", "name": "Standard", "price": "1500.00", "currency": "USD"}],
        },
    )
    await pi.process("Website ki price kya hai?", "svc-one")
    await pi.deliver_all()
    await pi.process("Necesito una tienda online, mi presupuesto es 5000 USD", "svc-two")
    await pi.deliver_all()
    conversation = await pi.conversation()
    assert conversation.language == "es" and "5000 USD" in conversation.summary
    assert conversation.service_brief["requirements"]["scope"] == "Online shop"
    assert conversation.followup_due_at is None  # No permission, no reminder.
    assert "1500" not in contexts[0]  # Catalog prices never enter the prompt.
    assert "main maqsad" in contexts[1] and "Website" in contexts[1]  # Conversation history.
    assert all("1500" not in m.body and "5000" not in m.body for m in await pi.outbound())
    assert (
        await business_db.scalar(
            select(func.count()).select_from(Order).where(Order.tenant_id == conversation.tenant_id)
        )
        == 0
    )
    assert (
        await business_db.scalar(
            select(func.count()).select_from(Quote).where(Quote.tenant_id == conversation.tenant_id)
        )
        == 0
    )
    lead = await business_db.scalar(
        select(SalesLead).where(SalesLead.tenant_id == conversation.tenant_id)
    )
    assert lead.requirements["customer_budget"] == "5000 USD"
    assert (
        await business_db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.kind == "pi.service_brief",
                Notification.tenant_id == conversation.tenant_id,
            )
        )
        == 2
    )
    response = await api.get(f"/api/v1/pi/conversations/{conversation.id}/context")
    assert response.json()["service_brief"]["ready_for_team"] is True
    await pi.close()


@pytest.mark.parametrize("reply", ["The price is $500", "It costs 5000 PKR", "قیمت ۵۰۰۰ ہے"])
async def test_service_price_output_is_never_sent(api, business_db, monkeypatch, reply):
    mock_turns(monkeypatch, turn(reply=reply))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("Website price?", "bad-price")
    assert (await pi.conversation()).mode == "human"
    assert all(reply != m.body for m in await pi.outbound())
    await pi.close()


async def reminder_workspace(api, business_db, monkeypatch):
    mock_turns(
        monkeypatch,
        turn(
            consent="granted",
            consent_evidence="Yes, remind me",
            language="en",
            reply="What features should the website include?",
        ),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("Yes, remind me", "consented")
    await pi.deliver_all()
    conversation = await pi.conversation()
    assert (
        timedelta(days=6, hours=23)
        < conversation.followup_due_at - datetime.now(UTC)
        <= timedelta(days=7)
    )
    policy = await business_db.scalar(
        select(PiSettings).where(PiSettings.tenant_id == conversation.tenant_id)
    )
    policy.whatsapp_config = {
        **policy.whatsapp_config,
        "reminder_templates": {"en": {"name": "service_followup", "language": "en_US"}},
    }
    connection = await business_db.scalar(
        select(WhatsAppConnection).where(WhatsAppConnection.tenant_id == conversation.tenant_id)
    )
    connection.business_account_id = "987654321"
    conversation.followup_due_at = datetime.now(UTC) - timedelta(seconds=1)
    conversation.last_inbound_at = datetime.now(UTC) - timedelta(days=8)
    pi.ctx["queue"] = CaptureQueue()
    await business_db.commit()
    return pi, conversation


async def test_weekly_reminder_uses_approved_template_once(api, business_db, monkeypatch):
    pi, conversation = await reminder_workspace(api, business_db, monkeypatch)
    await sweep_followups(pi.ctx)
    await sweep_followups(pi.ctx)
    reminders = [m for m in await pi.outbound() if m.media.get("reminder")]
    assert len(reminders) == 1 and len(pi.ctx["queue"].jobs) == 1
    calls = []

    def provider(request):
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "name": "service_followup",
                            "language": "en_US",
                            "status": "APPROVED",
                            "components": [
                                {"type": "BODY", "text": "Would you like to continue your enquiry?"}
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"messages": [{"id": "reminder-sent"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        await send_pi_message({**pi.ctx, "http": http}, str(reminders[0].id))
        await send_pi_message({**pi.ctx, "http": http}, str(reminders[0].id))
    assert reminders[0].status == "sent" and len(calls) == 2
    assert b'"type":"template"' in calls[-1].content
    assert (
        conversation.service_brief["reminded_source_id"]
        == conversation.service_brief["source_message_id"]
    )
    assert conversation.followup_due_at is None
    await pi.close()


@pytest.mark.parametrize("cancel", ["reply", "takeover", "opt_out", "disabled", "closed"])
async def test_queued_reminder_rechecks_cancellation(api, business_db, monkeypatch, cancel):
    pi, conversation = await reminder_workspace(api, business_db, monkeypatch)
    await sweep_followups(pi.ctx)
    reminder = next(m for m in await pi.outbound() if m.media.get("reminder"))
    if cancel == "reply":
        conversation.last_inbound_at = datetime.now(UTC)
    elif cancel == "takeover":
        conversation.mode = "human"
    elif cancel == "opt_out":
        conversation.service_brief = {**conversation.service_brief, "reminder_consent": "declined"}
    elif cancel == "closed":
        conversation.status = "closed"
    else:
        policy = await business_db.scalar(
            select(PiSettings).where(PiSettings.tenant_id == conversation.tenant_id)
        )
        policy.auto_reply_enabled = False
    await business_db.commit()
    before = len(pi.sent)
    await send_pi_message(pi.ctx, str(reminder.id))
    assert reminder.status == "skipped" and len(pi.sent) == before
    await pi.close()


async def test_missing_template_notifies_team_without_sending(api, business_db, monkeypatch):
    pi, conversation = await reminder_workspace(api, business_db, monkeypatch)
    policy = await business_db.scalar(
        select(PiSettings).where(PiSettings.tenant_id == conversation.tenant_id)
    )
    policy.whatsapp_config = {**policy.whatsapp_config, "reminder_templates": {}}
    await business_db.commit()
    await sweep_followups(pi.ctx)
    await sweep_followups(pi.ctx)
    assert len(await pi.outbound()) == 1
    assert (
        await business_db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.kind == "pi.followup_blocked",
                Notification.tenant_id == conversation.tenant_id,
            )
        )
        == 1
    )
    assert conversation.followup_due_at is not None
    await pi.close()


async def test_invented_consent_is_ignored(api, business_db, monkeypatch):
    mock_turns(monkeypatch, turn(consent="granted", consent_evidence="yes"))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("Website chahiye", "no-consent")
    await pi.deliver_all()
    conversation = await pi.conversation()
    assert conversation.service_brief["reminder_consent"] == "unknown"
    assert conversation.followup_due_at is None
    await pi.close()


async def test_provider_failure_does_not_invent_a_reply(api, business_db, monkeypatch):
    mock_turns(monkeypatch, GatewayUnavailable())
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("Website chahiye", "provider-down")
    assert (await pi.conversation()).mode == "human"
    assert (await api.get("/api/v1/pi/handoffs")).json()[0]["reason"] == "provider_failure"
    await pi.close()


@pytest.mark.parametrize(
    "kind,mime,content",
    [
        ("audio", "audio/ogg", b"OggS" + b"\x00" * 32),
        ("image", "image/png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32),
        ("video", "video/mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32),
    ],
)
async def test_media_reaches_service_discovery_with_caption(
    api, business_db, monkeypatch, kind, mime, content
):
    contexts = mock_turns(monkeypatch, turn())
    observed = []

    async def transcribe(self, scope, data, media_type, **kwargs):
        assert scope is not None and data == content and media_type == mime
        observed.append("audio")
        return SimpleNamespace(text="Website mein booking chahiye")

    async def vision(self, scope, prompt, images, **kwargs):
        assert scope is not None and images == [(content, mime)]
        observed.append("image")
        return SimpleNamespace(text="Website mein booking chahiye")

    async def video(self, scope, **kwargs):
        assert scope is not None and kwargs["alias"] == "video"
        observed.append("video")
        return SimpleNamespace(text="Website mein booking chahiye")

    monkeypatch.setattr(LLMManager, "transcribe", transcribe)
    monkeypatch.setattr(LLMManager, "vision", vision)
    monkeypatch.setattr(LLMManager, "complete", video)
    pi = await pi_workspace(api, business_db, business_type="service_business")

    def provider(request):
        if request.url.path.endswith("/7654321"):
            return httpx.Response(
                200,
                json={
                    "url": "https://lookaside.fbsbx.com/attachment",
                    "mime_type": mime,
                    "file_size": len(content),
                },
            )
        return httpx.Response(200, content=content)

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        pi.ctx["http"] = http
        await pi.process("Meri reference dekhein", f"media-{kind}", kind=kind, media_id="7654321")
    assert observed == [kind]
    assert "Meri reference dekhein" in contexts[0] and "booking chahiye" in contexts[0]
    inbound = await business_db.scalar(
        select(PiMessage).where(
            PiMessage.tenant_id == pi.identity["tenant"]["id"], PiMessage.direction == "inbound"
        )
    )
    assert inbound.message_type == kind and inbound.media["provider_media_id"] == "7654321"
    assert "booking" in inbound.media["transcript" if kind == "audio" else "description"]
    assert (await pi.conversation()).mode == "ai"
    await pi.close()


async def test_service_handoff_delivers_acknowledgement(api, business_db, monkeypatch):
    mock_turns(
        monkeypatch,
        turn(
            reply="Our team can review the scope with you.",
            request_human=True,
            ready_for_team=True,
            awaiting_customer=False,
        ),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("Necesito hablar sobre un proyecto especial", "service-human")
    await pi.deliver_all()
    assert (await pi.conversation()).mode == "human"
    replies = await pi.outbound()
    assert len(replies) == 1 and replies[0].status == "sent"
    assert "review the scope" in replies[0].body
    await pi.close()


async def test_followup_does_not_run_before_due(api, business_db, monkeypatch):
    pi, conversation = await reminder_workspace(api, business_db, monkeypatch)
    conversation.followup_due_at = datetime.now(UTC) + timedelta(days=1)
    await business_db.commit()
    await sweep_followups(pi.ctx)
    assert len(await pi.outbound()) == 1
    await pi.close()


async def test_new_reply_cancels_old_queued_service_reply(api, business_db, monkeypatch):
    mock_turns(monkeypatch, turn(), turn(reply="Aur kis qisam ke features chahiye?"))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("Website chahiye", "old-service")
    old = await pi.reply_to("old-service")
    await pi.process("Booking form bhi chahiye", "new-service")
    await send_pi_message(pi.ctx, str(old.id))
    assert old.status == "skipped" and old.error_code == "NEWER_CUSTOMER_MESSAGE"
    await pi.close()


async def test_customer_opt_out_is_saved_and_cancels_reminder(api, business_db, monkeypatch):
    pi, conversation = await reminder_workspace(api, business_db, monkeypatch)
    mock_turns(
        monkeypatch,
        turn(
            reply="Theek hai, reminder nahi bhejunga.",
            consent="declined",
            consent_evidence="reminder mat bhejna",
        ),
    )
    await pi.process("reminder mat bhejna", "customer-optout")
    await pi.deliver_all()
    assert conversation.service_brief["reminder_consent"] == "declined"
    assert conversation.service_brief["consent_evidence"] == "reminder mat bhejna"
    assert conversation.followup_due_at is None
    await sweep_followups(pi.ctx)
    assert not any(m.media.get("reminder") for m in await pi.outbound())
    await pi.close()


async def test_takeover_during_generation_discards_generated_reply(api, business_db, monkeypatch):
    pi = await pi_workspace(api, business_db, business_type="service_business")

    async def generate(self, scope, output, **kwargs):
        conversation = await pi.conversation()
        conversation.mode = "human"
        await business_db.commit()
        return SimpleNamespace(value=turn(), response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", generate)
    await pi.process("Website chahiye", "inflight-takeover")
    assert await pi.outbound() == []
    assert (await pi.conversation()).summary == ""
    await pi.close()


async def test_service_uses_approved_knowledge_and_respects_tool_switch(
    api, business_db, monkeypatch
):
    contexts = mock_turns(monkeypatch, turn(), turn())
    pi = await pi_workspace(api, business_db, business_type="service_business")
    source = await create(api, "pi/knowledge/sources", {"name": "Service policy", "kind": "policy"})
    await create(
        api,
        "pi/knowledge/documents",
        {
            "source_id": source["id"],
            "title": "Revisions",
            "body": "Website revisions include accessibility review.",
        },
    )
    await pi.process("revisions", "faq-enabled")
    assert "accessibility review" in contexts[0]
    response = await api.patch(
        "/api/v1/pi/settings/tool_permissions", json={"value": {"search_knowledge_base": False}}
    )
    assert response.status_code == 200
    await pi.process("revisions", "faq-disabled")
    import json

    assert json.loads(contexts[1])["approved_knowledge"] == []
    await pi.close()
