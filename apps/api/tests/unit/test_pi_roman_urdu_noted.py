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
    # the list is written in English; the reply-language step after it rewrites the whole reply
    assert roman.reply.startswith("Sure.") and roman.reply.count("•") == 2


def test_haan_document_aur_quote_chahiye_is_a_yes_to_the_offer() -> None:
    from app.modules.pi import decisions
    from app.modules.pi.flow import State

    facts = {
        "problem_count": 1,
        "group_count": 1,
        "brief": {"offer_asked": True},
        "changed": False,
        "message_id": "x",
    }
    decided = decisions.decide(
        State.S5_READINESS, "haan document aur quote chahiye", "roman_ur", facts
    )
    assert decided is not None and decided.next_state == State.S6_PREPARING


def test_more_plain_asks_for_a_fix_and_for_the_map() -> None:
    from app.modules.pi import problems, solution_ask

    for said in (
        "Can you give my problem solution",
        "Give more ideas please",
        "Mujhe solution dw Meri problems ka",
        "Hal tw btao",
        "First give me your solution idea",
    ):
        assert solution_ask.asked_for_ideas(said), said
    assert not solution_ask.asked_for_ideas("hal nahi mil raha")
    assert problems.summary_due("Show my problem map", 2, 0) == "map"
    assert problems.summary_due("Can you send again my problem map?", 1, 0) == "map"


def test_a_plain_yes_after_all_or_some_means_all() -> None:
    from app.modules.pi import decisions
    from app.modules.pi.flow import State

    facts = {
        "problem_count": 3,
        "group_count": 2,
        "problem_refs": ["a", "b", "c"],
        "chosen_refs": [],
        "brief": {"offer_asked": True, "scope_asked": True, "offer_yes_id": "m1"},
        "changed": False,
        "message_id": "m2",
    }
    decided = decisions.decide(
        State.S5_READINESS, "Hn mujeh solution document chahiye", "roman_ur", facts
    )
    assert decided is not None and decided.next_state == State.S6_PREPARING


def test_no_idea_for_the_problem_is_said_plainly() -> None:
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import brain_no_ideas

    turn = SimpleNamespace(
        reply="Noted. Aur kya masla aa raha hai?",
        _summary=False,
        _decision=None,
        request_human=False,
        awaiting_customer=False,
    )
    brain_no_ideas(turn, {"solution_asked_no_ideas": True, "reply_language": "roman_ur"})
    assert turn.reply.startswith("Ji. ") and "solution document" in turn.reply


def test_short_roman_urdu_nothing_more_and_summary_asks() -> None:
    from app.modules.pi import problems

    assert problems.summary_due("Abh NH", 2, 1) == "done"
    assert problems.summary_due("bas nh", 2, 1) == "done"
    assert problems.summary_due("Summary kosni", 2, 1) == "show"
    assert problems.summary_due("abh nahi hota ye masla ab kaafi kam hai bahut", 2, 1) is None


def test_a_yes_that_asks_for_the_document_stands_when_a_problem_was_touched() -> None:
    from app.modules.pi import decisions
    from app.modules.pi.flow import State

    facts = {
        "problem_count": 2,
        "group_count": 1,
        "problem_refs": ["a", "b"],
        "brief": {"offer_asked": True},
        "changed": True,
        "message_id": "m3",
    }
    decided = decisions.decide(
        State.S5_READINESS, "haan document aur quote chahiye", "roman_ur", facts
    )
    assert decided is not None and decided.next_state == State.S6_PREPARING
    assert decisions.decide(State.S5_READINESS, "wait, one more thing", "en", facts) is None
    assert decisions.decide(State.S5_READINESS, "yes", "en", facts) is None


def test_the_no_idea_line_is_not_repeated_word_for_word() -> None:
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import NO_IDEA_LINES, brain_no_ideas

    def turn() -> SimpleNamespace:
        return SimpleNamespace(
            reply="x",
            _summary=False,
            _decision=None,
            request_human=False,
            awaiting_customer=False,
        )

    first = turn()
    context = {"solution_asked_no_ideas": True, "reply_language": "en", "history": []}
    brain_no_ideas(first, context)
    assert first.reply == NO_IDEA_LINES["en"]
    second = turn()
    context["history"] = [{"role": "ai", "text": first.reply}]
    brain_no_ideas(second, context)
    assert second.reply != first.reply and "solution document" in second.reply
