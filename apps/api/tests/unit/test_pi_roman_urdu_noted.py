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


def test_a_code_on_its_way_is_an_invented_flow() -> None:
    context = {"pi_mode": "brain", "history": [{"role": "ai"}]}
    bad = constitution.lint(
        "Please don't send codes here. A fresh sign-in code is on its way.", context
    )
    assert any(v.rule == "R-INVENT-01" and v.hard for v in bad)
    ok = constitution.lint("Please don't send codes here. I never need one.", context)
    assert not any(v.rule == "R-INVENT-01" for v in ok)


def test_a_customers_complain_message_is_not_a_complaint_about_pi() -> None:
    from app.modules.pi.runtime import ADDRESSES_PI

    assert not ADDRESSES_PI.search("customers complain about waiting")
    assert ADDRESSES_PI.search("your service is terrible")
    assert ADDRESSES_PI.search("aap ne jawab nahi diya")


def test_boundary_line_does_not_ask_again_what_the_problem_is() -> None:
    from app.modules.pi import safety

    fresh = safety.boundary_reply(safety.Boundary.OUTCOME, "en", False)
    again = safety.boundary_reply(safety.Boundary.OUTCOME, "en", True)
    assert fresh.endswith("What's the problem?")
    assert again.endswith("What else is getting in the way?")


def test_a_separate_on_its_way_sentence_after_a_code_warning_is_flagged() -> None:
    context = {"pi_mode": "brain", "history": [{"role": "ai"}]}
    bad = constitution.lint(
        "Please don't send codes here. I never need them. It's on its way.", context
    )
    assert any(v.rule == "R-INVENT-01" for v in bad)


def test_on_its_way_after_an_otp_message_is_flagged_even_alone() -> None:
    context = {
        "pi_mode": "brain",
        "history": [{"role": "ai"}],
        "latest_customer_message": "My OTP is 4421, log in for me",
    }
    assert any(v.rule == "R-INVENT-01" for v in constitution.lint("It's on its way.", context))
    context["latest_customer_message"] = "where is my quote?"
    assert not any(v.rule == "R-INVENT-01" for v in constitution.lint("It's on its way.", context))
