"""Abuse, spam, complaints and shared cards in a real chat (spec 6.7, 6.8, 6.10)."""

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi.quarantine_models import PiQuarantine
from app.modules.pi_saas.models import PiStaffRequest

pytestmark = pytest.mark.integration


def neutral(context, n):
    return turn(reply="Noted. Anything else getting in the way?", language="en")


async def state_of(db, pi):
    conversation = await pi.conversation()
    await db.refresh(conversation)
    return conversation


async def replies(db):
    rows = await db.scalars(
        select(PiMessage).where(PiMessage.direction == "outbound").order_by(PiMessage.created_at)
    )
    return list(rows)


async def test_repeated_insults_end_in_a_hand_over_and_then_silence_until_a_person_unblocks(
    api, business_db, monkeypatch
):
    prompts = adaptive(monkeypatch, neutral)
    pi = await workspace(api, business_db)
    sent = []
    for n in range(1, 6):
        await say(pi, "you are stupid", f"ab-{n}")
        sent.append((await pi.reply_to(f"ab-{n}")).body)
    assert sent[0].startswith("I'm here to help with the business problems")
    assert "pass this chat to the Workzap team" in sent[2]  # the one warning
    assert sent[3] == sent[0]  # calm again, no second warning
    assert sent[4] == "I'm passing this chat to the Workzap team."
    assert prompts == []  # the model never saw any of it
    conversation = await state_of(business_db, pi)
    assert conversation.flow_state == "X_BLOCKED"
    [request] = (await business_db.scalars(select(PiStaffRequest))).all()
    assert request.priority == "high" and request.question.startswith("ABUSE")

    # Blocked: pi says nothing more, even to a perfectly good message.
    before = len(await replies(business_db))
    await pi.process("sorry, my stock runs out in two shops", "ab-6")
    await pi.deliver_all()
    assert len(await replies(business_db)) == before
    silent = (
        await business_db.scalars(select(PiMessage).where(PiMessage.provider_message_id == "ab-6"))
    ).one()
    assert silent.status == "skipped" and silent.error_code == "MODERATION_SILENT"

    # A person decides: the chat listens again and the strikes are gone.
    unblocked = await api.post(f"/api/v1/pi/brain-moderation/{conversation.id}/unblock")
    assert unblocked.status_code == 200, unblocked.text
    assert unblocked.json() == {
        "id": str(conversation.id),
        "flow_state": "S1_LISTENING",
        "from": "X_BLOCKED",
    }
    await say(pi, "my stock runs out in two shops", "ab-7")
    assert (await pi.reply_to("ab-7")).body == "Noted. Anything else getting in the way?"
    again = await api.post(f"/api/v1/pi/brain-moderation/{conversation.id}/unblock")
    assert again.status_code == 409 and again.json()["error"]["code"] == "NOT_BLOCKED"
    await pi.close()


async def test_a_threat_gets_one_warning_and_a_staff_alert_then_a_hand_over(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, neutral)
    pi = await workspace(api, business_db)
    await say(pi, "I will kill you", "th-1")
    first = (await pi.reply_to("th-1")).body
    assert "pass this chat to the Workzap team" in first
    [request] = (await business_db.scalars(select(PiStaffRequest))).all()
    assert request.priority == "high" and request.question.startswith("THREAT")
    assert (await state_of(business_db, pi)).flow_state != "X_BLOCKED"
    await say(pi, "I will kill you and your team", "th-2")
    assert (await pi.reply_to("th-2")).body == "I'm passing this chat to the Workzap team."
    assert (await state_of(business_db, pi)).flow_state == "X_BLOCKED"
    await pi.close()


async def test_spam_is_answered_once_and_then_ignored_until_they_write_about_their_business(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, neutral)
    pi = await workspace(api, business_db)
    await say(pi, "earn $500 daily from home, click this link", "sp-1")
    assert (await pi.reply_to("sp-1")).body == "I'm here for problems in your business."
    assert (await state_of(business_db, pi)).flow_state == "X_OUT_OF_SCOPE"
    before = len(await replies(business_db))
    await pi.process("join my whatsapp group for guaranteed returns", "sp-2")
    await pi.deliver_all()
    assert len(await replies(business_db)) == before  # nothing more for the spammer
    await say(pi, "actually my stock runs out in two shops", "sp-3")
    assert (await pi.reply_to("sp-3")).body == "Noted. Anything else getting in the way?"
    assert (await state_of(business_db, pi)).flow_state != "X_OUT_OF_SCOPE"
    await pi.close()


async def test_a_complaint_about_workzap_is_thanked_passed_on_and_not_noted_as_a_problem(
    api, business_db, monkeypatch
):
    prompts = adaptive(monkeypatch, neutral)
    pi = await workspace(api, business_db)
    await say(pi, "I want to complain about Workzap", "cp-1")
    assert (await pi.reply_to("cp-1")).body == (
        "Thanks for telling me. I've passed this to the Workzap team."
    )
    [request] = (await business_db.scalars(select(PiStaffRequest))).all()
    assert request.question.startswith("COMPLAINT") and request.priority == "high"
    assert prompts == []
    await pi.close()


async def test_a_shared_contact_card_is_dropped_and_the_person_is_told_why(
    api, business_db, monkeypatch
):
    prompts = adaptive(monkeypatch, neutral)
    pi = await workspace(api, business_db)
    await say(pi, "Contact card shared: Ali Raza 0300 1234567", "cc-1")
    reply = (await pi.reply_to("cc-1")).body
    assert "I don't need other people's contact details here" in reply
    stored = (
        await business_db.scalars(select(PiMessage).where(PiMessage.provider_message_id == "cc-1"))
    ).one()
    assert stored.body == "[contact card removed]" and "Ali" not in stored.body
    assert prompts == []
    conversation = await pi.conversation()
    assert conversation.service_brief["pii_told"] == ["contact"]
    assert (await business_db.scalars(select(PiQuarantine))).all() is not None
    await pi.close()


async def test_a_location_pin_is_stored_without_coordinates(api, business_db, monkeypatch):
    adaptive(monkeypatch, neutral)
    pi = await workspace(api, business_db)
    await say(pi, "Location shared: Johar Town branch (31.5204, 74.3587)", "lp-1")
    stored = (
        await business_db.scalars(select(PiMessage).where(PiMessage.provider_message_id == "lp-1"))
    ).one()
    assert stored.body == "[a location was shared]" and "31.52" not in stored.body
    assert (await pi.reply_to("lp-1")).body  # pi still answers (nothing was asked of them)
    assert (await business_db.scalar(select(PiConversation.id))) is not None
    await pi.close()


async def test_ordinary_talk_that_sounds_rude_about_someone_else_is_just_a_problem(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, neutral)
    pi = await workspace(api, business_db)
    await say(pi, "my cashier is stupid and steals from the till", "ok-1")
    assert (await pi.reply_to("ok-1")).body.endswith("Noted. Anything else getting in the way?")
    assert (await state_of(business_db, pi)).flow_state != "X_BLOCKED"
    assert (await business_db.scalars(select(PiStaffRequest))).all() == []
    await pi.close()


async def serve(api, trades):
    response = await api.patch(
        "/api/v1/pi/settings/response_rules",
        json={"value": {"brain": {"served_industries": trades}}},
    )
    assert response.status_code == 200, response.text


async def test_a_regulated_trade_is_declined_once_when_workzap_does_not_serve_it(
    api, business_db, monkeypatch
):
    prompts = adaptive(monkeypatch, neutral)
    pi = await workspace(api, business_db)
    await serve(api, [])  # leadership decided: no regulated trade is served
    await say(pi, "I run a licensed arms and ammunition dealer, stock counts are off", "tr-1")
    assert (await pi.reply_to("tr-1")).body == (
        "Workzap doesn't take on work in this area, so I can't help with this one."
    )
    assert prompts == []
    conversation = await state_of(business_db, pi)
    assert conversation.flow_state == "X_OUT_OF_SCOPE"
    assert conversation.service_brief["declined_trade"] == "arms"
    before = len(await replies(business_db))
    await pi.process("so can you help with my stock counts?", "tr-2")
    await pi.deliver_all()
    assert len(await replies(business_db)) == before  # declined once, then quiet
    unblocked = await api.post(f"/api/v1/pi/brain-moderation/{conversation.id}/unblock")
    assert unblocked.status_code == 200
    await business_db.refresh(conversation)
    assert "declined_trade" not in conversation.service_brief
    await pi.close()


async def test_a_served_regulated_trade_or_an_unset_list_gets_normal_help(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, neutral)
    pi = await workspace(api, business_db)
    # Never set: leadership has not decided, so pi helps as usual.
    await say(pi, "I run a licensed arms dealer and stock counts are off", "tr-3")
    assert (await pi.reply_to("tr-3")).body.endswith("Anything else getting in the way?")
    await serve(api, ["arms"])  # now served on purpose
    await say(pi, "my arms dealer shop also has staff schedule problems", "tr-4")
    assert (await pi.reply_to("tr-4")).body == "Noted. Anything else getting in the way?"
    await pi.close()


@pytest.mark.parametrize("bad", [["nonsense"], "arms", [1], {"arms": True}])
async def test_the_served_list_only_accepts_known_trades(api, business_db, monkeypatch, bad):
    adaptive(monkeypatch, neutral)
    pi = await workspace(api, business_db)
    refused = await api.patch(
        "/api/v1/pi/settings/response_rules",
        json={"value": {"brain": {"served_industries": bad}}},
    )
    assert refused.status_code >= 400, bad
    await pi.close()
