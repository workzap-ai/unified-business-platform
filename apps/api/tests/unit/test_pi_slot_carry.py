"""S4 (B6 root cause 1): what carries from an owner's earlier chat into a new one, and what not.

Only pi's own questions that the owner answered (closed slots) and, briefly, the facts pi asked for
and got no answer to travel. No word the owner wrote, no summary, no requirements, no generic
"anything else?", nothing stale, and nothing that holds personal data."""

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.pi import slot_carry

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
FRESH = NOW - timedelta(days=3)


def brief(**extra):
    return {"closed_slots": [{"slot": "shops.where", "q": "Which shop is it?"}], **extra}


def test_a_recent_answered_question_is_carried_and_marked() -> None:
    out = slot_carry.carried([(brief(), FRESH)], NOW)
    assert out["closed_slots"] == [
        {"slot": "shops.where", "q": "Which shop is it?", "carried": True}
    ]


def test_only_closed_slots_and_asked_facts_are_ever_copied() -> None:
    private = brief(
        requirements={"service": "Website"},
        customer_profile={"name": "Ali", "phone": "0300 1234567"},
        last_question={"slot": "x", "q": "What is your cash balance?"},
        open_requests=[{"id": "1"}],
        asked_facts=["business_name"],
        summary="owner said his brother steals",
        missing=["budget"],
    )
    out = slot_carry.carried([(private, NOW - timedelta(hours=5))], NOW)
    assert set(out) <= {"closed_slots", "asked_facts"}
    assert "Ali" not in str(out) and "brother" not in str(out) and "cash balance" not in str(out)


def test_the_generic_anything_else_slot_is_never_carried() -> None:
    previous = brief(
        closed_slots=[
            {"slot": "anything_else", "q": "Anything else getting in the way?"},
            {"slot": "shops.where", "q": "Which shop is it?"},
        ]
    )
    out = slot_carry.carried([(previous, FRESH)], NOW)
    assert [c["slot"] for c in out["closed_slots"]] == ["shops.where"]


def test_a_question_older_than_the_window_is_not_carried() -> None:
    stale = NOW - timedelta(days=slot_carry.CARRY_SLOTS_DAYS + 1)
    assert slot_carry.carried([(brief(), stale)], NOW) == {}


def test_an_unknown_age_is_not_carried() -> None:
    assert slot_carry.carried([(brief(), None)], NOW) == {}


@pytest.mark.parametrize(
    "q",
    [
        "Is 0300 1234567 your number?",
        "Is ali@example.com your email?",
        "Is 4111 1111 1111 1111 your card?",
        "Is 35202-1234567-1 your ID?",
    ],
)
def test_a_question_that_holds_personal_data_is_dropped(q: str) -> None:
    previous = brief(
        closed_slots=[{"slot": "x", "q": q}, {"slot": "shops.where", "q": "Which shop?"}]
    )
    out = slot_carry.carried([(previous, FRESH)], NOW)
    assert [c["q"] for c in out["closed_slots"]] == ["Which shop?"]


def test_an_erased_or_empty_brief_carries_nothing() -> None:
    assert slot_carry.carried([({"erased": True}, FRESH), ({}, FRESH)], NOW) == {}


def test_malformed_entries_are_ignored() -> None:
    previous = {"closed_slots": ["text", {"slot": 5}, {"q": 7}, {"slot": "a", "q": ""}, None]}
    assert slot_carry.carried([(previous, FRESH)], NOW) == {}


def test_newest_first_deduplicated_and_capped() -> None:
    newest = brief(closed_slots=[{"slot": "shops.where", "q": "Which shop is it?"}])
    older = brief(
        closed_slots=[
            {"slot": "shops.where", "q": "Which shop is it?"},
            *(
                {"slot": f"s{n}", "q": f"What about thing number {n} here today?"}
                for n in range(40)
            ),
        ]
    )
    out = slot_carry.carried([(newest, FRESH), (older, FRESH - timedelta(days=2))], NOW)
    slots = [c["slot"] for c in out["closed_slots"]]
    assert slots.count("shops.where") == 1 and len(slots) <= slot_carry.MAX_SLOTS


def test_asked_facts_carry_briefly_and_only_known_keys() -> None:
    previous = brief(asked_facts=["business_name", "location", "my_secret_key"])
    recent = NOW - timedelta(hours=20)
    assert slot_carry.carried([(previous, recent)], NOW)["asked_facts"] == [
        "business_name",
        "location",
    ]
    old = NOW - timedelta(days=slot_carry.CARRY_ASKED_DAYS + 1)
    assert "asked_facts" not in slot_carry.carried([(previous, old)], NOW)
