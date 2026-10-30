"""Part 14 residue: the handbook as production assembles it must carry none of the old opening,
the noting openers or the old offer script (Brain v3 printed them as canonical lines and a model
copies a canonical line). Every state, every golden, every section is scanned."""

import re

import pytest

from app.modules.pi import flow, spec_handbook

RESIDUE = (
    "what's going wrong in your business",
    "going wrong in your business",
    "I'll start on it",
    "Noted",
    "Note kar liya",
    "Here are some ideas for you",
    "Shall I get one solution document",
    "You can say no",
    "End the reply with the offer",
)
# R-SELL-01/02/04 are superseded: the prompt does not name them at all (no "named as superseded"
# exception, so nothing can be read as still in force).
SUPERSEDED_RULES = re.compile(r"R-SELL-0[124]\b|R-SELL-01\.\.05")


def _whole_handbook() -> dict[str, str]:
    """Title and text of every section (a title can carry a rule id too)."""
    return {
        key: item["title"] + " | " + item["text"] for key, item in spec_handbook.sections().items()
    }


def test_no_section_or_golden_carries_the_residue():
    hits = [
        (key, phrase)
        for key, text in _whole_handbook().items()
        for phrase in RESIDUE
        if (phrase in text if phrase == "Noted" else phrase.lower() in text.lower())
    ]
    assert not hits, hits


def test_no_section_names_the_superseded_sell_rules():
    hits = [
        (k, m.group()) for k, t in _whole_handbook().items() if (m := SUPERSEDED_RULES.search(t))
    ]
    assert not hits, hits


@pytest.mark.parametrize("state", [s.name for s in flow.State])
@pytest.mark.parametrize("language", ["en", "roman_ur", "ar"])
def test_the_assembled_prompt_text_has_no_residue(state, language):
    """The text the model receives for the moment, golden conversations included, with the messages
    that pull in the most extra sections (G4, G13, G14, G15 and the topic sections)."""
    for message in ("", "can you make an app to fix this, nori demo", "price? bank transfer"):
        text = spec_handbook.guidance(
            state, message, language, can_approve=False, days_away=40, sectors=()
        )
        for phrase in RESIDUE:
            if phrase == "Noted":
                assert "Noted" not in text, (state, language, message)
            else:
                assert phrase.lower() not in text.lower(), (state, language, message, phrase)
        assert not SUPERSEDED_RULES.search(text), (state, language, message)


def test_the_listening_states_do_not_carry_the_offer_script():
    for state in ("S0_NEW", "S1_LISTENING", "S2_CLARIFYING", "S3_NOTED", "S_LISTEN_THINK"):
        rules, _golden = spec_handbook.chosen_ids(state)
        assert "3.8" not in rules, state
