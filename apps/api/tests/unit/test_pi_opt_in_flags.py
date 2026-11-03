"""The per-workspace opt-in flags can be set from the settings API, and only as true or false."""

import pytest

from app.modules.pi.policy import validate_section
from app.shared.errors import BusinessRuleViolation

BASE = {
    "language": "auto",
    "service_mode": "auto",
    "pi_mode": "brain",
    "tone": "friendly",
    "greeting": "",
    "sign_off": "",
}


@pytest.mark.parametrize("flag", ["idea_link", "fact_ask", "list_guard"])
def test_the_flag_is_accepted_as_a_boolean(flag: str) -> None:
    validate_section("response_rules", {**BASE, "brain": {flag: True}})
    validate_section("response_rules", {**BASE, "brain": {flag: False}})


@pytest.mark.parametrize("flag", ["idea_link", "fact_ask", "list_guard"])
@pytest.mark.parametrize("bad", ["yes", 1, None, "true"])
def test_the_flag_is_refused_when_it_is_not_a_boolean(flag: str, bad: object) -> None:
    with pytest.raises(BusinessRuleViolation):
        validate_section("response_rules", {**BASE, "brain": {flag: bad}})


def test_an_unknown_brain_key_is_still_refused() -> None:
    with pytest.raises(BusinessRuleViolation):
        validate_section("response_rules", {**BASE, "brain": {"made_up_flag": True}})
