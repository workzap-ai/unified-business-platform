"""Platform spec v1.4, 17.3 (TS1-TS3, A44, G53): the active topic, parking, a second business."""

from types import SimpleNamespace
from typing import Any

from app.modules.pi import flow, topics, turn_state

FIRST = "Main locksmith hoon, dukan Lahore mein hai aur missed calls ka masla hai"
SECOND = "Mera ek aur karobar hai, lettuce farm, wahan paani ka masla hai"


def test_a_second_business_is_noted_labelled_and_asked_about() -> None:
    new, event = topics.observe(topics.Topics(), SECOND, [FIRST])
    assert event.kind == "second_business"
    assert [i["id"] for i in new.items] == ["b1", "b2"]
    assert new.items[0]["label"].startswith("Main locksmith")
    assert new.active == "b1" and new.pending
    assert "Pehle kis se shuru karein" in topics.note(event, new)


def test_the_same_message_twice_does_not_add_a_third_business() -> None:
    new, _ = topics.observe(topics.Topics(), SECOND, [FIRST])
    again, event = topics.observe(new, SECOND, [FIRST])
    assert len(again.items) == 2 and event.kind == "second_business"


def test_the_owner_steers_by_position_or_by_words_and_the_other_is_parked() -> None:
    state, _ = topics.observe(topics.Topics(), SECOND, [FIRST])
    after, event = topics.observe(state, "pehle lettuce farm se shuru karte hain", [FIRST])
    assert (event.kind, after.active, event.parked) == ("steered", "b2", "b1")
    assert not after.pending
    after, event = topics.observe(state, "dusra wala pehle", [FIRST])
    assert after.active == "b2"
    after, event = topics.observe(state, "pehla wala", [FIRST])
    assert after.active == "b1" and event.kind == "steered"


def test_an_unclear_answer_keeps_the_first_business_and_stops_asking() -> None:
    state, _ = topics.observe(topics.Topics(), SECOND, [FIRST])
    after, event = topics.observe(state, "hmm theek hai", [FIRST])
    assert (after.active, after.pending, event.kind) == ("b1", False, "none")


def test_the_owner_can_ask_to_go_back_to_the_old_business() -> None:
    state, _ = topics.observe(topics.Topics(), SECOND, [FIRST])
    state, _ = topics.observe(state, "dusra wala pehle", [FIRST])
    back, event = topics.observe(state, "chalo wapas pehle wale karobar par", [FIRST])
    assert (event.kind, back.active) == ("returned", "b1")


def test_a_plain_message_changes_nothing_and_a_switch_phrase_is_a_switch() -> None:
    same, event = topics.observe(topics.Topics(), "stock kam hai", [])
    assert event.kind == "none" and same.items == []
    _, event = topics.observe(topics.Topics(), "waise ek aur baat, rent bhi barh gaya", ["a"])
    assert event.kind == "switch"


def test_the_stored_state_round_trips_through_the_brief() -> None:
    state, _ = topics.observe(topics.Topics(), SECOND, [FIRST])
    assert topics.from_brief({"topics": state.to_dict()}).to_dict() == state.to_dict()
    assert topics.from_brief({"topics": "junk"}).items == []
    assert topics.from_brief(None).active is None


def test_the_reply_after_a_second_business_has_no_ideas_and_ends_in_the_question() -> None:
    event = topics.Event("second_business", "b2", "b1")
    ok = (
        "Paani ka masla farm par bhi wohi pattern hai. Dono karobar ke naqshe alag rakhte hain. "
        "Pehle kis se shuru karein?"
    )
    assert topics.reply_problem(event, ok, 0) is None
    assert "no ideas" in (topics.reply_problem(event, ok, 2) or "")
    assert "end with one question" in (topics.reply_problem(event, "Alag note kar liya.", 0) or "")
    assert topics.reply_problem(event, ok, 2, asked_for_ideas=True) is None


def test_after_a_switch_no_ideas_about_the_old_thread_unless_asked() -> None:
    event = topics.Event("switch", "b1")
    assert "parked" in (topics.reply_problem(event, "Rent ki baat.", 1) or "")
    assert topics.reply_problem(event, "Rent ki baat.", 0) is None
    assert topics.reply_problem(topics.Event("steered", "b2"), "Shuru karte hain.", 2) is None


def test_enter_stores_the_pointer_and_tells_the_model() -> None:
    c = SimpleNamespace(flow_state="S1_LISTENING", flow_state_since=None, service_brief={})
    ctx: dict[str, Any] = {}
    turn_state.enter(c, flow.State.S1_LISTENING, SECOND, [FIRST], ctx)
    assert c.service_brief["topics"]["pending"] is True
    assert ctx["topic_event"] == "second_business" and "Pehle kis se" in ctx["topic_note"]
    assert ctx["topic_active"] == "b1" and len(ctx["topics"]) == 2
    reply = "Noted. Count stock weekly.\n• one\n• two"
    assert turn_state.guard(reply, {**ctx, "latest_customer_message": SECOND}) is not None
