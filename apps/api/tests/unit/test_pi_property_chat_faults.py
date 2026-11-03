# ruff: noqa: E501
"""Faults from one live property-management chat (Roman Urdu, 2026-11-01)."""

import pytest

from app.modules.pi import decisions, flow, listening_tidy, problems
from app.modules.pi import service_conversation as sc


class FakeTurn:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self._summary = False
        self._board = False
        self._free = False
        self._decision = None
        self.request_human = False


def ctx(said: str = "", history: list[str] | None = None, **extra):
    return {
        "latest_customer_message": said,
        "history": [{"role": "customer", "text": t} for t in history or []],
        "flow": {"state": flow.State.S2_CLARIFYING.value},
        "reply_language": "roman_ur",
        **extra,
    }


# d) cost words on the owner's own money flow ------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        "tenant ki payment verify kaise hoti hai, property owner ko kitni payment deni hai ye kaise "
        "calculate hota hai",
        "partial balance kaise rakhte hain, owner ko kitna hissa dena hota hai",
        "how much rent is due to the property owner and how is it calculated",
        "kitna kiraya wasool hua ye kaise pata chalega",
    ],
)
def test_own_money_flow_is_not_a_cost_question(text: str) -> None:
    assert not decisions.cost_asked(text)


@pytest.mark.parametrize(
    "text",
    [
        "kitna kharcha aayega",
        "how much will it cost",
        "price kya hai",
        "aap ki qeemat kitni hai",
        "how much do you charge",
    ],
)
def test_true_cost_questions_still_work(text: str) -> None:
    assert decisions.cost_asked(text)


# a) summary keeps its bullets, no empty heading ----------------------------------------------------
def test_summary_survives_idea_shaping() -> None:
    items = [
        {"category": "money", "title": "rent wusooli"},
        {"category": "contact", "title": "tenant rabta"},
    ]
    reply = problems.summary_message(items, "roman_ur", ["rent software"])
    turn = FakeTurn(reply)
    turn._summary = True
    sc.shape_expert_ideas(turn, ctx(expert_on=True))
    assert turn.reply == reply
    assert "• rent wusooli" in turn.reply
    assert "• rent software" in turn.reply


def test_whole_business_owner_gets_no_pick_one_summary() -> None:
    said = "pehle meri poori business samajh lo, abhi solution nahi chahiye"
    assert listening_tidy.owner_declines_pick([said])


# b) empty labelled sections never print -----------------------------------------------------------
def test_recap_list_under_a_label_is_not_stripped() -> None:
    reply = "*Jo pata hai:*\n• 45 properties\n• apartments, houses, shops\n\n*Abhi unknown hai:* employees"
    turn = FakeTurn(reply)
    sc.shape_expert_ideas(turn, ctx(expert_on=True))
    assert "• 45 properties" in turn.reply


def test_empty_section_never_prints() -> None:
    text = "*Jo pata hai:* *Abhi unknown hai:* employees ki tadaad, agreements kahan hain."
    out = listening_tidy.drop_empty_sections(text)
    assert "Jo pata hai" not in out
    assert "employees ki tadaad" in out
    assert listening_tidy.drop_empty_sections("Heading:\n\n") == ""


# c) already answered choices ----------------------------------------------------------------------
def test_choice_question_the_owner_already_answered_is_dropped() -> None:
    owner = ["mere paas apartments, houses aur commercial shops hain, 45 properties"]
    reply = "Samajh gaya. Pehle kin properties se ye shuru karein: apartments, houses ya commercial shops?"
    assert listening_tidy.answered_questions(reply, owner)
    assert "?" not in listening_tidy.without_answered_questions(reply, owner)


def test_unanswered_choice_question_stays() -> None:
    reply = "Aap ke paas apartments, houses ya commercial shops hain?"
    assert not listening_tidy.answered_questions(reply, ["mere paas kuch properties hain"])


def test_pick_question_dropped_when_owner_wants_whole_business() -> None:
    owner = ["pehle meri poori business samajh lo, abhi solution nahi chahiye"]
    reply = "Samajh gaya. In mein se pehle kis par kaam shuru karein?"
    assert listening_tidy.answered_questions(reply, owner)


def test_tidy_replaces_dropped_question_with_one_question() -> None:
    owner = "mere paas apartments, houses aur commercial shops hain"
    turn = FakeTurn(
        "Theek hai. Pehle kin properties se ye shuru karein: apartments, houses ya commercial shops?"
    )
    sc.brain_listening_tidy(turn, ctx(owner))
    assert turn.reply.count("?") == 1
    assert "commercial shops?" not in turn.reply
    assert turn.reply.rstrip().endswith(("?", "؟"))


# e) a cause is never settled, and a reply always ends with one question ----------------------------
def test_settled_cause_sentence_goes_and_one_question_is_added() -> None:
    turn = FakeTurn(
        "Outstanding rent ka pata na chalna ab saaf hai: payment aati hai, lekin record mein nahi chadhti."
    )
    assert listening_tidy.settled_cause(turn.reply)
    sc.brain_listening_tidy(turn, ctx("employee entry bhool jata hai"))
    assert "saaf hai" not in turn.reply
    assert turn.reply.count("?") == 1
    assert turn.reply.rstrip().endswith(("?", "؟"))


def test_tidy_leaves_a_good_reply_alone() -> None:
    reply = "Tenant cash ya bank se deta hai. Payment kaun check karta hai?"
    turn = FakeTurn(reply)
    sc.brain_listening_tidy(turn, ctx("cash aur bank"))
    assert turn.reply == reply
