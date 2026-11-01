# ruff: noqa: E501
"""Scope before money, and a guess with nothing behind it is not voiced."""

from types import SimpleNamespace

from app.modules.pi import graph_voice, scope_first
from app.modules.pi import problem_graph as pg

SYSTEM = "I run a property rental business and I'm looking for a proper system to manage my entire business."


def test_a_system_ask_gets_the_scope_question_in_place_of_a_budget_question():
    q = scope_first.scope_question("budget_ceiling", [SYSTEM], False, "en")
    assert q and q.endswith("?") and q.count("?") == 1 and "budget" not in q.lower()


def test_staff_and_deadline_questions_are_replaced_too():
    for key in ("staff_headcount", "deadline_duration"):
        assert scope_first.scope_question(key, [SYSTEM], False, "en")


def test_asked_once_only():
    assert scope_first.scope_question("budget_ceiling", [SYSTEM], True, "en") is None


def test_no_system_ask_keeps_the_money_question():
    assert (
        scope_first.scope_question("budget_ceiling", ["buyers ask price and go quiet"], False, "en")
        is None
    )


def test_other_questions_are_never_replaced():
    assert scope_first.scope_question("tried_outcome", [SYSTEM], False, "en") is None


def test_every_language_has_one_question_that_ends_with_a_mark():
    for text in scope_first.QUESTION.values():
        assert text.count("?") + text.count("؟") == 1 and text.rstrip()[-1] in "?؟"


def _graph(item):
    return SimpleNamespace(edges=(), problems=(), learn_first=(item,), priority=None, language="en")


def _item(status, supports):
    return pg.LearnItem("k", "customers or staff not told", status, ("p1",), 1, supports, "check")


def test_a_guess_with_no_owner_evidence_is_not_voiced():
    out = graph_voice.lines(_graph(_item(pg.PI_INFERRED, 0)), "en", want_first=True)
    assert not any("not told" in x for x in out)


def test_a_guess_with_evidence_or_an_owner_said_cause_is_voiced():
    assert any(
        "not told" in x
        for x in graph_voice.lines(_graph(_item(pg.PI_INFERRED, 2)), "en", want_first=True)
    )
    assert any(
        "not told" in x
        for x in graph_voice.lines(_graph(_item(pg.OWNER_SAID, 0)), "en", want_first=True)
    )
