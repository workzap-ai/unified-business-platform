from app.modules.pi import constitution


def test_english_noted_sentence_in_roman_urdu_is_flagged() -> None:
    context = {"reply_language": "roman_ur", "pi_mode": "brain", "history": [{"role": "ai"}]}
    found = constitution.lint("Thanks. I've noted it: udhaar ka total nahi pata. Kab se?", context)
    assert any(v.rule == "R-LANG-02" for v in found)


def test_roman_urdu_noted_sentence_is_fine() -> None:
    context = {"reply_language": "roman_ur", "pi_mode": "brain", "history": [{"role": "ai"}]}
    found = constitution.lint(
        "Shukriya. Maine note kar liya: udhaar ka total nahi pata. Kab se?", context
    )
    assert not any(v.rule == "R-LANG-02" for v in found)


def test_handed_ideas_must_be_given() -> None:
    context = {
        "reply_language": "roman_ur",
        "pi_mode": "brain",
        "history": [{"role": "ai"}],
        "solution_ideas": ["Let only one person make payment entries."],
        "solution_asked": True,
    }
    flat = constitution.lint("Note kar liya. Kya aap bata sakte hain ke masla kya hai?", context)
    assert any(v.rule == "R-VAL-08" for v in flat)
    listed = constitution.lint(
        "Haan.\n1. Sirf ek banda entry kare.\n2. Har payment par tareekh likhein.", context
    )
    assert not any(v.rule == "R-VAL-08" for v in listed)
