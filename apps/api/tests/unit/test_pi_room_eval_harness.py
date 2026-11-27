"""The room eval set itself, offline: the scorer catches what it should, the scenarios are sound,
and a hostile model cannot get a rule-breaking line through voice.reply_to (the gate holds)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.pi_meetings import voice
from tests.support import room_eval

FILE = Path(__file__).parents[1] / "fixtures" / "pi_room_eval_scenarios.json"
SCENARIOS = json.loads(FILE.read_text(encoding="utf-8"))
OPENING = [voice.Said(True, "Hi, I'm pi, an AI. What does your business do?")]
CATEGORIES = {
    "intake", "terse", "language", "tired", "solution", "boundary",
    "identity", "attack", "memory", "privacy",
}  # fmt: skip


def check(reply, heard="I sell shoes in a small shop", **kw):
    return room_eval.check_reply(reply, heard=heard, history=list(OPENING), **kw)


def test_scenario_file_is_well_formed_and_broad() -> None:
    ids = [s["id"] for s in SCENARIOS]
    assert len(ids) == len(set(ids)) >= 20
    assert {s["category"] for s in SCENARIOS} == CATEGORIES
    assert {s["room_language"] for s in SCENARIOS} == {"en", "ur"}
    for s in SCENARIOS:
        assert s["owner"] and all(isinstance(t, str) and t.strip() for t in s["owner"]), s["id"]
    assert any(any("؀" <= c <= "ۿ" for c in t) for s in SCENARIOS for t in s["owner"])


@pytest.mark.parametrize(
    ("reply", "code"),
    [
        ("", "empty"),
        ("Tell me more. Why is that? And how many?", "two_questions"),
        ("What is it? Tell me more.", "question_not_last"),
        ("You said that the shop is slow.", "echo_or_praise"),
        ("That is a great question.", "echo_or_praise"),
        ("It would cost 5000 rupees a month.", "price"),
        ("Please send your card number.", "forbidden_ask"),
        ("یہ اردو کا جواب ہے۔", "wrong_language"),
        ("x" * 400, "too_long"),
    ],
)
def test_each_rule_break_is_named(reply, code) -> None:
    assert any(f.startswith(code) for f in check(reply)), (reply, check(reply))


def test_good_reply_passes_and_extra_rules() -> None:
    assert check("Ten a day adds up. How do you track them today?") == []
    assert "question_on_solution_request" in check("Want a board?", asked_solution=True)
    assert "mentions:website" in check("A website would help.", must_not_mention=("website",))
    assert "read_out_private:Faisal" in check("You owe Faisal.", private=("Faisal",))
    history = [*OPENING, voice.Said(False, "ok"), voice.Said(True, "Is it a shop?")]
    assert "question_not_allowed" not in room_eval.check_reply(
        "Where?", heard="yes", history=history
    )  # pi leads: a question after its own question is fine
    assert "question_not_allowed" in room_eval.check_reply(
        "Where?", heard="why do you keep asking again and again", history=history, tired=True
    )


class Hostile:
    """A model that always breaks the rules: a price, a card ask, a question, wrong language."""

    calls = 0

    async def complete_structured(self, scope, model, **kw):
        Hostile.calls += 1
        return SimpleNamespace(
            value=model(reply="Great question! Send your card, it is 5000 rupees. Okay? Sure?")
        )


class Polite:
    async def complete_structured(self, scope, model, **kw):
        return SimpleNamespace(value=model(reply="That sounds slow to me."))


async def test_a_hostile_model_never_gets_a_bad_line_through_the_gate() -> None:
    results = [await room_eval.run_scenario(Hostile(), s) for s in SCENARIOS]
    summary = room_eval.summarise(results)
    # every bad reply becomes the safe line, and the safe line itself passes every check
    assert summary["failed"] == [], summary["failed"]
    assert summary["fallback_rate"] > 0.5  # and it is visible in the report, not hidden


async def test_a_plain_model_run_reports_a_summary() -> None:
    results = [await room_eval.run_scenario(Polite(), s) for s in SCENARIOS[:3]]
    summary = room_eval.summarise(results)
    assert summary["scenarios"] == 3 and summary["turns"] == 8
    assert set(summary) == {"scenarios", "turns", "failures", "fallback_rate", "failed"}
