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


def test_a_title_with_a_qualifier_is_the_same_symptom() -> None:
    from app.modules.pi.problems import same_symptom

    assert same_symptom("Best-selling items running out", "Best-selling items running out in shops")
    assert same_symptom("Missed appointments", "Missed appointments.")
    assert not same_symptom("Cashiers are late", "Stock runs out in two shops")


def test_no_thats_right_confirms_the_summary() -> None:
    from app.modules.pi import decisions
    from app.modules.pi.flow import State

    facts = {"problem_count": 2, "brief": {}, "changed": False}
    for said in ("no that's right", "no", "no, nothing missing"):
        decided = decisions.decide(State.S4_SORTED_SUMMARY, said, "en", facts)
        assert decided is not None and decided.next_state == State.S5_READINESS
    assert decisions.decide(State.S4_SORTED_SUMMARY, "no, P2 is wrong", "en", facts) is None


def test_a_shop_is_not_a_mine_collapse() -> None:
    from app.modules.pi import safety

    assert safety.emergency("میری دکان میں مال کا حساب نہیں ملتا") is None


def test_a_word_only_one_problem_uses_finds_the_idea_whatever_the_category() -> None:
    from app.modules.pi import solution_ideas, solutions

    entries = solutions.load("kiryana_corner_shops_and_convenience_stores")["problems"]
    found = solution_ideas.match_problem(entries, "accounting_errors", "", "Udhaar hisaab gadbad")
    assert found is not None and found["subtype"] == "credit_customers"
    assert solution_ideas.match_problem(entries, "accounting_errors", "", "Mausam kharab") is None


def test_asking_for_the_document_early_shows_the_summary_first() -> None:
    from app.modules.pi import problems

    assert (
        problems.summary_due("yes please prepare the document and quote", 2, 2) == "document_asked"
    )
    assert problems.summary_due("haan document aur quote chahiye", 1, 1) == "document_asked"
    assert problems.summary_due("the shop is busy", 2, 1) is None


def test_plain_ways_of_asking_for_a_fix_are_asks() -> None:
    from app.modules.pi import solution_ask

    for said in (
        "any solution? what can we do about it?",
        "any solution?",
        "what can we do about it?",
        "how can I fix this?",
        "what do you suggest?",
        "any ideas?",
        "how do we solve this",
        "isko theek kaise karein?",
        "iska hal kya hai",
    ):
        assert solution_ask.asked_for_ideas(said), said


def test_describing_a_problem_is_not_asking_for_a_fix() -> None:
    from app.modules.pi import solution_ask

    for said in (
        "we fix phones and laptops",
        "no idea why customers leave",
        "any idea why the stock goes missing at night",
        "how much does it cost",
    ):
        assert not solution_ask.asked_for_ideas(said), said


def test_handed_ideas_are_written_by_the_application_when_the_model_left_them_out() -> None:
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import brain_ideas

    context = {
        "reply_language": "en",
        "solution_ideas": ["Mark the oldest unpaid accounts first.", "Add up every balance once"],
    }
    turn = SimpleNamespace(
        reply="Noted. What else is getting in the way?",
        _summary=False,
        _decision=None,
        request_human=False,
        awaiting_customer=False,
    )
    brain_ideas(turn, context)
    assert turn.reply.startswith("Sure.") and turn.reply.count("•") == 2

    turn.reply = "Sure.\n• Do one.\n• Do two."
    brain_ideas(turn, context)
    assert turn.reply.count("•") == 2 and "Mark the oldest" not in turn.reply

    roman = SimpleNamespace(
        reply="Theek hai.",
        _summary=False,
        _decision=None,
        request_human=False,
        awaiting_customer=False,
    )
    brain_ideas(roman, {**context, "reply_language": "roman_ur"})
    assert roman.reply == "Theek hai."
