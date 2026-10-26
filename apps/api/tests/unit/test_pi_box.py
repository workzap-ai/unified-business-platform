import dataclasses

import pytest

from app.modules.pi import box
from app.modules.pi.box import OfferFacts, can_move, can_offer

READY = OfferFacts(
    problem_count=4,
    understood_count=3,
    map_reviewed=True,
    ranked=True,
    voluntary_count=2,
    pi_message_count=9,
)


def test_ready_facts_allow_b() -> None:
    assert can_offer(READY) == (True, "B", "B1 to B7 hold")


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"problem_count": 2}, "B1"),
        ({"understood_count": 1}, "B2"),
        ({"map_reviewed": False}, "B3"),
        ({"ranked": False}, "B4"),
        ({"voluntary_count": 0}, "B5"),
        ({"pi_message_count": 7}, "B6"),
        ({"trust_trend": "falling"}, "B7"),
        ({"upset": True}, "B7"),
        ({"declined_recently": True}, "B7"),
        ({"main_cause_known": False}, "never offer"),
        ({"just_corrected": True}, "never offer"),
        ({"in_a_hurry": True}, "never offer"),
    ],
)
def test_each_condition_blocks(change: dict[str, object], code: str) -> None:
    allowed, rule, reason = can_offer(dataclasses.replace(READY, **change))  # type: ignore[arg-type]
    assert (allowed, rule) == (False, "B")
    assert reason.startswith(code)


def test_no_others_replaces_three_problems() -> None:
    facts = dataclasses.replace(READY, problem_count=2, no_other_problems=True)
    assert can_offer(facts)[0] is True


@pytest.mark.parametrize(
    ("field", "rule"),
    [
        ("asked_for_document_or_price", "R1"),
        ("said_yes", "R2"),
        ("asked_who_or_how_long", "R3"),
    ],
)
def test_exceptions_always_honoured(field: str, rule: str) -> None:
    # even on an empty map, an upset owner and a recent decline
    facts = OfferFacts(upset=True, declined_recently=True, trust_trend="falling", **{field: True})  # type: ignore[arg-type]
    allowed, got, _ = can_offer(facts)
    assert (allowed, got) == (True, rule)


def test_empty_facts_blocked() -> None:
    assert can_offer(OfferFacts())[0] is False


def test_flag_needs_brain_and_true() -> None:
    assert box.box_offer_enabled(None) is False
    assert box.box_offer_enabled({"pi_mode": "brain"}) is False
    assert box.box_offer_enabled({"pi_mode": "brain", "brain": {"box_offer": "yes"}}) is False
    assert box.box_offer_enabled({"brain": {"box_offer": True}}) is False
    assert box.box_offer_enabled({"pi_mode": "brain", "brain": {"box_offer": True}}) is True


def test_happy_path_transitions() -> None:
    path = [
        ("collecting", "ready", "pi"),
        ("ready", "offered", "pi"),
        ("offered", "drafting", "pi"),
        ("drafting", "in_review", "pi"),
        ("in_review", "sent", "staff"),
        ("sent", "accepted", "owner"),
    ]
    for current, target, actor in path:
        assert can_move(current, target, actor)[0], (current, target)


def test_only_staff_can_send() -> None:
    for actor in ("pi", "owner"):
        assert can_move("in_review", "sent", actor)[0] is False
    assert can_move("in_review", "sent", "staff")[0] is True


def test_decline_returns_to_collecting() -> None:
    assert can_move("offered", "collecting", "owner")[0]
    assert can_move("sent", "declined", "owner")[0]
    assert can_move("declined", "collecting", "pi")[0]


def test_illegal_moves() -> None:
    assert can_move("collecting", "sent", "staff")[0] is False
    assert can_move("collecting", "drafting", "pi")[0] is False
    assert can_move("accepted", "collecting", "pi")[0] is False
    assert can_move("sent", "accepted", "pi")[0] is False  # the owner or staff answer
    assert can_move("nope", "ready", "pi")[0] is False
    assert can_move("collecting", "ready", "robot")[0] is False


def test_revision_after_send() -> None:
    assert can_move("sent", "revised", "pi")[0]
    assert can_move("revised", "in_review", "pi")[0]
    assert box.legal_targets("revised") == ("in_review",)


def test_value_line_two_ideas_each() -> None:
    ok, why = box.value_line(
        {
            "P1": [
                "Count the stock once a week, so you see what is stuck",
                "Put the oldest stock at the front, so it sells first",
            ]
        }
    )
    assert ok, why


def test_value_line_failures() -> None:
    ok, why = box.value_line({"P1": ["Count the stock once a week, so you see what is stuck"]})
    assert not ok and "needs 2" in why[0]
    ok, why = box.value_line({"P1": ["Count weekly", "Install a tool, step 1: open settings"]})
    assert not ok
    assert box.value_line({})[0] is False
