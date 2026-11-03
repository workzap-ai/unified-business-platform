# ruff: noqa: E501
"""A2-FIX-5: the opener of the Workzap line is a learned voice variant, only while learning is on."""

from app.modules.pi import learning_voice, solution_ask, solutions

PROBLEM = {"id": "p1", "workzap_build": {"keys": ["custom_build"]}}


def test_the_approved_openers_are_the_bridge_variants_and_the_first_is_the_baseline():
    for language in ("en", "roman_ur"):
        seeds = learning_voice.SEEDS["bridge"][language]
        openers = [o[language] for o in solutions.BRIDGE_OPENERS if o[language]]
        assert seeds == openers and len(seeds) >= 3
        assert learning_voice.slot_of("bridge") == "voice_bridge"


def test_no_model_writes_new_openers():
    assert "bridge" not in learning_voice.MINED
    assert set(learning_voice.MINED) <= set(learning_voice.SEEDS)


def test_the_learned_opener_is_used_when_it_has_not_been_used_in_this_chat():
    preferred = solutions.BRIDGE_OPENERS[1]["roman_ur"]
    line = solution_ask.bridge({"bridge_preferred": preferred}, PROBLEM, "roman_ur")
    assert line is not None and line["opener"] == preferred and line["_index"] == 1
    used = solution_ask.bridge(
        {"bridge_preferred": preferred, "bridge_used": [1]}, PROBLEM, "roman_ur"
    )
    assert used is not None and used["opener"] != preferred  # never the same opener twice in a chat


def test_without_a_learned_opener_the_openers_rotate_as_before():
    first = solution_ask.bridge({}, PROBLEM, "en")
    second = solution_ask.bridge({"bridge_used": [first["_index"]]}, PROBLEM, "en")
    assert first["_index"] == 0 and second["_index"] == 1


def test_a_preferred_opener_of_another_language_is_ignored():
    english = solutions.BRIDGE_OPENERS[1]["en"]
    line = solution_ask.bridge({"bridge_preferred": english}, PROBLEM, "roman_ur")
    assert line is not None and line["_index"] == 0
