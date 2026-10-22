"""Brain mode: the offer, the yes gate and the decline, in a real chat. Real database/webhook/
worker; the AI and WhatsApp are mocked (the model's own reply is overridden at the gates)."""

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, create, problems_of, say, workspace
from test_pi_service_conversations import turn

from app.modules.customers.models import Customer
from app.modules.pi import decisions
from app.modules.pi_saas.models import PiStaffRequest

pytestmark = pytest.mark.integration

OPENING = "Hi, I'm pi, an AI from Workzap."


def model(context, n):
    """New problems when the customer describes them; otherwise a neutral reply. At the gates the
    application replaces the reply; for 'only the stock ones' the model picks the refs."""
    said = context["latest_customer_message"]
    ops, refs = [], []
    reply = "Noted. Anything else getting in the way?"
    if "Best-sellers" in said:
        ops = [
            create("Best-sellers run out in two shops", "Best-sellers run out."),
            create("Cashiers late on weekends", "Cashiers come late.", "people_staff"),
        ]
        reply = f"{OPENING} Noted both. Anything else getting in the way?"
    elif "delivery" in said:
        ops = [create("Deliveries arrive late", "Delivery is late.", "orders_fulfilment")]
    elif "only the stock" in said:
        refs = [p["ref"] for p in context["noted_problems"] if p["group"] == "stock_inventory"]
        reply = "Understood."
    return turn(reply=reply, language="en", problem_ops=ops, include_refs=refs)


async def to_the_offer(api, db, monkeypatch):
    prompts = adaptive(monkeypatch, model)
    pi = await workspace(api, db)
    await say(pi, "Best-sellers run out and cashiers are late on weekends", "of-1")
    await say(pi, "That's all", "of-2")
    await say(pi, "looks right", "of-3")
    return pi, prompts


async def state_of(db, pi):
    conversation = await pi.conversation()
    await db.refresh(conversation)
    return conversation


async def test_the_summary_then_the_fixed_offer_with_buttons(api, business_db, monkeypatch):
    pi, _ = await to_the_offer(api, business_db, monkeypatch)
    summary = (await pi.reply_to("of-2")).body
    assert summary.startswith("Here's what I've noted and sorted so far.")
    offer = await pi.reply_to("of-3")
    assert offer.body == decisions.text("offer", "en")
    assert (await state_of(business_db, pi)).flow_state == "S5_READINESS"
    assert (offer.media or {}).get("buttons") == decisions.OFFER_BUTTONS["en"]
    await pi.close()


async def test_yes_asks_all_or_some_then_all_starts_preparing(api, business_db, monkeypatch):
    pi, _ = await to_the_offer(api, business_db, monkeypatch)
    await say(pi, "ok", "of-4")
    assert (await pi.reply_to("of-4")).body == "Shall I go ahead and ask Workzap to prepare them?"
    assert (await state_of(business_db, pi)).flow_state == "S5_READINESS"  # ok is not a yes
    await say(pi, "yes", "of-5")
    assert (await pi.reply_to("of-5")).body == "Should it cover all of these, or only some?"
    await say(pi, "all of them", "of-6")
    assert (await pi.reply_to("of-6")).body == decisions.text("preparing", "en")
    conversation, rows = await problems_of(business_db, pi)
    assert conversation.flow_state == "S6_PREPARING"
    offer = conversation.service_brief["offer"]
    assert offer["problem_refs"] == [str(r.id)[:8] for r in rows]
    assert offer["yes_message_id"] and offer["confirm_message_id"] and offer["at"]
    assert (
        offer["yes_message_id"] != offer["confirm_message_id"]
    )  # yes first, then the scope answer
    [request] = (await business_db.scalars(select(PiStaffRequest))).all()
    assert request.kind == "review_document" and request.priority == "high"
    assert "Best-sellers run out in two shops" in request.question
    assert "Cashiers late on weekends" in request.question
    await pi.close()


async def test_only_some_prepares_just_the_chosen_problems(api, business_db, monkeypatch):
    pi, _ = await to_the_offer(api, business_db, monkeypatch)
    await say(pi, "yes", "os-1")
    await say(pi, "only the stock ones", "os-2")
    conversation, rows = await problems_of(business_db, pi)
    stock = next(r for r in rows if r.category == "stock_inventory")
    assert conversation.flow_state == "S6_PREPARING"
    assert conversation.service_brief["offer"]["problem_refs"] == [str(stock.id)[:8]]
    [request] = (await business_db.scalars(select(PiStaffRequest))).all()
    assert "Best-sellers" in request.question and "Cashiers" not in request.question
    await pi.close()


async def test_no_is_accepted_and_new_problems_reopen_listening(api, business_db, monkeypatch):
    pi, _ = await to_the_offer(api, business_db, monkeypatch)
    await say(pi, "no thanks", "dn-1")
    assert (await pi.reply_to("dn-1")).body == decisions.text("declined", "en")
    conversation = await state_of(business_db, pi)
    assert conversation.flow_state == "S5b_DECLINED"
    assert conversation.service_brief["offer_declined"] is True
    assert (await business_db.scalars(select(PiStaffRequest))).all() == []
    await say(pi, "Also the delivery is always late", "dn-2")
    reply = (await pi.reply_to("dn-2")).body
    assert "solution document" not in reply and "quote" not in reply  # no re-offer (R-SELL-05)
    assert (await state_of(business_db, pi)).flow_state == "S3_NOTED"
    await pi.close()


async def test_a_team_member_cannot_say_yes_for_the_business(api, business_db, monkeypatch):
    pi, _ = await to_the_offer(api, business_db, monkeypatch)
    conversation = await state_of(business_db, pi)
    customer = await business_db.get(Customer, conversation.customer_id)
    customer.can_approve = False
    await business_db.commit()
    await say(pi, "yes", "mem-1")
    reply = (await pi.reply_to("mem-1")).body
    assert "needs to say yes to a quote" in reply and "workzap.ai/pi/talk-to-pi" in reply
    conversation = await state_of(business_db, pi)
    assert conversation.flow_state == "S5_READINESS"
    assert conversation.service_brief["offer_wanted_by_member"] is True
    assert (await business_db.scalars(select(PiStaffRequest))).all() == []
    await pi.close()


async def test_later_pauses_and_coming_back_listens_again(api, business_db, monkeypatch):
    pi, _ = await to_the_offer(api, business_db, monkeypatch)
    await say(pi, "later", "lt-1")
    assert (await pi.reply_to("lt-1")).body.startswith("No rush.")
    conversation = await state_of(business_db, pi)
    assert conversation.flow_state == "X_PAUSED"
    assert conversation.service_brief["paused_from"] == "S5_READINESS"
    await say(pi, "Hi, I'm back", "lt-2")
    assert (await state_of(business_db, pi)).flow_state in ("S1_LISTENING", "S2_CLARIFYING")
    await pi.close()


async def test_a_cost_question_at_the_offer_is_answered_not_gated(api, business_db, monkeypatch):
    pi, prompts = await to_the_offer(api, business_db, monkeypatch)
    await say(pi, "how much would it cost?", "cq-1")
    assert (await pi.reply_to("cq-1")).body != decisions.text("preparing", "en")
    assert (await state_of(business_db, pi)).flow_state == "S5_READINESS"
    assert (await business_db.scalars(select(PiStaffRequest))).all() == []
    await pi.close()


async def test_approving_a_quote_takes_two_confirmations(api, business_db, monkeypatch):
    """The quote itself arrives in phase 4: here it is put on the table by hand."""
    from app.modules.pi import service_conversation as conversation_service

    real = conversation_service.brain_problems

    async def with_quote(*args, **kwargs):
        context = await real(*args, **kwargs)
        return {**context, "open_quote": {"id": "Q-12", "total": "Rs 450,000"}}

    monkeypatch.setattr(conversation_service, "brain_problems", with_quote)
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await say(pi, "Best-sellers run out and cashiers are late on weekends", "ap-1")
    conversation = await state_of(business_db, pi)
    conversation.flow_state = "S8_REVIEW"
    await business_db.commit()
    await say(pi, "Approve", "ap-2")
    first = (await pi.reply_to("ap-2")).body
    assert first == "Just to confirm: you approve quote Q-12 for Rs 450,000. Is that right?"
    conversation = await state_of(business_db, pi)
    assert conversation.flow_state == "S8_REVIEW"
    assert conversation.service_brief["approval_pending"]["quote"] == "Q-12"
    await say(pi, "yes", "ap-3")
    assert (await pi.reply_to("ap-3")).body == decisions.text("approved", "en")
    conversation = await state_of(business_db, pi)
    assert conversation.flow_state == "S10_AWAITING_PAYMENT"
    approval = conversation.service_brief["approval"]
    assert approval["quote"] == "Q-12" and len(approval["confirm_message_ids"]) == 2
    assert approval["confirm_message_ids"][0] != approval["confirm_message_ids"][1]
    assert "approval_pending" not in conversation.service_brief
    [request] = (await business_db.scalars(select(PiStaffRequest))).all()
    assert request.kind == "approve" and "Q-12" in request.question
    await pi.close()


async def test_a_second_message_that_is_not_a_yes_drops_the_approval(api, business_db, monkeypatch):
    from app.modules.pi import service_conversation as conversation_service

    real = conversation_service.brain_problems

    async def with_quote(*args, **kwargs):
        return {**await real(*args, **kwargs), "open_quote": {"id": "Q-12", "total": "Rs 450,000"}}

    monkeypatch.setattr(conversation_service, "brain_problems", with_quote)
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await say(pi, "Best-sellers run out and cashiers are late on weekends", "dr-1")
    conversation = await state_of(business_db, pi)
    conversation.flow_state = "S8_REVIEW"
    await business_db.commit()
    await say(pi, "Approve", "dr-2")
    await say(pi, "wait, when does it start?", "dr-3")
    assert (await pi.reply_to("dr-3")).body.startswith("Okay, I haven't approved anything.")
    conversation = await state_of(business_db, pi)
    assert conversation.flow_state == "S8_REVIEW"
    assert "approval_pending" not in conversation.service_brief
    assert (await business_db.scalars(select(PiStaffRequest))).all() == []
    await pi.close()
