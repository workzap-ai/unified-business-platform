"""Regressions for docs/PI_TEST_READINESS_2026-09-29.md, against the real test database.

AI and WhatsApp delivery are mocked; these tests prove the guards, filters and
transaction boundaries, not live model behaviour.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import mock_turns, turn

from app.ai.registry import ModelRegistry
from app.modules.pi.models import PiAgentTool, PiConversation, PiMessage, PiSettings

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "reply",
    [
        "Is website ki qeemat pachaas hazaar rupay hai.",
        "اس ویب سائٹ کی قیمت پچاس ہزار روپے ہے۔",
        "سعر الموقع خمسة آلاف درهم",
    ],
)
async def test_written_service_price_never_reaches_whatsapp(api, business_db, monkeypatch, reply):
    mock_turns(monkeypatch, turn(reply=reply))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    try:
        await pi.process("Website ki qeemat kya hai?", "review-price-words")
        await pi.deliver_all()
        assert all(reply not in m.body for m in await pi.outbound())
        assert all(reply not in str(sent) for sent in pi.sent)
        assert (await pi.conversation()).mode == "human"  # Refused replies go to a person.
    finally:
        await pi.close()


async def test_business_hours_notice_with_digits_does_not_block_reply(
    api, business_db, monkeypatch
):
    mock_turns(monkeypatch, turn(reply="Aapki website ka main maqsad kya hai?"))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    try:
        assert (await api.get("/api/v1/pi/settings")).status_code == 200
        policy = await business_db.scalar(
            select(PiSettings).where(PiSettings.tenant_id == UUID(pi.tenant_id))
        )
        closed = {"open": False, "start": "09:00", "end": "17:00"}
        policy.business_hours = {
            "enabled": True,
            "outside_hours": "reply_with_notice",
            "notice": "We reply between 9am and 5pm.",
            "days": {d: dict(closed) for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")},
        }
        await business_db.flush()
        await pi.process("Mujhe website chahiye", "review-notice")
        reply = await pi.reply_to("review-notice")
        assert "main maqsad" in reply.body and "9am and 5pm" in reply.body
        assert (await pi.conversation()).mode == "ai"
    finally:
        await pi.close()


async def _second_conversation(db, first: PiConversation, **values) -> PiConversation:
    row = PiConversation(
        tenant_id=first.tenant_id,
        environment_id=first.environment_id,
        customer_id=first.customer_id,
        connection_id=first.connection_id,
        contact_wa_id=values.pop("contact_wa_id", "15550000002"),
        status="open",
        mode="ai",
        last_message_at=datetime.now(UTC),
        **values,
    )
    db.add(row)
    await db.flush()
    return row


@pytest.mark.parametrize("query", ["unread=true", "assignment=unassigned", "assignment=mine"])
async def test_inbox_filters_are_applied(api, business_db, query):
    pi = await pi_workspace(api, business_db)
    try:
        await pi.process("hello", "review-filter")
        first = await pi.conversation()
        first.unread_count = 0
        first.assigned_user_id = UUID(pi.identity["user"]["id"])
        other = await _second_conversation(business_db, first, unread_count=3)
        rows = (await api.get("/api/v1/pi/conversations?" + query)).json()["items"]
        expected = first.id if query == "assignment=mine" else other.id
        assert [row["id"] for row in rows] == [str(expected)]
        assert len((await api.get("/api/v1/pi/conversations?assignment=all")).json()["items"]) == 2
    finally:
        await pi.close()


@pytest.mark.parametrize("search", ["15550000001", "+1 555 000 0001", "reviewuniquemessage"])
async def test_inbox_search_matches_phone_and_message_text(api, business_db, search):
    pi = await pi_workspace(api, business_db)
    try:
        await pi.process("reviewuniquemessage", "review-search")
        response = await api.get("/api/v1/pi/conversations", params={"search": search})
        assert response.status_code == 200 and response.json()["total"] == 1
        miss = await api.get("/api/v1/pi/conversations", params={"search": "nothing-like-this"})
        assert miss.json()["total"] == 0
    finally:
        await pi.close()


async def test_history_cursor_returns_every_message_once_including_ties(api, business_db):
    pi = await pi_workspace(api, business_db)
    try:
        await pi.process("hello", "review-history")
        first = await pi.conversation()
        same = datetime.now(UTC) - timedelta(days=1)
        for i in range(107):
            business_db.add(
                PiMessage(
                    tenant_id=first.tenant_id,
                    environment_id=first.environment_id,
                    conversation_id=first.id,
                    direction="inbound",
                    sender_type="customer",
                    body=f"History {i}",
                    status="received",
                    # Ten messages share each timestamp to exercise the tie-breaker.
                    created_at=same + timedelta(seconds=i // 10),
                )
            )
        await business_db.flush()
        total = await business_db.scalar(
            select(PiMessage.id).where(PiMessage.conversation_id == first.id).limit(1)
        )
        assert total is not None
        seen: list[str] = []
        params: dict[str, str] = {"limit": "25"}
        while True:
            page = (
                await api.get(f"/api/v1/pi/conversations/{first.id}/history", params=params)
            ).json()
            seen = [m["id"] for m in page["items"]] + seen
            if not page["has_more"]:
                break
            params = {"limit": "25", "before": page["before"], "before_id": page["before_id"]}
        all_ids = set(
            str(i)
            for i in await business_db.scalars(
                select(PiMessage.id).where(PiMessage.conversation_id == first.id)
            )
        )
        assert len(seen) == len(set(seen)) == len(all_ids)
        assert set(seen) == all_ids
    finally:
        await pi.close()


async def test_agent_publish_is_atomic(api, business_db):
    pi = await pi_workspace(api, business_db)
    try:
        agents = (await api.get("/api/v1/pi/agents")).json()
        agent = next(a for a in agents if a["key"] == "support")
        version = {
            "instructions": "Answer from approved knowledge only.",
            "model_alias": "balanced",
            "temperature": "0.30",
            "note": "Review",
        }
        failed = await api.post(
            f"/api/v1/pi/agents/{agent['id']}/publish",
            json={"version": version, "tools": {"search_knowledge_base": False, "nope": True}},
        )
        assert failed.status_code == 422
        after = (await api.get(f"/api/v1/pi/agents/{agent['id']}")).json()
        assert after["current_version"] == agent["current_version"]
        ok = await api.post(
            f"/api/v1/pi/agents/{agent['id']}/publish",
            json={"version": version, "tools": {"search_knowledge_base": False}},
        )
        assert ok.status_code == 200, ok.text
        after = (await api.get(f"/api/v1/pi/agents/{agent['id']}")).json()
        assert after["current_version"] == agent["current_version"] + 1
        tool = await business_db.scalar(
            select(PiAgentTool).where(
                PiAgentTool.agent_id == UUID(agent["id"]),
                PiAgentTool.tool_key == "search_knowledge_base",
            )
        )
        assert tool is not None and tool.enabled is False
    finally:
        await pi.close()


async def test_overview_counts_default_model_aliases_as_configured(api, business_db):
    pi = await pi_workspace(api, business_db)
    settings = pi.app.state.settings
    saved = (settings.gemini_api_key, settings.gemini_models, settings.ai_use_default_models)
    try:
        settings.gemini_api_key = SecretStr("test-only-not-a-live-key")
        settings.gemini_models = {}
        settings.ai_use_default_models = True
        assert ModelRegistry.from_settings(settings).resolve("gemini", "balanced")
        providers = (await api.get("/api/v1/pi/overview")).json()["providers"]
        assert next(p for p in providers if p["name"] == "gemini")["configured"] is True
        settings.ai_use_default_models = False
        providers = (await api.get("/api/v1/pi/overview")).json()["providers"]
        assert next(p for p in providers if p["name"] == "gemini")["configured"] is False
    finally:
        settings.gemini_api_key, settings.gemini_models, settings.ai_use_default_models = saved
        await pi.close()
