# ruff: noqa: E501
"""The owner reads the options in the chat: PS-3's six verdicts, with the L2-1 gate plugged in, in
four languages. One verdict path (`option_voice.voice`)."""

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

BUL = "\u2022 "
PROBLEMS = [
    {
        "title": "Late courier makes buyers refuse parcels",
        "user_words": ["our courier delivers late"],
        "group": "orders_fulfilment",
    }
]
LINKED = "Message each buyer when the parcel leaves with the courier tracking line, so the buyer expects it."
VIOLATING = "Change the courier to a faster one."
UNLINKED = "Repaint the shop signboard in a brighter colour."
GENERIC = "Use better software to improve your business."
REPEAT = "Offer a discount to customers whose orders were late."


def reqs(cannot=(), tried=(), budget=None):
    c = Constraints(
        budget=Limit(budget) if budget else None, cannot_change=tuple(Limit(x) for x in cannot)
    )
    return Requirements(
        problems=(ProblemRequirements(constraints=c, tried=tuple(TriedItem(t) for t in tried)),)
    )


COURIER = reqs(cannot=["we cannot change courier because of the contract"])


def run(*ideas, r=COURIER, lang="en", problems=PROBLEMS):
    reply = "Here are some ideas:\n" + "\n".join(f"{BUL}{i}" for i in ideas)
    return ov.voice(reply, r, lang, problems)


def test_linked_idea_with_the_gate_ok_stays_and_is_recommended():
    r = run(LINKED)
    assert r.accepted == 1 and r.unknown == 0 and not r.unmarked
    assert ov.T["en"]["start"] in r.block and LINKED in r.reply


def test_violating_idea_is_removed_with_the_owners_words_and_one_question():
    r = run(VIOLATING)
    assert "faster one" not in r.reply
    assert 'you said: "we cannot change courier because of the contract"' in r.block
    assert r.question == ov.T["en"]["q_cannot_change"]


def test_violation_wins_even_over_a_linked_idea():
    r = run(VIOLATING, LINKED)
    assert VIOLATING not in r.reply and LINKED in r.reply


def test_unlinked_idea_is_removed_and_said_so():
    r = run(UNLINKED, LINKED)
    assert UNLINKED not in r.reply and ov.T["en"]["off_topic"] in r.block


def test_generic_idea_is_removed_and_said_so():
    r = run(GENERIC, LINKED)
    assert GENERIC not in r.reply and ov.T["en"]["generic"] in r.block


def test_repeated_idea_is_removed_with_the_owners_words():
    r = run(REPEAT, LINKED, r=reqs(tried=["I tried a discount on late orders"]))
    assert REPEAT not in r.reply
    assert 'you already tried: "I tried a discount on late orders"' in r.block


def test_nothing_linked_never_pads_and_asks_one_question():
    r = run(UNLINKED, GENERIC)
    assert not [x for x in r.reply.splitlines() if x.startswith(BUL)]
    assert r.question == ov.T["en"]["q_default"]


def test_unknown_is_labelled_never_linked():
    # no noted problem to judge by: relevance is UNKNOWN, so the idea stays only as "not yet checked"
    r = run(LINKED, problems=())
    assert r.unknown == 1 and r.accepted == 0
    assert ov.T["en"]["label"] in ov.label_ideas(r.reply, r.unmarked, "en")
    assert ov.T["en"]["start"] not in r.block


def test_unreadable_requirements_are_unknown_not_confirmed():
    r = run(LINKED, r=Requirements(columns_available=False))
    assert r.accepted == 0 and r.unknown == 1


def test_reply_that_already_asks_keeps_its_one_question():
    reply = f"{BUL}{UNLINKED}\nWhat result do you want?"
    r = ov.voice(reply, COURIER, "en", PROBLEMS)
    assert r.question == "" and r.reply.count("?") == 1


@pytest.mark.parametrize("lang", ["en", "roman_ur", "ur", "ar"])
def test_templates_are_complete_and_clean(lang):
    t = ov.T[lang]
    assert set(t) == set(ov.T["en"])
    for key, text in t.items():
        if lang == "en":
            assert not re.search(r"\b(will|guarantee|price)\b", text, re.I), key
        if key.startswith("q_"):
            assert len(re.findall(r"[?\u061f]", text)) == 1 and text.rstrip().endswith(
                ("?", "\u061f")
            )
        else:
            assert not re.search(r"[?\u061f]", text.replace("{words}", "")), key
    assert "{words}" in t["left_out"] and "{words}" in t["repeat"]


URDU_LINKED = "پارسل کے ساتھ خریدار کو ڈیلیوری کی ٹریکنگ بھیجیں۔"
ARABIC_LINKED = "أرسل للمشتري تتبع التوصيل عند خروج الطرد."


@pytest.mark.parametrize(("lang", "idea"), [("ur", URDU_LINKED), ("ar", ARABIC_LINKED)])
def test_urdu_and_arabic_linked_ideas_are_kept_and_unchecked_ones_are_labelled(lang, idea):
    r = run(idea, lang=lang)
    # the L2-1 gate reads English and Roman Urdu only, so the idea stays labelled as not yet checked
    assert r.accepted == 0 and r.unknown == 1
    assert ov.T[lang]["label"] in ov.label_ideas(r.reply, r.unmarked, lang)
    assert ov.T[lang]["unknown"] in r.block


def test_block_is_not_linted_as_a_promise():
    r = run(VIOLATING)
    text = f"{r.block}\n\n{r.reply}\n\n{r.question}"
    assert [
        v for v in constitution.hard(constitution.lint(text, {})) if v.rule != "R-DISC-01"
    ] == []
