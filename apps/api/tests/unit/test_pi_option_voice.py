# ruff: noqa: E501
import re

import pytest

from app.modules.pi import constitution
from app.modules.pi import option_voice as ov
from app.modules.pi.requirements_types import (
    Constraints,
    Limit,
    ProblemRequirements,
    Requirements,
    TriedItem,
)


def reqs(cannot=(), budget=None, tried=()):
    c = Constraints(
        budget=Limit(budget) if budget else None, cannot_change=tuple(Limit(x) for x in cannot)
    )
    return Requirements(
        problems=(ProblemRequirements(constraints=c, tried=tuple(TriedItem(t) for t in tried)),)
    )


BUL = "\u2022 "


def test_nothing_stated_changes_nothing():
    r = ov.voice(f"Here are some ideas:\n{BUL}Send a reminder.", Requirements(), "en")
    assert not r.changed and r.block == "" and r.question == ""


def test_rejected_idea_removed_with_owner_words_and_one_question():
    reply = f"Here are some ideas:\n{BUL}Change the courier company to a faster one."
    r = ov.voice(reply, reqs(cannot=["we cannot change courier because of the contract"]), "en")
    assert "faster one" not in r.reply
    assert 'you said: "we cannot change courier because of the contract"' in r.block
    assert r.question == ov.T["en"]["q_cannot_change"]
    assert len(re.findall(r"[?\u061f]", r.question)) == 1


def test_accepted_idea_is_recommended_and_no_question_added():
    reply = f"Here are some ideas:\n{BUL}Keep a list of refused parcels with the reason."
    r = ov.voice(reply, reqs(cannot=["we cannot change courier because of the contract"]), "en")
    assert r.accepted == 1 and ov.T["en"]["start"] in r.block and r.question == ""


@pytest.mark.parametrize("lang", ["en", "roman_ur", "ur", "ar"])
def test_templates_are_complete_and_clean(lang):
    t = ov.T[lang]
    assert set(t) == set(ov.T["en"])
    for key, text in t.items():
        assert not re.search(r"\b(will|guarantee|price|rs\b)", text, re.I) or lang != "en", key
        if key.startswith("q_"):
            assert len(re.findall(r"[?\u061f]", text)) == 1 and text.rstrip().endswith(
                ("?", "\u061f")
            )
        else:
            assert not re.search(r"[?\u061f]", text.replace("{words}", "")), key
    assert "{words}" in t["left_out"]


@pytest.mark.parametrize("lang", ["ur", "ar"])
def test_non_latin_or_unreadable_ideas_are_labelled_not_confirmed(lang):
    idea = {
        "ur": "\u067e\u0631\u0627\u0646\u0627 \u0645\u0627\u0644 \u067e\u06c1\u0644\u06d2 \u0628\u06cc\u0686\u06cc\u06ba\u06d4",
        "ar": "\u0627\u0628\u062f\u0623 \u0628\u0627\u0644\u0645\u062e\u0632\u0648\u0646 \u0627\u0644\u0642\u062f\u064a\u0645.",
        "roman_ur": "Purana maal pehle becheen.",
    }[lang]
    r = ov.voice(f"{BUL}{idea}", reqs(cannot=["we cannot change courier"]), lang)
    assert ov.T[lang]["label"] in ov.label_ideas(r.reply, r.unmarked, lang)
    assert ov.T[lang]["unknown"] in r.block
    assert r.accepted == 0


def test_unknown_only_asks_the_blocking_limit_once():
    r = ov.voice(
        f"{BUL}ابدأ بالمخزون القديم.",
        reqs(budget="my budget is 50,000 rupees a month"),
        "ar",
    )
    assert r.unknown == 1 and r.accepted == 0
    assert r.question in ov.T["ar"].values()


def test_reply_that_already_asks_keeps_its_one_question():
    reply = f"{BUL}Change the courier company to a faster one.\nWhat result do you want?"
    r = ov.voice(reply, reqs(cannot=["we cannot change courier"]), "en")
    assert r.question == "" and r.reply.count("?") == 1


def test_block_is_not_linted_as_a_promise():
    r = ov.voice(
        f"{BUL}Change the courier company to a faster one.",
        reqs(cannot=["we cannot change courier"]),
        "en",
    )
    text = f"{r.block}\n\n{r.reply}\n\n{r.question}"
    assert [
        v for v in constitution.hard(constitution.lint(text, {})) if v.rule != "R-DISC-01"
    ] == []
