"""Nori support mode on the disposable database: a registry person's message gets a grounded reply
from pi when the workspace turned on `support`, and every failure falls back to the plain
acknowledgement. The model is a fake; nori and WhatsApp are mock transports. Run only through
scripts/pi-test-env.sh."""

import pytest
from sqlalchemy import select
from test_nori_board_flow import WRITER, add_number, cards, outbound_bodies
from test_nori_credits_bridge import bridge

from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi_saas.nori_credits.client import WORKSPACE_CACHE
from app.modules.pi_saas.nori_credits.hook import BOARD_ACK
from app.modules.pi_saas.nori_support.responder import KEY_PREFIX

pytestmark = pytest.mark.integration

WORKSPACE = {
    "name": "Mendeez Demo",
    "plan": "Starter",
    "status": "trial",
    "trial_ends_at": "2026-11-20T10:00:00Z",
    "credits": 120,
    "health": {"status": "ok"},
}


class FakeManager:
    """Stands in for the model: answers with whatever the test set, and records the prompts."""

    def __init__(self, reply: str | Exception) -> None:
        self.reply = reply
        self.calls: list[dict] = []

    async def complete(self, scope, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.reply, Exception):
            raise self.reply
        return type("R", (), {"text": self.reply})()


@pytest.fixture
def model(monkeypatch):
    manager = FakeManager("")
    monkeypatch.setattr("app.ai.manager.build_llm_manager", lambda *a, **k: manager)
    return manager


async def support_bridge(api, business_db, **extra):
    WORKSPACE_CACHE.clear()  # the cache is per process: one test's facts must not reach the next
    b = await bridge(api, business_db, board=True, **extra)
    await add_number(b)
    b.nori.workspaces[WRITER] = WORKSPACE
    return b


async def test_support_off_keeps_the_silent_chat_and_never_calls_the_model(api, business_db, model):
    b = await support_bridge(api, business_db)  # support not set
    model.reply = "I'm pi, an AI assistant. You have 120 credits left."
    await b.say(WRITER, "How many credits do I have?", "wamid.s-off-1")
    assert await outbound_bodies(b) == [BOARD_ACK]
    assert model.calls == []
    assert b.nori.calls("/api/credits/pi", "workspace_info") == []
    await b.pi.close()


async def test_support_on_answers_from_nori_facts_and_files_the_card(api, business_db, model):
    b = await support_bridge(api, business_db, support=True)
    model.reply = (
        "I'm pi, an AI assistant. Your trial ends on 20 November and 120 credits are left."
    )
    await b.say(WRITER, "How many credits do I have?", "wamid.s-on-1")
    assert await outbound_bodies(b) == [model.reply]  # the reply, not the acknowledgement
    assert len(await cards(b)) == 1  # still a requirement for the team
    [inbound] = await b.inbound_rows("wamid.s-on-1")
    assert (await b.pi.db.get(PiConversation, inbound.conversation_id)).mode == "human"
    keys = list(
        await b.pi.db.scalars(
            select(PiMessage.idempotency_key).where(PiMessage.direction == "outbound")
        )
    )
    assert keys == [f"{KEY_PREFIX}{inbound.id}"]
    # the facts reached the model as data, below the rules, with the number's last message
    prompt = model.calls[0]["messages"][1].content
    assert "Mendeez Demo" in str(prompt) and "Credits left: 120" in str(prompt)
    assert len(b.nori.calls("/api/credits/pi", "workspace_info")) == 1
    await b.pi.close()


async def test_an_invented_figure_falls_back_to_the_acknowledgement(api, business_db, model):
    b = await support_bridge(api, business_db, support=True)
    model.reply = "I'm pi, an AI assistant. You have 999 credits left."
    await b.say(WRITER, "How many credits do I have?", "wamid.s-bad-1")
    assert await outbound_bodies(b) == [BOARD_ACK]
    assert len(await cards(b)) == 1
    await b.pi.close()


async def test_a_model_failure_falls_back_and_the_chat_still_works(api, business_db, model):
    b = await support_bridge(api, business_db, support=True)
    model.reply = RuntimeError("model down")
    await b.say(WRITER, "The export is not working", "wamid.s-fail-1")
    assert await outbound_bodies(b) == [BOARD_ACK]
    await b.pi.close()


async def test_nori_down_means_no_facts_and_no_figure_in_the_reply(api, business_db, model):
    b = await support_bridge(api, business_db, support=True)
    b.nori.mode = "500"
    model.reply = "I'm pi, an AI assistant. I will check with the Workzap team."
    await b.say(WRITER, "How many credits do I have?", "wamid.s-down-1")
    assert await outbound_bodies(b) == [model.reply]
    assert "nothing is known" in str(model.calls[0]["messages"][1].content)
    model.reply = "You have 120 credits."
    await b.say(WRITER, "And now?", "wamid.s-down-2")
    assert (await outbound_bodies(b))[-1] != model.reply  # an ungrounded figure is never sent
    await b.pi.close()


async def test_card_data_typed_in_chat_gets_a_fixed_line_without_the_model(api, business_db, model):
    b = await support_bridge(api, business_db, support=True)
    model.reply = "should never be used"
    await b.say(WRITER, "my card is 4242 4242 4242 4242", "wamid.s-card-1")
    bodies = await outbound_bodies(b)
    assert len(bodies) == 1 and bodies[0] != model.reply
    assert model.calls == []
    await b.pi.close()


async def test_a_retried_message_is_answered_once(api, business_db, model):
    b = await support_bridge(api, business_db, support=True)
    model.reply = "I'm pi, an AI assistant. Noted for the Workzap team."
    await b.say(WRITER, "Please add van sales", "wamid.s-dup-1")
    await b.say(WRITER, "Please add van sales", "wamid.s-dup-1")
    assert await outbound_bodies(b) == [model.reply]
    await b.pi.close()


async def test_the_kill_switch_turns_support_off_at_once(api, business_db, model):
    b = await support_bridge(api, business_db, support=True)
    b.pi.app.state.settings.nori_bridge_kill = True
    model.reply = "I'm pi, an AI assistant. Noted."
    await b.say(WRITER, "The export is not working", "wamid.s-kill-1")
    assert model.calls == []
    await b.pi.close()


async def test_are_you_human_gets_the_fixed_ai_answer_without_the_model(api, business_db, model):
    b = await support_bridge(api, business_db, support=True)
    model.reply = "Yes, I am from the support team."
    await b.say(WRITER, "is this a real person?", "wamid.s-human-1")
    bodies = await outbound_bodies(b)
    assert len(bodies) == 1 and "AI" in bodies[0].split(".")[0]
    assert model.calls == []
    await b.pi.close()


async def test_card_numbers_typed_by_a_registry_person_are_not_stored_raw(api, business_db, model):
    b = await support_bridge(api, business_db, support=True)
    await b.say(WRITER, "my card is 4242 4242 4242 4242", "wamid.s-raw-1")
    [inbound] = await b.inbound_rows("wamid.s-raw-1")
    stored = await b.pi.db.get(PiMessage, inbound.id)
    assert "4242 4242" not in str(stored.body)
    conversation = await b.pi.db.get(PiConversation, inbound.conversation_id)
    assert "4242 4242" not in conversation.last_message_preview
    await b.pi.close()
