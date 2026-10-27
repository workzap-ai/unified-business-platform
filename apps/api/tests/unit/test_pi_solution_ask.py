"""Free ideas on request, "how exactly?", the Workzap line and the free-rider signal (Addendum 2,
Parts 1.4 to 1.6 and 1.9) in the live chat."""

import pytest

from app.modules.pi import constitution as c
from app.modules.pi import decisions, flow, solution_ask, solutions
from app.modules.pi.service_conversation import ServiceTurn, brain_offer, brain_summary


@pytest.mark.parametrize(
    "said",
    [
        "Can you tell me the solution",
        "Aap jaldi solution do na mujhe, sawal hi poochti rahogi kya?",
        "Batao kuch kar sakte hain ya nahi kar sakte?",
        "Kya karun? Kya solution hai tumhare paas?",
        "so what can you do?",
        "can you make an app for this?",
    ],
)
def test_asking_for_a_fix_is_recognised(said):
    assert solution_ask.asked_for_ideas(said)


@pytest.mark.parametrize(
    "said",
    ["how much would it cost?", "kitna kharcha hoga", "stock khatam ho jata hai", "no", "hello"],
)
def test_a_cost_question_or_a_problem_is_not_a_request_for_ideas(said):
    assert not solution_ask.asked_for_ideas(said)


@pytest.mark.parametrize(
    "said,app",
    [
        ("ye ad wala code kaise lagana hai exactly?", False),
        ("how exactly?", False),
        ("step by step batao", False),
        ("just tell me which app to use", True),
        ("kaunsa software?", True),
    ],
)
def test_how_exactly_and_which_app(said, app):
    assert solution_ask.asked_howto(said)
    assert solution_ask.asked_which_app(said) is app


def test_what_the_document_covers_comes_from_the_entry():
    problem = solutions.load("retail_shops_and_chains")["problems"][0]
    covered = solution_ask.covers(problem)
    assert covered and "solution document" not in covered and not covered.endswith(".")
    assert solution_ask.covers(None) == ""


def test_the_workzap_line_once_per_problem_with_a_new_opener_each_time():
    problems = solutions.load("retail_shops_and_chains")["problems"]
    brief: dict = {}
    openers = []
    for problem in problems[:5]:
        line = solution_ask.bridge(brief, problem, "en")
        assert line and line["says"] and "refer_back" not in line
        openers.append(line["opener"])
        brief = solution_ask.remember_bridge(brief, line)
    assert len({o for o in openers if o}) == len([o for o in openers if o])  # none repeats
    again = solution_ask.bridge(brief, problems[0], "en")
    assert again == {"refer_back": True}  # RBUILD03
    assert solution_ask.bridge(brief, None, "en") is None
    assert "_index" not in solution_ask.public(line)


def test_the_free_rider_signal_never_needs_a_tone_change():
    assert not solution_ask.free_rider({}, "what can you do?")
    assert solution_ask.free_rider({"howto_asked": 3}, "")
    assert solution_ask.free_rider({"declines": 2}, "")
    assert solution_ask.free_rider({}, "this is for my client, an agency")


BOX_READY = {
    "box_offer": True,
    "noted_problems": [
        {"ref": "a", "since": "a year"},
        {"ref": "b", "impact": "cash"},
        {"ref": "c"},
    ],
    "brief": {"map_reviewed": True, "ranked": True, "voluntary_problems": 1},
    "history": [{"role": "ai"}] * 9,
}

LISTENING = {
    "flow": {"state": "S1_LISTENING"},
    "noted_problems": [{"ref": "a", "group": "x", "title": "Footfall is low"}],
}


def turn(reply="Do badlav foran karein. Workzap yahan seedha sa kaam kar sakta hai: x"):
    return ServiceTurn(reply=reply)


def test_without_the_box_the_offer_follows_the_ask_as_before():
    t = turn()
    brain_offer(t, {**LISTENING, "solution_asked": True, "reply_language": "en"})
    assert t.reply.endswith(solution_ask.offer_line("en"))
    assert t._decision.next_state == flow.State.S5_READINESS


def test_with_the_box_on_and_not_ready_the_offer_waits():
    t = turn()
    brain_offer(t, {**LISTENING, "box_offer": True, "solution_asked": True, "reply_language": "en"})
    assert t.reply == turn().reply and t._decision is None


def test_with_the_box_ready_the_application_makes_the_offer_after_ideas_and_moves_to_s5():
    t = turn()
    brain_offer(t, {**LISTENING, **BOX_READY, "solution_asked": True, "reply_language": "en"})
    assert t.reply.endswith(solution_ask.offer_line("en"))
    assert t._decision.next_state == flow.State.S5_READINESS
    assert t._decision.brief == {"offer_asked": True}
    assert t.awaiting_customer


def test_no_offer_when_it_was_already_made_or_nothing_is_noted_or_it_is_a_summary():
    for context in (
        {**LISTENING, "flow": {"state": "S5_READINESS"}, "solution_asked": True},
        {"flow": {"state": "S1_LISTENING"}, "solution_asked": True},
        {**LISTENING},
    ):
        t = turn()
        brain_offer(t, context)
        assert t.reply == turn().reply and t._decision is None
    summary = turn()
    summary._summary = True
    brain_offer(summary, {**LISTENING, "solution_asked": True})
    assert summary._decision is None
    decided = turn()
    decided._decision = decisions.Decision("fixed")
    brain_offer(decided, {**LISTENING, "solution_asked": True})
    assert decided._decision.reply == "fixed"


def test_how_exactly_gets_the_offer_too():
    t = turn("Ye solution document mein detail se hota hai: har ad ka alag code.")
    brain_offer(
        t,
        {**LISTENING, **BOX_READY, "solution_howto": {"covers": "x"}, "reply_language": "roman_ur"},
    )
    assert t.reply.endswith(solution_ask.offer_line("roman_ur"))


def test_a_push_for_a_fix_gets_ideas_not_the_summary_when_solution_mode_handed_them():
    said = "Aap jaldi solution do na mujhe"
    base = {**LISTENING, "latest_customer_message": said, "problems_since_summary": 1}
    plain = turn("Ji, batayiye.")
    brain_summary(plain, dict(base))
    assert plain._summary  # without solution mode the push still shows the sorted summary
    given = turn("Do badlav foran karein.")
    brain_summary(given, {**base, "solution_ideas": ["a", "b"], "solution_asked": True})
    assert not given._summary and given.reply == "Do badlav foran karein."


def lint(reply, **extra):
    context = {
        "latest_customer_message": "ye kaise karna hai?",
        "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
        "flow": {"state": "S1_LISTENING"},
        **extra,
    }
    return c.lint(reply, context)


def rules(reply, **extra):
    return {v.rule for v in lint(reply, **extra)}


def test_the_pitch_check_is_relaxed_only_for_a_turn_that_was_asked():
    pitch = "Workzap could set up a message so you know which ad brought each customer."
    assert "R-SELL-01" in rules(pitch)
    assert "R-SELL-01" not in rules(pitch, solution_asked=True)
    assert "R-SELL-01" not in rules(
        "Ye solution document mein hota hai: har ad ka alag code.", solution_howto={}
    )
    assert "R-SELL-01" in rules(
        "Ye solution document mein hota hai.", latest_customer_message="hmm"
    )


def test_a_how_exactly_answer_has_no_steps_and_no_app():
    howto = {"covers": "codes per ad", "which_app": True}
    good = "Ye solution document mein detail se hota hai: har ad ka alag code aur roz ki report."
    assert not {v.rule for v in c.hard(lint(good, solution_howto=howto))}
    steps = "Step 1: har ad mein code daalein. Step 2: sheet banayein."
    assert "R-VAL-04" in {v.rule for v in c.hard(lint(steps, solution_howto=howto))}
    app = "Aap Canva use an app jaise tool install karein ya use an app like Zapier."
    assert "R-VAL-05" in {v.rule for v in c.hard(lint(app, solution_howto=howto))}
    # a named product is a vendor whether or not they asked "which app" (gap closed 2026-10-24)
    assert "R-VAL-05" in {v.rule for v in lint(app, solution_howto={"which_app": False})}
    plain = "Ye solution document mein detail se hota hai: har ad ka alag code aur roz ki report."
    assert "R-VAL-05" not in {v.rule for v in lint(plain, solution_howto={"which_app": False})}


def test_the_workzap_line_rules_for_the_live_reply():
    history = [
        {"role": "ai", "text": "Hi, I'm pi, an AI from Workzap. The lasting fix would be x."}
    ]
    again = "The lasting fix would be that you hear the day stock runs low."
    assert "R-BUILD-04" in rules(again, solution_asked=True, history=history)
    assert "R-BUILD-04" not in rules(again, solution_asked=True)
    assert "R-BUILD-01" in rules("Workzap can build a dashboard for you.", solution_asked=True)
    assert "R-BUILD-01" not in rules(
        "A dashboard works.", solution_asked=True, latest_customer_message="I want a dashboard"
    )
    two = " ".join(
        solutions.build_phrase(k) + "."
        for k in ("stock_alerts", "attribution_codes", "job_tracking")
    )
    assert "R-BUILD-05" in rules(two, solution_asked=True)
    once = solutions.build_phrase("stock_alerts") + "."
    assert "R-BUILD-05" not in rules(once, solution_asked=True)


@pytest.mark.parametrize(
    "said",
    [
        "we fix phones and laptops",
        "koi hal nahi abhi tak",
        "no idea why they leave",
        "customers suggest changes every day",
        "help me understand what happened",
        "log kaise karte hain pata nahi",
        "I have no solution for this",
        "How do I make the payment?",
        "the supplier will fix it next week",
    ],
)
def test_describing_a_problem_never_opens_the_free_ideas_path(said):
    assert not solution_ask.asked_for_ideas(said)
    assert not solution_ask.asked_howto(said)


def test_asking_is_answered_only_while_the_offer_is_still_open_to_talk_about():
    assert "S10_AWAITING_PAYMENT" not in solution_ask.ASKABLE
    assert "S8_REVIEW" not in solution_ask.ASKABLE
    assert {"S1_LISTENING", "S4_SORTED_SUMMARY", "S5_READINESS"} <= set(solution_ask.ASKABLE)


def test_a_cost_question_keeps_the_fixed_answer_even_when_ideas_were_handed_over():
    said = "how much will it cost?"
    base = {**LISTENING, "latest_customer_message": said, "problems_since_summary": 1}
    t = turn("A quote says it.")
    brain_summary(t, {**base, "solution_ideas": ["a"]})  # S4 and S5 hand ideas over unasked
    assert t._summary  # the summary and the fixed cost answer, never the model's free answer
    assert not solution_ask.asked_for_ideas(said)


def test_a_given_turn_may_not_pitch_offer_or_price():
    asked = {"solution_asked": True}

    def hard(reply, **extra):
        return {v.rule for v in c.hard(lint(reply, **{**asked, **extra}))}

    assert "R-SELL-01" in hard("Nori can read it every morning for you.")
    assert "R-SELL-01" in hard("Our product would send it each day.")
    assert "R-SELL-01" in hard("I'd recommend a daily check.")
    assert "R-OFFER-03" in hard("Shall I send you a quote?")
    assert "R-OFFER-03" in hard("It goes in the solution document.")
    assert "R-OFFER-05" in hard("It would take 20k rupees to build.")
    assert "R-OFFER-05" in hard("It costs a few lakh.")
    howto = {v.rule for v in c.hard(lint("It goes in the solution document.", solution_howto={}))}
    assert "R-OFFER-03" not in howto
    assert "R-BUILD-06" in {v.rule for v in lint("Workzap will fix it.", solution_asked=True)}
    clean = "Do badlav foran karein. Workzap would send each manager a message when stock runs low."
    assert not hard(clean)


def test_how_exactly_reasons_carry_their_own_rule_ids():
    howto = {"covers": "x", "which_app": False}
    three = chr(10).join(["• Ek idea hai.", "• Doosra idea hai.", "• Teesra idea hai."])
    assert "R-VAL-01" in {v.rule for v in c.hard(lint(three, solution_howto=howto))}
    tools = "Workzap would build a dashboard for you."
    assert "R-BUILD-01" in {v.rule for v in lint(tools, solution_howto=howto)}


def test_the_build_line_must_actually_name_workzap_not_read_as_a_third_idea():
    # Found by the grader on a real simulation: the data handed over was correct, but the
    # rendered reply dropped the opener and never said Workzap at all (R-BUILD-03).
    build = {
        "says": "Har customer ka baqaya likha rahe aur waqt par narmi se yaad-dahani chali jaye",
        "opener": solutions.BRIDGE_OPENERS[0]["roman_ur"],
    }
    unattributed = (
        "Theek hai, seedha solution.\n• Idea ek.\n• Idea do.\n"
        "Har customer ka baqaya likha rahe aur waqt par narmi se yaad-dahani chali jaye"
    )
    assert "R-BUILD-03" in rules(unattributed, solution_asked=True, solution_build=build)
    named = (
        "Theek hai, seedha solution.\n• Idea ek.\n• Idea do.\n"
        f"{build['opener']}, Workzap har customer ka baqaya likha rahe."
    )
    assert "R-BUILD-03" not in rules(named, solution_asked=True, solution_build=build)
    # A referred-back line (already said once) needs no re-attribution.
    assert "R-BUILD-03" not in rules(
        unattributed, solution_asked=True, solution_build={"refer_back": True}
    )
    # No solution_build at all (e.g. the problem has no build keys): nothing to check.
    assert "R-BUILD-03" not in rules(unattributed, solution_asked=True)


def test_live_chat_push_phrasings_from_2026_10_24_count_as_asking_for_a_fix() -> None:
    """Production chat: 'Ap solution dw' and 'B's yehi agy bnwao' were treated as plain answers."""
    from app.modules.pi.problems import WHAT_NOW
    from app.modules.pi.solution_ask import asked_for_ideas

    for said in ("Ap solution dw", "B's yehi agy bnwao", "ye bana do", "can you build this for me"):
        assert asked_for_ideas(said), said
        assert WHAT_NOW.search(said), said
    # Describing a problem is still not a request.
    for said in ("we fix phones", "customers ask how much it costs", "koi hal nahi hai"):
        assert not asked_for_ideas(said), said


def test_the_owners_own_loss_does_not_count_as_pushing_for_a_fix() -> None:
    """Real sweep: 'I am not sure how much we lose' brought an early summary and ideas."""
    from app.modules.pi.problems import what_now
    from app.modules.pi.solution_ask import asked_for_ideas

    for said in (
        "Yes, it happens every week and I am not sure how much we lose because of it.",
        "Haan, har hafte hota hai aur nuksan ka andaza nahi hota.",
        "kitna nuksan hota hai pata nahi, kabhi kabhi zyada",
    ):
        assert not what_now(said), said
        assert not asked_for_ideas(said), said
    for said in ("what now?", "so what can you do", "kuch kar sakte ho", "how much would it cost"):
        assert what_now(said), said


def test_the_card_reminder_is_not_said_twice_when_the_model_repeats_it() -> None:
    from app.modules.pi.service_conversation import without_repeated_sentences

    notice = (
        "Meherbani karke yahan card number na bhejein. Mujhe in ki zaroorat nahi, aur payment is "
        "chat mein kabhi nahi hoti. Maine ise apne notes se nikaal diya hai."
    )
    echoed = (
        "Meherbani karke card number yahan na bhejein. Mujhe is ki zaroorat nahi, aur payment is "
        "chat mein kabhi nahi hoti. Maine isay apne notes se nikaal diya hai."
    )
    assert without_repeated_sentences(notice, echoed) == ""
    own = "Aap ka masla note hai. Kya aap bata sakte hain ke payment kab aati hai?"
    assert without_repeated_sentences(notice, f"{echoed} {own}") == own


def test_a_live_roman_urdu_promise_that_the_document_is_being_prepared_is_caught() -> None:
    from app.modules.pi.service_conversation import PROMISED_DOCUMENT

    # live chat 2026-10-26: a bare "g" was answered with this before any yes to the offer
    assert PROMISED_DOCUMENT.search(
        "Ji, document aur quote prepare ho rahe hain. Yahin chat mein aayega."
    )
    assert not PROMISED_DOCUMENT.search(
        "Kya aap in sab ke liye solution document aur quote chahenge?"
    )


def test_a_chat_that_began_before_brain_mode_is_told_once_that_pi_is_an_ai() -> None:
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import brain_context

    policy = SimpleNamespace(response_rules={"pi_mode": "brain"})

    def ai(body: str) -> SimpleNamespace:
        return SimpleNamespace(sender_type="ai", body=body)

    old_chat = SimpleNamespace(flow_state=None, flow_state_since=None)
    context = brain_context(policy, old_chat, [ai("Hi SAW. How can I help you today?")])  # type: ignore[arg-type]
    assert context["legacy_undisclosed"] is True and old_chat.flow_state == "S1_LISTENING"
    told = SimpleNamespace(flow_state=None, flow_state_since=None)
    context = brain_context(policy, told, [ai("Hi, I'm pi, an AI from Workzap.")])  # type: ignore[arg-type]
    assert context["legacy_undisclosed"] is False
    fresh = SimpleNamespace(flow_state=None, flow_state_since=None)
    assert brain_context(policy, fresh, [])["legacy_undisclosed"] is False  # type: ignore[arg-type]
