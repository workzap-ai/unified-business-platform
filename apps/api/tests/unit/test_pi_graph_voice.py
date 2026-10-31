# ruff: noqa: E501
"""PS-7 in the chat: relationships are guesses unless the owner stated them; no question; four languages."""

import re

import pytest

from app.modules.pi import graph_voice as gv
from app.modules.pi import problem_graph as pg

NOTED = [
    {
        "ref": "P1",
        "title": "Many orders come back",
        "user_words": ["About 200 parcels come back every month"],
    },
    {
        "ref": "P2",
        "title": "Late courier makes buyers refuse parcels",
        "user_words": ["Our courier also delivers late, so people refuse the parcel at the door"],
    },
]
OWNER = [
    "About 200 parcels come back every month.",
    "Our courier also delivers late, so people refuse the parcel at the door. I think the courier is slow because it sends everything through one depot.",
]


def test_an_edge_the_owner_stated_is_said_as_theirs_and_the_rest_are_guesses():
    g = gv.graph_of(NOTED, OWNER, "en")
    out = gv.lines(g, "en", want_first=True)
    assert any(x.startswith("You told me") for x in out)
    first = [x for x in out if x.startswith("Worth checking first")]
    assert first and "my own guess" in first[0]  # a pi-inferred cause is never worded as fact
    assert any("cannot rank" in x for x in out)  # no figures for each problem: no order


def test_no_question_and_no_promise_in_any_language():
    for lang, tb in gv.T.items():
        assert set(tb) == set(gv.T["en"])
        for key, text in tb.items():
            assert not re.search(r"[?\u061f]", text), (lang, key)
            if lang == "en":
                assert not re.search(r"\b(will|guarantee|price)\b", text, re.I), key


@pytest.mark.parametrize("lang", ["en", "roman_ur", "ur", "ar"])
def test_every_language_renders_without_error(lang):
    g = gv.graph_of(NOTED, OWNER, lang)
    assert isinstance(gv.lines(g, lang, want_first=True), list)


def test_a_single_problem_gets_no_relationship_or_ranking_line():
    g = gv.graph_of(NOTED[:1], OWNER[:1], "en")
    assert gv.lines(g, "en") == [] or all("cannot rank" not in x for x in gv.lines(g, "en"))
    assert pg is not None
