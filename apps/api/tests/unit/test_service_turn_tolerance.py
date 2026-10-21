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


def test_unknown_choices_fall_back_to_safe_values():
    turn = ServiceTurn.model_validate(
        {
            "reply": "ok",
            "summary": "s",
            "action": "refund_everything",
            "consent": "maybe",
            "action_priority": "ASAP",
            "payment_method": "crypto",
        }
    )
    assert turn.action == "none" and turn.consent == "unchanged"
    assert turn.action_priority == "normal" and turn.payment_method == "none"


def test_nulls_numbers_and_lists_are_tolerated():
    turn = ServiceTurn.model_validate(
        {
            "reply": "Ji zaroor, website ke liye kuch sawal.",
            "summary": None,
            "language": None,
            "requirements": {
                "service": "Website",
                "customer_budget": 50000,
                "scope": ["shop", "blog"],
                "audience": None,
            },
            "missing": "audience",
            "awaiting_customer": "true",
            "ready_for_team": None,
            "consent_evidence": None,
            "action": None,
            "booking_start": None,
        }
    )
    assert turn.requirements.customer_budget == "50000"
    assert turn.requirements.scope == "shop, blog" and turn.requirements.audience == ""
    assert turn.missing == ["audience"] and turn.awaiting_customer is True
    assert turn.ready_for_team is False and turn.action == "none"
    assert turn.summary == ""  # compose_service_turn writes one from the brief


def test_schema_is_accepted_by_gemini():
    # Gemini refuses a response schema whose choices include an empty string.
    from app.ai.providers.gemini import to_gemini_schema

    schema = to_gemini_schema(ServiceTurn.model_json_schema())
    for field in schema["properties"].values():
        assert "" not in field.get("enum", [])
