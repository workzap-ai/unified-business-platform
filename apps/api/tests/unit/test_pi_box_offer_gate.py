"""The Solution Box offer rule in the conversation (platform spec Book 5, 5.4): off by default
(no offer of its own), and when on, pi's own offer waits for R1 to R3 or B1 to B7."""

from app.modules.pi import box, decisions
from app.modules.pi.flow import State

SUMMARY_OK = "haan sahi hai"


def _facts(**more: object) -> dict[str, object]:
    return {"problem_count": 2, "group_count": 1, "problem_refs": ["P1", "P2"], **more}


def test_with_the_box_off_the_summary_makes_no_offer() -> None:
    # Book 5 Part 14: accepting the summary is no longer an offer trigger on its own.
    assert decisions.decide(State.S4_SORTED_SUMMARY, SUMMARY_OK, "roman_ur", _facts()) is None


def test_with_the_box_on_two_problems_and_no_map_review_hold_the_offer_back() -> None:
    ctx = {"noted_problems": [{"since": "a year"}, {}], "brief": {}, "history": []}
    d = decisions.decide(
        State.S4_SORTED_SUMMARY, SUMMARY_OK, "roman_ur", _facts(box_offer=box.offer_facts(ctx))
    )
    assert d is not None and d.reply is None and d.next_state is None
    assert d.why.startswith("B-blocked: B1")


def test_with_the_box_on_every_condition_met_the_offer_is_made() -> None:
    ctx = {
        "noted_problems": [{"since": "a year"}, {"impact": "cash"}, {"cause": "price"}],
        "brief": {"map_reviewed": True, "ranked": True, "voluntary_problems": 1},
        "history": [{"role": "ai"}] * 9,
    }
    d = decisions.decide(
        State.S4_SORTED_SUMMARY, SUMMARY_OK, "roman_ur", _facts(box_offer=box.offer_facts(ctx))
    )
    assert d is not None and d.next_state == State.S5_READINESS


def test_a_direct_request_for_the_document_is_never_held_back() -> None:
    facts = _facts(box_offer=box.offer_facts({"noted_problems": [{}], "brief": {}}))
    d = decisions.decide(State.S4_SORTED_SUMMARY, "quote bhej dein", "roman_ur", facts)
    assert d is not None and d.why != "" and "blocked" not in d.why
