# ruff: noqa: E501
"""PS-flow: the PS-10 review before send: typed inputs, regenerate once, then the owner-language fallback."""

import asyncio
from types import SimpleNamespace

from app.modules.pi import service_conversation as sc


def turn_with(reply, items=()):
    t = sc.ServiceTurn(reply=reply)
    t._voice_items = tuple(items)
    return t


def ctx(msg, other=None, lang="en", **extra):
    c = {"pi_mode": "brain", "latest_customer_message": msg, "reply_language": lang, **extra}
    if other:
        c["reply_language_other"] = other
    return c


def run(t, c, manager=None):
    asyncio.run(sc.pre_send_guard(t, c, manager, None, None, None))


class FakeManager:
    """Answers the single rewrite call (the guard's regenerate-once) with a fixed text."""

    def __init__(self, text):
        self.text = text
        self.calls = 0

    async def complete(self, *args, **kwargs):
        self.calls += 1
        return SimpleNamespace(text=self.text)


def test_a_delivered_claim_is_replaced_by_the_proposal_fallback():
    t = turn_with("Yes, your reminder system has been delivered and is live now.")
    run(t, ctx("Is the reminder system ready?"))
    assert "delivered" not in t.reply and "suggestion" in t.reply and t.reply.count("?") == 1


def test_a_roman_urdu_reply_to_an_urdu_script_owner_is_written_again_once():
    t = turn_with("Theek hai, main aap ke liye ek system banata hoon. Kab tak chahiye?")
    manager = FakeManager("ٹھیک ہے، آپ کو یہ کب تک چاہیے؟")
    run(t, ctx("مجھے ایک ریمائنڈر سسٹم چاہیے", other="Urdu", lang=""), manager)
    assert manager.calls <= 1 and any("\u0600" <= ch <= "\u06ff" for ch in t.reply)
    assert "Theek" not in t.reply


def test_when_the_second_try_is_still_wrong_the_owner_language_fallback_goes():
    t = turn_with("Theek hai, main aap ke liye ek system banata hoon. Kab tak chahiye?")
    manager = FakeManager("Still Roman Urdu: kab tak chahiye?")
    run(t, ctx("مجھے ایک ریمائنڈر سسٹم چاہیے", other="Urdu", lang=""), manager)
    assert any("\u0600" <= ch <= "\u06ff" for ch in t.reply) and "Still" not in t.reply


def test_a_clean_reply_in_the_owners_language_is_left_alone():
    reply = "Ji, yeh theek hai. Kab se shuru hua?"
    t = turn_with(reply)
    run(t, ctx("Reminders late jate hain", lang="roman_ur"))
    assert t.reply == reply


def test_the_draft_carries_what_the_flow_holds():
    c = ctx(
        "Late orders hurt",
        memory={"known": [{"source": "facts", "text": "budget: 50,000"}], "scope": {}},
        requirements={"tried": [{"what": "a discount", "outcome": "failed"}]},
    )
    t = turn_with(
        "Ask each buyer for a delivery note. Which orders are late?",
        items=[
            {
                "text": "Ask each buyer for a delivery note",
                "gate": "satisfied",
                "relevance": "LINKED",
                "unchecked": False,
            }
        ],
    )
    d = sc.review_draft(t, c, "en", t.reply)
    assert d.context.retrieved is True and d.context.sources == ("facts",)
    assert d.tried_solutions == ("a discount",)
    assert [o.relevance for o in d.options] == ["LINKED"]
    assert d.questions.count == 1 and d.questions.last_sentence.endswith("?")


def test_application_written_replies_are_skipped():
    t = turn_with("Just to confirm: you approve quote Q-0001 for PKR 450,000.00. Is that right?")
    t._cost_line = "The quote is free of charge."
    before = t.reply
    run(t, ctx("yes"))
    assert t.reply == before
