"""The Solution Box readiness signals B3, B4, B5 and B7 (platform spec Book 5, 5.4), derived from
the conversation, and that the offer rule then goes through, or stays shut when the box is off."""

import pytest

from app.modules.pi import box, box_signals, decisions
from app.modules.pi.flow import State

THREE = [
    {"since": "a year", "raised_voluntarily": True},
    {"impact": "cash"},
    {"cause": "price"},
]
UPSET = "mera dil dukhta hai, bohat pareshan hoon"


def _context(**more: object) -> dict[str, object]:
    base: dict[str, object] = {
        "noted_problems": THREE,
        "brief": {"map_reviewed": True, "ranked": True},
        "history": [{"role": "ai", "text": "hello"}] * 9,
    }
    return {**base, **more}


def test_every_signal_true_reaches_the_offer() -> None:
    facts = box.offer_facts(_context())
    assert facts.voluntary_count == 1 and facts.trust_trend == "steady" and not facts.upset
    assert box.can_offer(facts) == (True, "B", "B1 to B7 hold")
    d = decisions.decide(
        State.S4_SORTED_SUMMARY,
        "haan sahi hai",
        "roman_ur",
        {
            "problem_count": 3,
            "group_count": 1,
            "problem_refs": ["P1", "P2", "P3"],
            "box_offer": facts,
        },
    )
    assert d is not None and d.next_state == State.S5_READINESS


@pytest.mark.parametrize(
    ("brief", "held"),
    [({"ranked": True}, "B3"), ({"map_reviewed": True}, "B4")],
)
def test_a_missing_map_signal_holds_the_offer(brief: dict[str, bool], held: str) -> None:
    allowed, _, reason = box.can_offer(box.offer_facts(_context(brief=brief)))
    assert not allowed and reason.startswith(held)


def test_b5_comes_from_the_noted_problems_and_the_brief_only_overrides() -> None:
    none = [{"since": "a year"}, {"impact": "cash"}, {"cause": "price"}]
    assert box.offer_facts(_context(noted_problems=none)).voluntary_count == 0
    assert box.offer_facts(_context(noted_problems=THREE)).voluntary_count == 1
    allowed, _, reason = box.can_offer(box.offer_facts(_context(noted_problems=none)))
    assert not allowed and reason.startswith("B5")
    brief = {"map_reviewed": True, "ranked": True, "voluntary_problems": 2}
    assert box.offer_facts(_context(noted_problems=none, brief=brief)).voluntary_count == 2


def test_a_rank_set_on_the_portal_counts_as_ranked_without_the_brief_key() -> None:
    noted = [{**THREE[0], "rank": 1}, *THREE[1:]]
    facts = box.offer_facts(_context(noted_problems=noted, brief={"map_reviewed": True}))
    assert facts.ranked and box.can_offer(facts)[0]


def test_b7_is_steady_and_calm_unless_thinking_is_on() -> None:
    plain = box.offer_facts(_context(latest_customer_message=UPSET))
    assert plain.trust_trend == "steady" and plain.upset is False


def test_b7_upset_comes_from_the_dials_when_thinking_is_on() -> None:
    facts = box.offer_facts(_context(thinking=True, latest_customer_message=UPSET))
    assert facts.upset is True
    allowed, _, reason = box.can_offer(facts)
    assert not allowed and reason == "B7: the owner is upset"


def test_b7_trust_follows_the_dials_and_a_brief_key_overrides() -> None:
    history = [{"role": "customer", "text": t} for t in ("ok", "hello")]
    steady = box_signals.trust_and_upset(_context(thinking=True, history=history))
    assert steady == ("steady", False)
    forced = box_signals.trust_and_upset(
        _context(thinking=True, history=history, brief={"trust_trend": "falling", "upset": True})
    )
    assert forced == ("falling", True)
    falling = {"map_reviewed": True, "ranked": True, "trust_trend": "falling"}
    assert not box.can_offer(box.offer_facts(_context(brief=falling)))[0]


def test_the_box_off_gate_ignores_the_signals() -> None:
    from app.modules.pi import service_conversation as svc

    assert box.box_offer_enabled({"pi_mode": "brain"}) is False
    assert svc.box_offer_allowed({"noted_problems": [], "brief": {}}) is True


@pytest.mark.parametrize(
    "said",
    [
        "sahi hai",
        "yes that is right",
        "ok",
        "haan",
        "theek hai",
        "P2 is wrong, it is cash",
        "lekin yeh jorr ghalat hai",
    ],
)
def test_a_reply_after_the_map_that_confirms_or_changes_it_is_b3(said: str) -> None:
    assert box_signals.confirms_or_changes_map(said)


@pytest.mark.parametrize("said", ["", "kitna kharcha hoga?", "hmm", "what is this"])
def test_other_replies_do_not_review_the_map(said: str) -> None:
    assert not box_signals.confirms_or_changes_map(said)


@pytest.mark.parametrize(
    "said",
    [
        "start with the first",
        "pehle ye",
        "pehle ye wala masla",
        "sab se pehle P2",
        "start with P3",
        "isi se shuru karo",
    ],
)
def test_where_to_start_is_b4(said: str) -> None:
    assert box_signals.says_start_here(said)


@pytest.mark.parametrize("said", ["ok", "the first time it happened was 2019", "pehle bhi hua tha"])
def test_other_words_are_not_where_to_start(said: str) -> None:
    assert not box_signals.says_start_here(said)


def test_rank_tags() -> None:
    tags = ["parked", "rank:2"]
    assert box_signals.rank_of(tags) == 2 and box_signals.rank_of(["parked"]) is None
    assert box_signals.with_rank(tags, 1) == ["parked", "rank:1"]
    assert box_signals.with_rank(tags, None) == ["parked"]
    assert box_signals.rank_of(["rank:0", "rank:x", "rank:99"]) is None
