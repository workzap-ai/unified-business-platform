# ruff: noqa: E501
"""Live chat of 2026-10-27 (a distributor with crores of stock and no visibility, Roman Urdu): the
owner asked for help three times without the word "solution" and pi kept asking questions. Their exact
messages are asks; their statements about the problem are not."""

from types import SimpleNamespace

import pytest

from app.modules.pi import ask_classifier, slots, solution_ask, solution_context

M12 = "Mujhe yeh bhi nahi pata ke sales staff kitni dukaanon par visit karta hai, kitne orders lata hai aur kitna stock unke paas hota hai. Mere paas taqreeban 6 se 10 crore ki inventory hai, lekin sales, warehouse aur accounts ka apas mein koi proper connection nahi hai. Mujhe samajh nahi aa raha ke in sab ko control kaise karun."
M14 = "Nahi, koi proper target ya visit report nahi hai. Har salesman apni marzi se kaam karta hai. Main chahta hoon ke mujhe sab kuch apne mobile se nazar aaye, lekin mujhe samajh nahi aa raha ke aisa system kaise banega."
M16 = "Sab se zyada nuqsan ka exact pata hi nahi hai, kyun ke mere paas proper records nahi hain. Mujhe shak hai ke sales miss ho rahi hain, stock ka hisaab theek nahi aur staff ko monitor karne ka koi tareeqa nahi. Isi liye main chahta hoon ke aap mujhe samjhayen ke is situation ko control karne ke liye kya system banana chahiye."
STATEMENTS = [
    "Sale mai hai. Mera sales staff bohat tang kar raha hai mujhay. Subah say gaib rehta hai. Dophir ko phone uthatay hain toh pata chalta hai beemar hain sub.",
    "Uskay baad koi inventory ka hisaab nahi. Shayd 6 say 10 crore ki inventory hai",
    "Sub alag alag dept kaam kar rahay hain",
    "Koi joor nahi hai",
    "Maslay bohat hain",
    "Mujhe samajh nahi aa raha ye kyun ho raha hai",
    "Mere customers ko ye system pasand nahi aaya, wo control kaise karte hain pata nahi",
]


@pytest.mark.parametrize("said", [M12, M14, M16])
def test_an_owner_who_is_lost_and_asks_how_to_control_it_has_asked_for_help(said: str) -> None:
    assert solution_ask.asked_for_ideas(said)


@pytest.mark.parametrize("said", STATEMENTS)
def test_describing_the_problem_is_not_an_ask(said: str) -> None:
    assert not solution_ask.asked_for_ideas(said)


@pytest.mark.parametrize(
    "said",
    [
        "in sab ko control kaise karun",
        "aisa system kaise banega",
        "kya system banana chahiye",
        "mujhe samjhayen",
        "How do I control all this?",
        "what system should I build for this",
        "مجھے سمجھ نہیں آ رہا یہ سب کیسے کنٹرول کروں",
        "मुझे समझ नहीं आ रहा कि इसे कैसे ठीक करूं",
    ],
)
def test_the_short_ways_to_ask_in_four_languages(said: str) -> None:
    assert solution_ask.asked_for_ideas(said)


def test_the_expert_answers_each_of_these_asks_instead_of_another_question() -> None:
    conversation = SimpleNamespace(flow_state="S1_LISTENING", service_brief={})
    noted = [{"title": "Sales staff absent"}, {"title": "No inventory record"}]
    for said in (M12, M14, M16):
        held = solution_context._expert_hold(conversation, said, noted, False)  # type: ignore[arg-type]
        assert held is not None and held["solution_why"] == "expert"


def test_a_message_that_answers_and_asks_still_closes_the_open_question() -> None:
    """The slot logic must not reopen a question the owner answered because the same message also
    asked for help (the reason a question could be asked twice)."""
    question = "Is mein sab se zyada nuqsan kis baat ka ho raha hai?"
    previous = {"last_question": {"slot": "biggest_loss", "q": question}}
    closed, _opened = slots.advance(previous, M16, "Kuch aur poochna hai?", "other")
    assert slots.asked_again("biggest_loss", question, closed) == question


def test_the_classifier_still_stays_out_of_plain_statements() -> None:
    assert not ask_classifier.needed("Sub alag alag dept kaam kar rahay hain", "S1_LISTENING")


# --- the repeated question was the safe fallback line itself ------------------------------------


def fallback_context(history: list[dict[str, str]]) -> dict:
    return {
        "pi_mode": "brain",
        "flow": {"state": "S1_LISTENING"},
        "reply_language": "roman_ur",
        "latest_customer_message": M16,
        "history": history,
    }


def test_the_safe_line_is_never_the_same_question_twice_in_a_chat() -> None:
    from app.modules.pi import constitution

    history = [{"role": "ai", "text": "Hi, main pi hoon, Workzap ka AI. Kia haal hain?"}]
    seen: list[str] = []
    for _ in range(4):
        line = constitution.safe_fallback(fallback_context(history))
        assert line not in seen, (line, seen)
        seen.append(line)
        history = [*history, {"role": "ai", "text": line}, {"role": "customer", "text": "jawab"}]
    assert seen[0] == constitution.FALLBACK_LISTENING["roman_ur"]  # the first time is unchanged


def test_when_every_safe_question_was_asked_the_next_slot_question_or_the_standard_one_follows() -> (
    None
):
    from app.modules.pi import constitution

    asked = [
        constitution.FALLBACK_LISTENING["roman_ur"],
        *constitution.FALLBACK_LISTENING_MORE["roman_ur"],
    ]
    history = [{"role": "ai", "text": q} for q in asked]
    line = constitution.safe_fallback(fallback_context(history))
    assert line.endswith("?")


def test_the_safe_lines_exist_in_every_language_the_fallback_has() -> None:
    from app.modules.pi import constitution

    for language in constitution.FALLBACK_LISTENING:
        assert len(constitution.FALLBACK_LISTENING_MORE[language]) == 3
