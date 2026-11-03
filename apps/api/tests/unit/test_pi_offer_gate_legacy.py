"""Audit R8 and R9: the offer is gated by canOffer even with response_rules.brain.box_offer off
(only R1 passes there), a model-written offer is cut when it is not allowed, "You can say no" is
removed, and "Alag note kar li" counts as a noting opener.

OF1: legacy path, owner did not ask -> no offer. OF2: legacy path, owner asked for a quote -> offer.
OF3: Solution Box on, B1 to B7 not met -> blocked; R1 still passes. OF4: a model-written offer is
removed from the reply when not allowed, kept when allowed."""

from app.modules.pi import constitution, decisions, reply_gates
from app.modules.pi import service_conversation as sc
from app.modules.pi.flow import State


def ctx(said: str, **extra):
    return {"latest_customer_message": said, "noted_problems": [{}, {}, {}, {}], **extra}


def turn_with(reply: str):
    return sc.ServiceTurn(reply=reply)


OFFER = "Shall I get one solution document and a quote made for all of these together?"


def test_of1_legacy_offer_blocked_when_not_asked() -> None:
    assert sc.box_offer_allowed(ctx("sales are falling, what can I do?")) is False


def test_of2_legacy_offer_allowed_when_owner_asks_for_quote() -> None:
    assert sc.box_offer_allowed(ctx("send me a quote for this")) is True


def test_of3_box_on_blocked_until_ready_but_r1_passes() -> None:
    on = {"box_offer": True}
    assert sc.box_offer_allowed(ctx("sales are falling", **on)) is False
    assert sc.box_offer_allowed(ctx("send me a quote for this", **on)) is True


def test_of4_model_written_offer_is_removed_when_not_allowed() -> None:
    turn = turn_with(f"Track which shop sells out first. {OFFER} You can say no.")
    sc.strip_unallowed_offer(turn, ctx("sales are falling"))
    assert "solution document" not in turn.reply
    assert "say no" not in turn.reply.lower()
    assert turn.reply.startswith("Track which shop")


def test_of4_offer_kept_when_allowed_but_say_no_removed() -> None:
    turn = turn_with(f"Track which shop sells out first. {OFFER} You can say no.")
    sc.strip_unallowed_offer(turn, ctx("send me a quote please"))
    assert "solution document" in turn.reply
    assert "say no" not in turn.reply.lower()


def test_s4_summary_accepted_does_not_offer_without_request() -> None:
    facts = {"problem_count": 4, "group_count": 2, "message_id": "m1"}
    got = decisions.decide(State.S4_SORTED_SUMMARY, "yes that is right", "en", facts)
    assert got is None or got.reply is None


def test_alag_note_kar_li_is_an_opener() -> None:
    assert reply_gates.empty_opener("Alag note kar li hai. Kitne orders?")
    assert constitution.ACK_OPENER.match("Alag note kar li hai. Kitne orders?")
    assert constitution.NOTED_START.match("Alag note kar li hai.")
