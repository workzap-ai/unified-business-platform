"""The blocklist's number rules: what counts as a number, what counts as a range, and that a
whole country can never be blocked by accident (no database)."""

import pytest

from app.modules.pi_saas.blocklist.models import MIN_PREFIX
from app.modules.pi_saas.blocklist.service import clean_value, view
from app.shared.errors import BusinessRuleViolation


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+62 895-6366-26854", "62895636626854"),
        ("62895636626854", "62895636626854"),
        ("(+92) 311 2546598", "923112546598"),
    ],
)
def test_a_number_is_kept_as_digits_with_its_country_code(raw: str, expected: str) -> None:
    assert clean_value(raw, "number") == expected


@pytest.mark.parametrize("raw", ["", "abc", "12345", "1234567890123456"])
def test_a_number_that_is_too_short_or_too_long_is_refused(raw: str) -> None:
    with pytest.raises(BusinessRuleViolation) as caught:
        clean_value(raw, "number")
    assert caught.value.code == "PHONE_INVALID"


def test_a_range_is_the_start_of_a_number() -> None:
    assert clean_value("+62 895636", "prefix") == "62895636"
    assert clean_value("628956366", "prefix") == "628956366"


@pytest.mark.parametrize("raw", ["62", "+92", "9231", "92311"])
def test_a_country_code_or_a_short_start_can_never_be_a_range(raw: str) -> None:
    assert len(raw.lstrip("+")) < MIN_PREFIX
    with pytest.raises(BusinessRuleViolation) as caught:
        clean_value(raw, "prefix")
    assert caught.value.code == "PREFIX_INVALID"


def test_the_view_masks_a_number_but_names_a_range() -> None:
    from types import SimpleNamespace

    number = SimpleNamespace(
        id="1", value="62895636626854", kind="number", reason="r", note="", source="chat",
        active=True, hits=2, last_hit_at=None, created_at=None,
    )  # fmt: skip
    rng = SimpleNamespace(
        id="2", value="628956366", kind="prefix", reason="", note="", source="bulk",
        active=True, hits=0, last_hit_at=None, created_at=None,
    )  # fmt: skip
    assert view(number)["masked"] != number.value and "62" in view(number)["masked"]  # type: ignore[arg-type]
    assert view(rng)["masked"] == "628956366…"  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "text",
    ["STOP", "stop", "please stop messaging me", "I want to kill myself", "he is going to kill me"],
)
def test_an_emergency_or_a_stop_from_a_blocked_number_still_gets_through(text: str) -> None:
    from app.modules.pi_saas.blocklist.service import must_pass

    assert must_pass(text)


@pytest.mark.parametrize("text", ["", "hello", "Wholesale price list please", "photo", None])
def test_anything_else_from_a_blocked_number_is_dropped(text: str | None) -> None:
    from app.modules.pi_saas.blocklist.service import must_pass

    assert not must_pass(text)
