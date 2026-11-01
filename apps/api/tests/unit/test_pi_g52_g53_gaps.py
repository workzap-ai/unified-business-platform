"""G52 (Chat A) and G53 (Chat B) fixes: a trade the model guessed is caught even with industry packs
off, and "X alag note kar li hai" is not announced (spec v1.6 17.3, 17.4 G11, 17.6)."""

from app.modules.pi import reply_voice, spec_rules2

GUESS = "Ye stock zyada tar AC units ka hai ya spare parts aur gas ka?"


def _brain(**more):
    return {
        "pi_mode": "brain",
        "latest_customer_message": "Koi joor nahi hai",
        "burst_texts": ["Uskay baad koi inventory ka hisaab nahi"],
        "reply_language": "roman_ur",
        **more,
    }


def test_a_guessed_trade_is_caught_when_packs_are_off() -> None:
    assert spec_rules2.assumed_industry(GUESS, _brain())  # no industry_unconfirmed flag at all


def test_a_confirmed_trade_is_not_caught_when_packs_are_off() -> None:
    confirmed = _brain(brief={"industry_confirmed": True})
    assert spec_rules2.assumed_industry(GUESS, confirmed) is None
    stored = _brain(brief={"business_profile": {"facts": [{"key": "business_type", "value": "x"}]}})
    assert spec_rules2.assumed_industry(GUESS, stored) is None


def test_an_open_question_is_never_caught() -> None:
    assert spec_rules2.assumed_industry("Ye maal kis cheez ka hai?", _brain()) is None


def test_outside_brain_mode_nothing_changes() -> None:
    assert spec_rules2.assumed_industry(GUESS, {**_brain(), "pi_mode": "standard"}) is None


def test_a_separate_note_announcement_is_dropped() -> None:
    reply = (
        "Ye do alag masle hain: patte zaya hote hain. Lettuce farm wali baat bhi alag note "
        "kar li hai. Restaurants ko aap kitne din pehle batate hain?"
    )
    kept = reply_voice.drop_noted(reply)
    assert "alag note kar li" not in kept
    assert kept.endswith("batate hain?") and kept.startswith("Ye do alag masle hain")
