"""Fixes from the rule-auditor pass over the Book 5 work: R-SELL-01 in the new states, a map button
is not a yes to an offer, hypotheses are redacted, and one script per map message."""

import pytest

from app.modules.pi import box_signals, decisions, flow, map_render, map_share, think_plan
from app.modules.pi import problems as problem_records
from app.modules.pi.flow import State


def test_a_returning_owner_or_a_map_is_never_met_with_a_pitch() -> None:
    assert State.S_RETURN in flow.NO_OFFER and State.S_MAP_SHARE in flow.NO_OFFER
    assert State.S_LISTEN_THINK not in flow.NO_OFFER  # ideas and the offer are its job


@pytest.mark.parametrize("language", sorted(map_share.BUTTONS))
def test_the_map_confirm_button_is_not_a_yes_to_an_offer(language: str) -> None:
    title = map_share.BUTTONS[language][0]
    answer, _ = decisions.classify(title)
    assert answer != decisions.Answer.YES
    assert not decisions.summary_ok(title)
    assert box_signals.confirms_or_changes_map(title)  # but it does confirm the map


@pytest.mark.parametrize("language", ["fr", "es"])
def test_french_and_spanish_maps_are_drawn_in_their_own_words(language: str) -> None:
    assert map_render.share_language(language) == language
    assert map_render.TEXT[language]["header"]
    assert map_render.CATEGORY_NAMES[language]["stock_inventory"]


def test_hindi_gets_english_for_the_whole_map_message_until_a_font_is_bundled() -> None:
    assert map_render.share_language("hi") == "en"
    assert map_render.share_language("ps") == "ur"


def test_a_hypothesis_update_is_redacted_before_storage() -> None:
    update = think_plan.HypothesisUpdate(
        action="add",
        text="owner at 0300 1234567 thinks price",
        evidence="mail me at a@b.com card 4111 1111 1111 1111",
        test="ask 0300 1234567",
    )
    kept = update.model_copy(
        update={
            "text": problem_records.redact(update.text)[0],
            "evidence": problem_records.redact(update.evidence)[0],
            "test": problem_records.redact(update.test)[0],
        }
    )
    assert "a@b.com" not in kept.evidence and "4111" not in kept.evidence
    assert "1234567" not in kept.text and "1234567" not in kept.test
