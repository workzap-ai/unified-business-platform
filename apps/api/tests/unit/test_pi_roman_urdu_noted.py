# ruff: noqa: E501
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
        "history": [{"role": "ai", "text": "Hi, I am pi."}],
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
        _free=False,
    )
    brain_no_ideas(
        turn,
        {
            "solution_asked_no_ideas": True,
            "reply_language": "roman_ur",
            "history": [{"role": "ai", "text": "Hi, I am pi."}],
        },
    )
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
            _free=False,
        )

    first = turn()
    context = {
        "solution_asked_no_ideas": True,
        "reply_language": "en",
        "history": [{"role": "ai", "text": "Hi, I am pi."}],
    }
    brain_no_ideas(first, context)
    assert first.reply == NO_IDEA_LINES["en"]
    second = turn()
    context["history"] = [
        {"role": "ai", "text": "Hi, I am pi."},
        {"role": "ai", "text": first.reply},
    ]
    brain_no_ideas(second, context)
    assert second.reply != first.reply and "solution document" in second.reply


def test_a_reply_that_already_says_it_is_an_ai_is_not_given_the_line_twice() -> None:
    from app.modules.pi.service_conversation import with_disclosure

    own = "Hi, main pi hoon, Workzap se AI. Aap ka masla kya hai?"
    assert with_disclosure(own, {"history": []}, "roman_ur") == own
    other = "Aap ka masla kya hai?"
    assert with_disclosure(other, {"history": []}, "roman_ur") != other


async def test_a_seeding_race_never_costs_the_reply() -> None:
    from sqlalchemy.exc import IntegrityError

    from app.modules.pi import solution_context

    calls = {"n": 0}

    class Nested:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *exc: object) -> bool:
            return False

    class FakeSession:
        def begin_nested(self) -> Nested:
            return Nested()

    async def fake_build(*args: object, **kwargs: object) -> dict[str, object]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise IntegrityError("insert", {}, Exception("uq_pi_solution_versions"))
        return {"solution_ideas": ["x"]}

    original = solution_context._build
    solution_context._build = fake_build  # type: ignore[assignment]
    try:
        out = await solution_context.build(FakeSession(), None, None, "any solution?", [], {})  # type: ignore[arg-type]
    finally:
        solution_context._build = original
    assert out == {"solution_ideas": ["x"]} and calls["n"] == 2


def test_free_ideas_parse_and_only_vetted_ones_survive() -> None:
    from app.modules.pi import solution_free

    answer = (
        '{"ideas": ["Write each animal\'s daily feed cost on one card, so you see which animal '
        'costs the most.", "Install a farm management app, so everything is tracked automatically.", '
        '"Give one worker the job of noting every sale in one notebook, so profit per animal can be '
        'checked."]}'
    )
    ideas = solution_free.vetted(solution_free.parse(answer), "40 janwar, kharcha?", [])
    assert len(ideas) == 2 and all("app" not in i.lower() for i in ideas)
    assert solution_free.parse("not json") == []
    assert solution_free.vetted(["Feed 5 kg of fodder twice a day, so they grow."], "", []) == []


async def test_the_model_gives_two_ideas_when_no_entry_fits() -> None:
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import brain_free_ideas

    class Manager:
        async def complete(self, *args: object, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                text='{"ideas": ["Note each animal\'s feed and sale on its own card, so you see which '
                'animal earns more than it costs.", "Give one worker the job of writing the day\'s '
                'spending in one notebook, so the daily cost is known."]}'
            )

    conversation = SimpleNamespace(id=None, service_brief={})
    turn = SimpleNamespace(
        reply="Ji. Koi chhota idea nahi.",
        _summary=False,
        _decision=None,
        request_human=False,
        awaiting_customer=False,
        _free=False,
        _english=False,
    )
    policy = SimpleNamespace(response_rules={"pi_mode": "brain"}, ai_config={})
    context = {
        "solution_asked_no_ideas": True,
        "latest_customer_message": "40 janwar hain, kharcha samajh nahi aata. Koi hal batao.",
        "history": [{"role": "ai", "text": "Hi, I am pi."}],
    }
    await brain_free_ideas(Manager(), None, conversation, policy, turn, context)  # type: ignore[arg-type]
    assert turn.reply.startswith("Sure.") and turn.reply.count("•") == 2 and turn._free
    assert conversation.service_brief["ideas_given"] == 2


def test_the_first_message_keeps_its_ai_line_when_ideas_replace_the_reply() -> None:
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import brain_ideas

    turn = SimpleNamespace(
        reply="Hi, I'm pi, an AI from Workzap. Noted.",
        _summary=False,
        _decision=None,
        request_human=False,
        awaiting_customer=False,
        _english=False,
    )
    brain_ideas(
        turn, {"reply_language": "en", "history": [], "solution_ideas": ["Count the gap once"]}
    )
    assert "an AI from Workzap" in turn.reply or "AI" in turn.reply
    assert turn.reply.count(chr(0x2022)) == 1 and turn._english


def test_misspelt_roman_urdu_asks_for_a_fix_are_asks() -> None:
    from app.modules.pi import solution_ask

    for said in (
        "Ap de skty hain solution?",
        "Ap dein solution",
        "Aur mujeh ek ai CCTV cameras ka app bnwana hai, usky liye idea ?",
        "mujhe koi mashwara dein",
        "iske liye koi hal",
    ):
        assert solution_ask.asked_for_ideas(said), said
    for said in (
        "mera idea hai ke dukan badi karun",
        "hal nahi mil raha",
        "do din se stock nahi aaya",
    ):
        assert not solution_ask.asked_for_ideas(said), said


def test_ek_near_a_price_word_is_not_an_amount_but_real_amounts_still_are() -> None:
    from app.modules.pi import price_policy

    fine = (
        "Ek worker ko roz ka kharch ek notebook mein likhne ka kaam do, taake profit saaf nazar aaye.",
        "Har janwar ka feed, labour aur kharcha ek jagah note karo.",
        "Assign one worker to record daily spending at one fixed time, so your kharcha stays clear.",
        "Aaj shed ko ek dafa walk karo aur feed note karo, taake tum dekh sako paisa kahan ja raha hai.",
    )
    for text in fine:
        assert price_policy.disclosures(text) == [], text
    for text in (
        "Iska kharcha ek hazaar rupaye hoga.",
        "The fee is 500 rupees.",
        "Iski qeemat teen hazaar hai.",
        "Cost would be fifty thousand.",
        "The fee is one dollar.",
        "Ye ek rupaya mein ho jayega.",
    ):
        assert price_policy.disclosures(text), text


def test_english_bullets_in_a_roman_urdu_chat_are_recognised() -> None:
    from app.modules.pi.service_conversation import english_bullets

    assert english_bullets(
        "Sure.\n• Number every thaan so the same animal is always written the same way."
    )
    assert not english_bullets(
        "Sure.\n• Har janwar ka milk alag likho, taake low yielder samne aa jaye."
    )
    assert not english_bullets("Theek hai, no bullets here at all.")


def test_a_person_who_now_runs_a_different_business_changes_the_industry() -> None:
    from decimal import Decimal
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import industry_context

    def customer() -> SimpleNamespace:
        return SimpleNamespace(
            industry_primary="cattle_and_buffalo_dairy_farms",
            industry_secondary=[],
            industry_confidence=Decimal("0.98"),
        )

    cattle = [
        "Mere paas Karachi mein cattle farm hai. Mere 40 janwar hain",
        "janwar ka kharcha samajh nahi aata, cattle farm ka profit",
    ]
    said = "Meri clothing shop hai. Sales ho rahi hain lekin profit kahan ja raha hai pata nahi."
    changed = customer()
    industry_context(changed, [*cattle, said], latest=said)
    assert changed.industry_primary == "retail_shops_and_chains"
    stays = customer()
    passing = "my cashier is late and I saw a pharmacy next door"
    industry_context(stays, [*cattle, passing], latest=passing)
    assert stays.industry_primary == "cattle_and_buffalo_dairy_farms"
    still = customer()
    ask = "Solution dein"
    industry_context(still, [*cattle, ask], latest=ask)
    assert still.industry_primary == "cattle_and_buffalo_dairy_farms"


def test_a_handed_back_chat_with_a_real_message_is_not_answered_with_the_hello_alone() -> None:
    from app.modules.pi.service_conversation import _brain_gate

    context = {
        "pi_mode": "brain",
        "reply_language": "roman_ur",
        "handback_notice": True,
        "history": [{"role": "ai", "text": "x"}],
    }
    hello = _brain_gate(context, "ji")
    assert hello is not None and "phir se pi" in hello.reply
    real = _brain_gate(
        context, "Meri clothing shop hai, sales ho rahi hain lekin profit kahan jata hai pata nahi"
    )
    assert real is None or "phir se pi" not in real.reply


def test_an_app_request_alone_is_not_an_ask_for_ideas_but_with_the_word_idea_it_is() -> None:
    from app.modules.pi.service_conversation import asked_without_ideas

    base = {"flow": {"state": "S3_NOTED"}}
    plain = {**base, "latest_customer_message": "can you make an app for this?"}
    assert asked_without_ideas(plain) is False
    urdu = {**base, "latest_customer_message": "Mujhe ek app bnwana hai CCTV ka, usky liye idea ?"}
    assert asked_without_ideas(urdu) is True
    assert asked_without_ideas({**base, "latest_customer_message": "Ap dein solution"}) is True
    assert asked_without_ideas({**base, "latest_customer_message": "mera dukan ka hisaab"}) is False


def test_how_exactly_gets_the_document_answer_when_the_model_says_noted() -> None:
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import brain_howto

    def turn(reply: str) -> SimpleNamespace:
        return SimpleNamespace(
            reply=reply,
            _summary=False,
            _decision=None,
            request_human=False,
            awaiting_customer=False,
            _free=False,
            _english=False,
        )

    context = {
        "reply_language": "en",
        "history": [{"role": "ai", "text": "Hi, I am pi."}],
        "solution_howto": {
            "covers": "How accounts are coded, limits set and reminders sent",
            "which_app": False,
        },
    }
    generic = turn("Thanks, that's noted. Is there anything else you want to add?")
    brain_howto(generic, context)
    assert "solution document: it covers how accounts are coded" in generic.reply
    assert generic._english and "?" not in generic.reply
    invented = turn(
        "Workzap aisa intezam kar sakta hai ke traceability fields aur reconciliation steps ho."
    )
    brain_howto(invented, context)  # steps and invented capabilities never reach the person
    assert "reconciliation" not in invented.reply and "solution document" in invented.reply
    app = turn("Noted.")
    brain_howto(app, {**context, "solution_howto": {"covers": "", "which_app": True}})
    assert app.reply.startswith("I don't recommend specific apps.")


def test_an_explicit_document_yes_with_an_offer_open_is_the_offers_yes_from_any_step() -> None:
    from app.modules.pi import decisions
    from app.modules.pi.flow import State

    facts = {
        "problem_count": 3,
        "group_count": 1,
        "problem_refs": ["a", "b", "c"],
        "brief": {"offer_asked": True},
        "changed": False,
        "message_id": "m9",
    }
    said = "Yes please, prepare the document and the quote."
    for step in (State.S3_NOTED, State.S4_SORTED_SUMMARY):
        decided = decisions.decide(step, said, "en", facts)
        assert decided is not None and decided.next_state == State.S6_PREPARING, step
    no_offer = decisions.decide(State.S3_NOTED, said, "en", {**facts, "brief": {}})
    assert no_offer is None or no_offer.next_state != State.S6_PREPARING
