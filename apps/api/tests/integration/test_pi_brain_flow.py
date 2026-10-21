"""pi_mode "brain": a conversation state, the fixed opening and listening-first rules.
Real database/webhook/worker; the AI and WhatsApp are mocked."""

import pytest
from test_pi_industry_context import contexts, scripted
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import turn

pytestmark = pytest.mark.integration


async def brain_on(api) -> None:
    response = await api.patch(
        "/api/v1/pi/settings/response_rules", json={"value": {"pi_mode": "brain"}}
    )
    assert response.status_code == 200, response.text
    assert response.json()["response_rules"]["pi_mode"] == "brain"


async def test_pi_mode_only_accepts_known_values(api, business_db):
    await pi_workspace(api, business_db, business_type="service_business")
    response = await api.patch(
        "/api/v1/pi/settings/response_rules", json={"value": {"pi_mode": "chaos"}}
    )
    assert response.status_code in (400, 422), response.text


async def test_standard_mode_has_no_state(api, business_db, monkeypatch):
    prompts = scripted(monkeypatch, turn(reply="Noted. Which shop is it?", language="en"))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("My shop stock keeps running out", "std-1")
    await pi.deliver_all()
    assert "flow" not in contexts(prompts)[0]
    assert (await pi.conversation()).flow_state is None
    await pi.close()


async def test_hi_gets_the_fixed_opening_and_the_chat_starts_listening(
    api, business_db, monkeypatch
):
    scripted(monkeypatch, turn(reply="unused", language="en"))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await brain_on(api)
    await pi.process("Hi", "brain-hi")
    await pi.deliver_all()
    assert (await pi.reply_to("brain-hi")).body == (
        "Hi, I'm pi, an AI from Workzap. Tell me what's going wrong in your business "
        "and I'll start on it."
    )
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.flow_state == "S1_LISTENING"
    assert conversation.flow_state_since is not None
    await pi.close()


async def test_pi_sees_its_state_and_a_pitch_is_sent_back(api, business_db, monkeypatch):
    prompts = scripted(
        monkeypatch,
        turn(reply="Hi, I'm pi, an AI from Workzap. We can build an app for that.", language="en"),
        turn(reply="Hi, I'm pi, an AI from Workzap. Which shop does it happen in?", language="en"),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await brain_on(api)
    await pi.process("My shop stock keeps running out", "brain-1")
    await pi.deliver_all()
    first = contexts(prompts)[0]
    assert first["pi_mode"] == "brain" and first["strict_voice"] is True
    assert first["flow"]["state"] == "S0_NEW"
    assert "S1_LISTENING" in first["flow"]["allowed_next"]
    assert "R-SELL-01" in prompts[1]  # the pitch went back to the model
    reply = (await pi.reply_to("brain-1")).body
    assert "build an app" not in reply and reply.endswith("Which shop does it happen in?")
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.flow_state == "S1_LISTENING"  # the opening went out
    await pi.close()


async def test_a_pitch_that_survives_the_rewrite_is_never_sent(api, business_db, monkeypatch):
    scripted(
        monkeypatch,
        turn(reply="Hi, I'm pi, an AI from Workzap. Shall I send you a quote?", language="en"),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await brain_on(api)
    await pi.process("My shop stock keeps running out", "brain-2")
    await pi.deliver_all()
    assert not any("send you a quote" in m.body for m in await pi.outbound())
    await pi.close()


async def test_the_next_message_sees_the_stored_state(api, business_db, monkeypatch):
    prompts = scripted(
        monkeypatch,
        turn(reply="Hi, I'm pi, an AI from Workzap. Which shop is it?", language="en"),
        turn(
            reply="Noted: stock runs out in the big shop. Anything else getting in the way?",
            language="en",
        ),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await brain_on(api)
    await pi.process("My shop stock keeps running out", "brain-3a")
    await pi.deliver_all()
    await pi.process("The big shop on the main road", "brain-3b")
    await pi.deliver_all()
    assert contexts(prompts)[0]["flow"]["state"] == "S0_NEW"
    assert contexts(prompts)[-1]["flow"]["state"] == "S1_LISTENING"  # stored after turn one
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.flow_state == "S2_CLARIFYING"  # turn two asked a question
    await pi.close()
