"""The request desk: pi asks the team, the team answers, pi replies to the customer
itself using that answer. Price and approve requests close when the proposal goes out."""

import json
from uuid import UUID

import pytest
from sqlalchemy import select
from test_pi_deals import DEALS, _customer_in_chat, _lead, _price
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import mock_turns, turn

from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi_saas.models import PiStaffRequest
from app.modules.pi_saas.requests import raise_request, reply_with_answer
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration
DESK = "/api/v1/pi/requests"


async def test_a_draft_proposal_becomes_a_price_request_that_closes_when_sent(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    customer_id, conversation = await _customer_in_chat(pi)
    lead_id = await _lead(pi, customer_id, conversation)
    from app.modules.pi_saas import deals

    system = await deals.system_scope_for(pi.db, UUID(pi.tenant_id), UUID(pi.environment_id))
    settings = api._transport.app.state.settings
    await deals.auto_proposal(pi.db, system, settings, UUID(lead_id))
    await pi.db.commit()

    desk = (await api.get(DESK)).json()
    [request] = [r for r in desk["items"] if r["kind"] == "price"]
    assert request["status"] == "open" and request["lead_id"] == lead_id
    assert request["customer_name"] == "Ayesha Khan" and desk["open"] >= 1
    quote_id = request["quote_id"]

    await _price(pi, quote_id)
    sent = await api.post(f"{DEALS}/quotes/{quote_id}/send")
    assert sent.status_code == 200, sent.text
    done = (await api.get(DESK, params={"status": "done"})).json()["items"]
    assert [r["status"] for r in done if r["id"] == request["id"]] == ["resolved"]
    await pi.close()


async def test_team_answer_goes_back_to_pi_which_replies_itself(api, business_db, monkeypatch):
    contexts = mock_turns(
        monkeypatch,
        turn(
            reply="Thanks for waiting! I checked with the team: yes, we deliver to Karachi "
            "too. Which city is it for?",
            language="en",
        ),
        turn(reply="Great, noted.", language="en"),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    customer_id, conversation = await _customer_in_chat(pi)
    # The customer asked something pi didn't know; the chat went to the team.
    pi.db.add(
        PiMessage(
            tenant_id=UUID(pi.tenant_id),
            environment_id=UUID(pi.environment_id),
            conversation_id=conversation.id,
            direction="inbound",
            sender_type="customer",
            message_type="text",
            body="Do you deliver to Karachi?",
            status="processed",
        )
    )
    row = await pi.db.get(PiConversation, conversation.id)
    row.mode = "human"
    scope = WorkspaceScope.system(
        UUID(pi.tenant_id), UUID(pi.environment_id), frozenset({"pi.read"}), "PI"
    )
    request = await raise_request(
        pi.db,
        scope,
        conversation_id=conversation.id,
        customer_id=UUID(customer_id),
        kind="question",
        question="Do you deliver to Karachi?",
    )
    await pi.db.commit()

    answered = await api.post(
        f"{DESK}/{request.id}/answer", json={"answer": "Yes, Karachi delivery takes 3 days."}
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["status"] == "answered"
    await pi.db.refresh(row)
    assert row.mode == "ai"  # pi has the chat again
    jobs = [args for name, args in pi.app.state.queue.jobs if name == "pi_reply_with_team_answer"]
    assert jobs == [(str(request.id),)]

    await reply_with_answer(pi.ctx, str(request.id))
    await reply_with_answer(pi.ctx, str(request.id))  # a repeated job sends nothing more
    context = json.loads(contexts[0])
    assert context["team_answer_now"]["answer"] == "Yes, Karachi delivery takes 3 days."
    replies = [
        m
        for m in await pi.db.scalars(
            select(PiMessage).where(
                PiMessage.conversation_id == conversation.id, PiMessage.sender_type == "ai"
            )
        )
    ]
    assert [m.body for m in replies] == [
        "Thanks for waiting! I checked with the team: yes, we deliver to Karachi too. "
        "Which city is it for?"
    ]
    assert replies[0].status == "queued"

    # The answer stays with pi for the next turns.
    await pi.process("Lahore actually", "desk-2")
    later = json.loads(contexts[1])
    assert any("Karachi delivery takes 3 days" in n["note"] for n in later["team_notes"])
    await pi.close()


async def test_the_pi_app_answer_route_uses_the_desk(api, business_db, monkeypatch):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    customer_id, conversation = await _customer_in_chat(pi)
    scope = WorkspaceScope.system(
        UUID(pi.tenant_id), UUID(pi.environment_id), frozenset({"pi.read"}), "PI"
    )
    request = await raise_request(
        pi.db,
        scope,
        conversation_id=conversation.id,
        customer_id=UUID(customer_id),
        kind="question",
        question="Do you have weekend hours?",
    )
    await pi.db.commit()
    answered = await api.post(
        f"/api/v1/pi-app/staff-requests/{request.id}/answer",
        json={"answer": "Saturdays 10 to 4.", "mode": "reply_once"},
    )
    if answered.status_code in (401, 403):
        pytest.skip("pi app session not set up in this harness")
    assert answered.status_code == 200, answered.text
    row = await pi.db.get(PiStaffRequest, request.id)
    await pi.db.refresh(row)
    assert row.answer == "Saturdays 10 to 4." and row.reply_message_id is None
    await pi.close()
