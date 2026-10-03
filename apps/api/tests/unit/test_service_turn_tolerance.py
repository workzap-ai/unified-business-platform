"""A model that adds an extra key, names the language in words or leaves out a minor
field still produces a usable turn; a turn without a reply is still rejected."""

import pytest
from pydantic import ValidationError

from app.modules.pi.service_conversation import ServiceTurn


def test_extra_keys_and_language_names_are_tolerated():
    turn = ServiceTurn.model_validate(
        {
            "reply": "Salam! Aap ko kaunsi service chahiye?",
            "summary": "Customer greeted and asked about services.",
            "language": "Roman Urdu",
            "intent": "greeting",  # not part of the format: ignored
            "requirements": {"service": "Website", "notes": "extra"},
        }
    )
    assert turn.language == "roman_ur"
    assert turn.requirements.service == "Website"
    assert turn.missing == [] and turn.awaiting_customer is False
    assert turn.action == "none"


def test_unknown_language_falls_back_and_long_text_is_trimmed():
    turn = ServiceTurn.model_validate(
        {"reply": "x" * 5000, "summary": "ok", "language": "Klingon", "missing": ["a"] * 20}
    )
    assert turn.language == "en"
    assert len(turn.reply) == 4000 and len(turn.missing) == 12


def test_reply_is_still_required():
    with pytest.raises(ValidationError):
        ServiceTurn.model_validate({"summary": "no reply"})


def test_actions_stay_limited():
    with pytest.raises(ValidationError):
        ServiceTurn.model_validate({"reply": "ok", "summary": "s", "action": "refund_everything"})
