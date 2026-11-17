"""The Nori Platform board's pure rules: number cleaning, the kind hint, the door's body checks."""

import pytest

from app.modules.pi_saas.nori_board.door import parse_item
from app.modules.pi_saas.nori_board.service import classify, normalise_phone
from app.modules.pi_saas.nori_credits.config import validate_workspace_section, workspace_bridge

HOST = "nori.test"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+92 300 1234567", "923001234567"),
        ("(92) 300-123-4567", "923001234567"),
        ("12345", None),
        ("1" * 16, None),
        ("", None),
        (None, None),
        (923001234567, None),
    ],
)
def test_phone_is_digits_with_country_code(raw, expected):
    assert normalise_phone(raw) == expected


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("The export is not working since morning", "problem"),
        ("payroll mein masla aa raha hai", "problem"),
        ("We need a new module for van sales", "feature"),
        ("mujhe ye feature chahiye", "feature"),
        ("Can the report show last month too?", "question"),
        ("Thanks, the new screen is great", "feedback"),
        ("ok", "note"),
    ],
)
def test_kind_hint(text, kind):
    assert classify(text) == kind


def item(**extra):
    return {
        "ref": "rq-12",
        "kind": "feature",
        "title": "Van sales",
        "workspace": "Mendeez",
        **extra,
    }


def test_a_good_item_is_cleaned_and_filled_in():
    got = parse_item(item(text="  add it  ", phone="+92 300 1234567", priority="high"), HOST)
    assert isinstance(got, dict)
    assert got["text"] == "add it"
    assert got["phone"] == "923001234567"
    assert got["priority"] == "high"
    assert got["url"] is None and got["person"] == "" and got["department"] == ""


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"ref": "has space"}, "bad_ref"),
        ({"ref": ""}, "bad_ref"),
        ({"ref": "x" * 81}, "bad_ref"),
        ({"kind": "rant"}, "bad_kind"),
        ({"title": "", "text": ""}, "bad_text"),
        ({"title": "x" * 201}, "bad_text"),
        ({"text": "x" * 2001}, "bad_text"),
        ({"title": 5}, "bad_text"),
        ({"workspace": ""}, "bad_item"),
        ({"workspace": None}, "bad_item"),
        ({"person": 3}, "bad_item"),
        ({"priority": "now"}, "bad_priority"),
        ({"phone": "12"}, "bad_phone"),
        ({"url": "http://nori.test/x"}, "bad_url"),
        ({"url": "https://evil.example/x"}, "bad_url"),
        ({"url": "https://nori.test.evil.example/x"}, "bad_url"),
        ({"url": "https://user:pw@nori.test/x"}, "bad_url"),
        ({"url": 7}, "bad_url"),
    ],
)
def test_a_bad_item_is_refused_with_a_reason(change, reason):
    assert parse_item(item(**change), HOST) == reason


def test_nori_own_host_and_subdomains_are_allowed_links():
    for url in ("https://nori.test/help/requests/12", "https://app.nori.test/r/12"):
        got = parse_item(item(url=url), HOST)
        assert isinstance(got, dict) and got["url"] == url


def test_board_flag_is_off_unless_exactly_true():
    assert workspace_bridge({"nori_bridge": {"enabled": True}}).board is False
    assert workspace_bridge({"nori_bridge": {"enabled": True, "board": True}}).board is True
    assert workspace_bridge({"nori_bridge": {"enabled": True, "board": "yes"}}) is None
    assert workspace_bridge({"nori_bridge": {"board": True}}) is None
    assert validate_workspace_section({"enabled": True, "board": True})
    assert not validate_workspace_section({"board": 1})
