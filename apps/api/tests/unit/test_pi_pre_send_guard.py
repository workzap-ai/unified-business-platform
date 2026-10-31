# ruff: noqa: E501
"""PS-flow: SR-13 and SR-16 of the self-review gate stop a wrong-language or 'delivered' reply."""

from app.modules.pi import service_conversation as sc


def turn_with(reply):
    t = sc.ServiceTurn(reply=reply) if hasattr(sc, "ServiceTurn") else None
    return t


def ctx(msg, other=None, lang="en"):
    c = {"pi_mode": "brain", "latest_customer_message": msg, "reply_language": lang}
    if other:
        c["reply_language_other"] = other
    return c


def test_a_delivered_claim_is_replaced_by_the_proposal_fallback():
    t = turn_with("Yes, your reminder system has been delivered and is live now.")
    sc.pre_send_guard(t, ctx("Is the reminder system ready?"))
    assert "delivered" not in t.reply and "suggestion" in t.reply and t.reply.count("?") == 1


def test_a_roman_urdu_reply_to_an_urdu_script_owner_becomes_urdu_script():
    t = turn_with("Theek hai, main aap ke liye ek system banata hoon. Kab tak chahiye?")
    sc.pre_send_guard(t, ctx("مجھے ایک ریمائنڈر سسٹم چاہیے", other="Urdu", lang=""))
    assert any("\u0600" <= ch <= "\u06ff" for ch in t.reply) and "Theek" not in t.reply


def test_a_clean_reply_in_the_owners_language_is_left_alone():
    reply = "Ji, yeh theek hai. Kab se shuru hua?"
    t = turn_with(reply)
    sc.pre_send_guard(t, ctx("Reminders late jate hain", lang="roman_ur"))
    assert t.reply == reply
