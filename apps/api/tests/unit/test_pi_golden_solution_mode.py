"""Book 2 (Solution Mode) golden phrases G17-G24 at the level the code decides them: whether an ask
is recognised, how pi opens, what a cost question or a "tried it" gets. The wording of the reply
itself comes from the model and needs a real-model run."""

import pytest

from app.modules.pi import decisions, solution_ask, solution_score
from app.modules.pi.flow import State
from app.modules.pi.service_conversation import ideas_opener


def test_g17_an_impatient_ask_gets_an_apology_then_the_ideas() -> None:
    said = "seedha batao, time nahi hai"
    assert solution_ask.asked_for_ideas(said) and solution_ask.impatient(said)
    assert ideas_opener({"latest_customer_message": said}).startswith("Sorry")


def test_g18_an_owner_about_to_leave_is_reassured_and_given_ideas() -> None:
    said = "rehne do, koi aur dekh leta hoon"
    assert solution_ask.asked_for_ideas(said) and solution_ask.churn_risk(said)
    assert ideas_opener({"latest_customer_message": said}).startswith("No pressure")


@pytest.mark.parametrize("said", ["rehne do", "not interested", "forget it"])
def test_g18_a_plain_no_is_not_mistaken_for_leaving(said: str) -> None:
    assert not solution_ask.churn_risk(said)


def test_g19_what_do_you_do_is_answered_not_ignored() -> None:
    assert solution_ask.asked_for_ideas("aap log karte kya ho?")


def test_g20_a_cost_question_is_a_cost_question_and_never_an_idea_ask() -> None:
    assert decisions.cost_asked("kitna kharcha aayega?")
    assert not solution_ask.asked_for_ideas("kitna kharcha aayega?")


def test_g21_a_capability_question_jumps_to_what_workzap_builds() -> None:
    assert solution_ask.asked_for_ideas("mujhe bas batao aap kya bana sakte ho")


def test_g23_an_idea_already_in_use_is_noted_so_a_different_one_follows() -> None:
    reaction = solution_score.classify("Google Maps pehle se hai")
    assert reaction is not None and reaction.signal == "idea_already_doing"


def test_g24_a_new_ask_after_a_declined_quote_gets_ideas_without_a_new_offer() -> None:
    assert solution_ask.asked_for_ideas("koi aur idea?")
    facts = {"problem_count": 2, "group_count": 1, "problem_refs": ["a", "b"], "brief": {}}
    decided = decisions.decide(State.S5B_DECLINED, "koi aur idea?", "roman_ur", facts)
    assert decided is None or decided.next_state != State.S5_READINESS


def test_g22_two_problems_and_no_request_start_no_ideas() -> None:
    said = "mera staff late aata hai aur sales kam hain"
    assert not solution_ask.asked_for_ideas(said)
