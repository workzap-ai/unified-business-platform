"""ROFFER07 (platform spec v1.6): after a yes to the offer, ask only the facts the quote needs,
at most two, and say why. One question sentence, so RASK01 still holds."""

from app.modules.pi import quote_facts
from app.modules.pi.decisions import decide
from app.modules.pi.flow import State


def test_roffer07_the_message_asks_at_most_two_facts_and_says_why() -> None:
    for language in ("en", "roman_ur", "ur", "ar"):
        line = quote_facts.ask_line(["shops", "locations", "systems"], language)
        assert quote_facts.question_count(line) <= 2
        assert not quote_facts.too_many_questions(line)
    roman = quote_facts.ask_line(["shops", "locations", "systems"], "roman_ur")
    assert "taake quote sahi bane" in roman.lower()
    assert "dukaanen" in roman and "shehron" in roman and "record" not in roman
    assert roman.rstrip().endswith("?")


def test_roffer07_the_facts_go_in_one_question_so_one_question_per_message_holds() -> None:
    line = quote_facts.ask_line(["shops", "systems"], "en")
    assert quote_facts.question_count(line) == 1
    assert line.rstrip().endswith("?")


def test_roffer07_only_the_missing_facts_are_asked() -> None:
    ctx = {
        "history": [{"role": "customer", "text": "I have 3 shops, stock is on paper"}],
        "noted_problems": [],
        "brief": {},
    }
    assert quote_facts.missing(ctx) == ["locations"]
    full = {**ctx, "noted_problems": [{"where": ["Lahore"]}]}
    assert quote_facts.missing(full) == []
    assert quote_facts.missing({"history": [], "brief": {}}) == ["shops", "locations"]


def _yes(brief: dict, missing: list[str] | None, message: str = "haan bana dein"):
    facts = {
        "message_id": "m1",
        "can_approve": True,
        "problem_count": 2,
        "group_count": 1,
        "problem_refs": ["P1", "P2"],
        "brief": brief,
        "quote_missing": missing,
    }
    return decide(State.S5_READINESS, message, "roman_ur", facts)


def test_roffer07_a_yes_with_missing_facts_asks_once_and_does_not_prepare_yet() -> None:
    d = _yes({}, ["shops", "locations"])
    assert d is not None and d.reply and "taake quote sahi bane" in d.reply.lower()
    assert d.next_state is None and "request_solution" not in d.effects
    assert d.brief["quote_facts_asked"] is True
    assert d.reply.count("?") == 1


def test_roffer07_the_answer_then_starts_the_quote_and_pi_does_not_ask_twice() -> None:
    asked = {"quote_facts_asked": True, "offer_yes_id": "m0"}
    d = _yes(asked, ["shops"], "teen shops hain Lahore mein")
    assert d is not None and d.next_state == State.S6_PREPARING
    assert "request_solution" in d.effects and d.brief["quote_facts_done"] is True
    again = _yes({"quote_facts_asked": True, "quote_facts_done": True}, ["shops"])
    assert again is not None and again.next_state == State.S6_PREPARING


def test_roffer07_nothing_missing_or_a_no_goes_the_old_way() -> None:
    d = _yes({}, [])
    assert d is not None and d.next_state == State.S6_PREPARING
    none_key = _yes({}, None)
    assert none_key is not None and none_key.next_state == State.S6_PREPARING
    declined = _yes({"quote_facts_asked": True}, ["shops"], "nahi shukriya")
    assert declined is not None and declined.next_state == State.S5B_DECLINED


def test_roffer07_the_flag_is_opt_in_and_only_a_boolean() -> None:
    import pytest

    from app.modules.pi.policy import validate_section
    from app.shared.errors import BusinessRuleViolation

    base = {
        "language": "auto",
        "service_mode": "auto",
        "pi_mode": "brain",
        "tone": "friendly",
        "greeting": "",
        "sign_off": "",
    }
    validate_section("response_rules", {**base, "brain": {"quote_facts": True}})
    with pytest.raises(BusinessRuleViolation):
        validate_section("response_rules", {**base, "brain": {"quote_facts": "true"}})


def test_roffer07_cap_demotes_extra_questions_and_keeps_every_sentence() -> None:
    text = "Kitni shops hain? Kahan hain? Kya Excel use karte hain?"
    capped = quote_facts.cap(text)
    assert quote_facts.question_count(capped) == 2
    assert capped.endswith("Kahan hain? Kya Excel use karte hain?")
    assert capped.startswith("Kitni shops hain.")
    assert len(capped) == len(text)
    arabic = quote_facts.cap("كم؟ أين؟ ماذا؟")
    assert quote_facts.question_count(arabic) == 2
    assert quote_facts.cap("One? Two?") == "One? Two?"
    assert quote_facts.cap("") == ""


def test_roffer07_the_ask_line_is_always_inside_the_cap() -> None:
    for language in ("en", "roman_ur", "ur", "ar"):
        line = quote_facts.ask_line(["shops", "locations", "systems"], language)
        assert quote_facts.cap(line) == line


def test_roffer07_facts_in_the_stored_profile_are_not_asked_again() -> None:
    ctx = {
        "history": [],
        "noted_problems": [],
        "brief": {
            "business_profile": {
                "facts": [
                    {"key": "branches", "value": "4"},
                    {"key": "cities", "value": "Lahore"},
                ]
            }
        },
    }
    assert quote_facts.missing(ctx) == ["systems"]
