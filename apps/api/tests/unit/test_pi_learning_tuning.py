"""Settings tuning (spec 8.5 job 7): one step, once a week, undone when a guardrail rises."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.modules.pi import brain_config, learning_rules, learning_tuning

NOW = datetime(2026, 10, 23, 3, 0, tzinfo=UTC)


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, row: object) -> None:
        self.added.append(row)


def rates(reward: float = 1.0, **extra: float) -> learning_rules.Rates:
    return learning_rules.Rates(conversations=100, reward=reward, **extra)


def change(kind: str, key: str, before: int, after: int, direction: int, days_ago: int):
    return SimpleNamespace(
        kind=kind,
        created_at=NOW - timedelta(days=days_ago),
        before={"key": key, "value": before, "direction": direction},
        after={"key": key, "value": after, "direction": direction},
    )


@pytest.fixture
def wire(monkeypatch):
    def go(latest, windows):
        async def fake_latest(session, scope):
            return latest

        calls = iter(windows)

        async def fake_rates(session, scope, start, end):
            return next(calls)

        monkeypatch.setattr(learning_tuning, "_latest", fake_latest)
        monkeypatch.setattr(learning_tuning, "_rates", fake_rates)

    return go


async def run(settings):
    session = FakeSession()
    out = await learning_tuning.tune(
        session, SimpleNamespace(tenant_id=1, environment_id=1), settings, NOW
    )
    return out, session


async def test_the_first_step_needs_a_week_of_data_and_moves_one_step(wire):
    settings = SimpleNamespace(response_rules={})
    wire({}, [None] * 5)
    out, session = await run(settings)
    assert out == {"tuned": None} and not session.added  # no data, nothing moves
    wire({}, [rates()])
    out, session = await run(settings)
    assert out["tuned"] == "debounce_seconds" and out["to"] == out["from"] + 1
    assert settings.response_rules["brain"]["debounce_seconds"] == out["to"]
    assert session.added[0].kind == "setting_tuned"


async def test_a_step_is_undone_when_a_guardrail_rose(wire):
    key = "debounce_seconds"
    default = brain_config.TUNABLES[key][0]
    settings = SimpleNamespace(response_rules={"brain": {key: default + 1}})
    latest = {key: change("setting_tuned", key, default, default + 1, +1, days_ago=29)}
    wire(latest, [rates(1.0), rates(1.5, opt_out=0.05)])
    out, session = await run(settings)
    assert out["reverted"] == key and out["to"] == default
    assert settings.response_rules["brain"][key] == default
    assert session.added[0].kind == "setting_reverted"
    assert session.added[0].after["direction"] == -1  # the next try goes the other way


async def test_a_step_stays_and_continues_when_nothing_got_worse(wire):
    key = "debounce_seconds"
    default = brain_config.TUNABLES[key][0]
    settings = SimpleNamespace(response_rules={"brain": {key: default + 1}})
    latest = {key: change("setting_tuned", key, default, default + 1, +1, days_ago=29)}
    wire(latest, [rates(1.0), rates(1.2)])
    out, _ = await run(settings)
    assert out == {"tuned": key, "from": default + 1, "to": default + 2}


async def test_nothing_moves_inside_the_first_week_or_past_the_range(wire):
    key = "debounce_seconds"
    high = brain_config.TUNABLES[key][2]
    all_recent = {
        k: change("setting_tuned", k, 1, 2, +1, days_ago=2) for k in learning_tuning.TUNED
    }
    wire(all_recent, [])
    out, session = await run(SimpleNamespace(response_rules={}))
    assert out == {"tuned": None, "waiting": True} and not session.added
    top = {k: change("setting_reverted", k, 1, 2, +1, days_ago=9) for k in learning_tuning.TUNED}
    settings = SimpleNamespace(
        response_rules={"brain": {k: brain_config.TUNABLES[k][2] for k in learning_tuning.TUNED}}
    )
    wire(top, [rates()] * 10)
    out, _ = await run(settings)
    assert out == {"tuned": None}
    assert high >= brain_config.TUNABLES[key][1]


def test_no_rule_setting_can_be_tuned():
    assert set(learning_tuning.TUNED) <= set(brain_config.TUNABLES)
    for never in ("max_clarify", "redisclose_days", "canary_percent", "summary_trigger"):
        assert never not in learning_tuning.TUNED


def test_the_grader_needs_all_twelve_scores_and_any_rule_break_excludes():
    from app.modules.pi import learning_grader as g

    assert g.interpret(g.Grading(scores=[2.0] * 5)) is None  # a short answer is not trusted
    ok = g.interpret(g.Grading(scores=[2.0] * 11))
    assert ok is not None and ok.mean == 2.0 and not ok.rule_break
    broke = g.interpret(
        g.Grading(scores=[1.0] * 11, rule_break_items=[3, 99], rule_break_notes=["quoted a price"])
    )
    assert broke is not None and broke.rule_break and broke.mean == 1.0
    assert broke.reasons == [
        "#3 No solution, offer or pitch before readiness: quoted a price",
        "#99 not a rubric item",  # an unknown number is still a break: doubt fails closed
    ]
    many = g.interpret(g.Grading(scores=[2.0] * 11, rule_break_items=[2] * 40))
    assert many is not None and many.rule_break and len(many.reasons) == 1  # not thrown away
    assert "any doubt counts as a break" in g.SYSTEM
    clamped = g.interpret(g.Grading(scores=[9.0] * 11))
    assert clamped is not None and clamped.mean == 2.0
    assert g.switched_on({"brain": {"grader": True}}) and not g.switched_on({"brain": {}})
    assert not g.switched_on({"brain": {"grader": "yes"}})


async def test_a_value_set_by_hand_is_not_undone(wire):
    key = "debounce_seconds"
    default = brain_config.TUNABLES[key][0]
    settings = SimpleNamespace(response_rules={"brain": {key: default + 3}})  # staff chose this
    latest = {key: change("setting_tuned", key, default, default + 1, +1, days_ago=29)}
    wire(latest, [rates(1.0), rates(0.2, opt_out=0.2)])
    out, session = await run(settings)
    assert out == {"tuned": None, "left_alone": key}
    assert settings.response_rules["brain"][key] == default + 3
    assert [r.kind for r in session.added] == ["setting_reverted"]  # the trial is closed


def test_a_change_needs_as_many_conversations_as_a_canary_and_four_weeks():
    assert learning_tuning.MIN_CONVERSATIONS == learning_rules.MIN_CANARY
    assert learning_tuning.TRIAL == timedelta(days=28)  # spec 9.10 rule 3


def test_document_lessons_refuse_names_and_chat_lessons_need_no_kind():
    from app.modules.pi import learning_docs as d

    assert d._unsafe("Say it the way Mr Khan likes it rather than the old way.")
    assert d._unsafe("Lost to Zoho because they were cheaper at the start.")
    assert not d._unsafe("When writing a solution document, say “takings” rather than “sales”.")


def test_phrase_pairs_only_come_from_word_replacements_never_from_numbers():
    from app.modules.pi import learning_docs as d

    before = ["A daily read would show each shop's sales every morning."]
    after = ["A daily read would show each shop's takings every morning."]
    assert d.phrase_pairs(before, after) == [("sales", "takings")]
    assert (
        d.phrase_pairs(before, ["A daily read would show each shop's sales every 9 morning."]) == []
    )
    assert d.phrase_pairs(before, ["Something quite different that shares nothing."]) == []
    assert d.phrase_pairs(before, before) == []
    price = ["It would cost 5000 rupees per month."]
    assert d.phrase_pairs(price, ["It would cost 6000 rupees per month."]) == []


def test_voice_moments_and_what_counts_as_used():
    from app.modules.pi import learning_voice as v

    assert v.moment_of("no, it is three shops", "S2_CLARIFYING") == "correct"
    assert v.moment_of("Actually it was last month", "S3_NOTED") == "correct"
    assert v.moment_of("stock runs out in two shops", "S1_LISTENING") == "acknowledge"
    assert v.moment_of("no thanks", "S2_CLARIFYING") is None  # a short "no" is an answer
    assert v.moment_of("no, it is three shops", "S2_CLARIFYING", has_notes=False) is None
    assert v.moment_of("ok", "S2_CLARIFYING") is None  # too short to acknowledge
    assert v.moment_of("stock runs out in two shops", "S6_DECIDING") is None  # not listening
    assert v.used_in("That sounds costly. Which shop is it?", "That sounds costly.")
    assert not v.used_in("Which shop is it?", "That sounds costly.")
    assert v.valid("acknowledge", "That sounds like a headache.") == []
    assert v.valid("acknowledge", "Is it a problem?")  # a question
    assert v.valid("acknowledge", "Fine")  # one word
    assert v.valid("opening", "Hi, I'm pi.")  # a fixed line is never varied
    assert set(v.SEEDS) == {"acknowledge", "correct"}


async def test_a_trial_is_not_judged_before_four_weeks_even_with_plenty_of_data(wire):
    key = "debounce_seconds"
    default = brain_config.TUNABLES[key][0]
    settings = SimpleNamespace(response_rules={"brain": {key: default + 1}})
    latest = {key: change("setting_tuned", key, default, default + 1, +1, days_ago=10)}
    wire(latest, [rates(1.0), rates(0.1, opt_out=0.5)])  # terrible numbers, but too early to say
    out, session = await run(settings)
    assert out == {"tuned": None, "waiting": True} and not session.added
    assert settings.response_rules["brain"][key] == default + 1
