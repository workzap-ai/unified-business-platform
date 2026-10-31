# ruff: noqa: E501  (the owner's words are kept whole)
"""Platform spec v1.6, Part 19 (Engagement Engine v2.5), from Live Audit 6: the Artwing Studios chat of
30 October. Tests BS1-BS6 (buying signals), DQ (direct questions), PR1-PR8 (what counts as a problem),
NU1 (the owner's number), DE1-DE3 (no dead ends), SM1-SM3 (summaries), BD (the board is what was sent)."""

import pytest

from app.modules.pi import brain_visuals, decisions, part19, problems, style, turn_coverage
from app.modules.pi.service_conversation import (
    NO_IDEA_AGAIN,
    NO_IDEA_THIRD,
    NO_MORE_IDEAS,
)

WANTS = [
    "ads that bring customers",
    "online payment",
    "website with a link",
    "sales manager follow-up",
    "customer onboarding and service",
]


# --- 19.2 buying signals -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "said",
    [
        "kitna kharcha hoga yeh usb karnay ka?",  # BS1
        "bhai mujhay quote do abhi wohi pooch raha hoan",  # BS2
        "How much will this cost?",  # BS6, English
        "send me the quote",
    ],
)
def test_bs_r1_price_and_quote_asks_are_signals(said):
    assert part19.buying_signal(said, 1) == "R1"


def test_bs3_budget_ready_is_r3_with_a_brief():
    assert (
        part19.buying_signal("Hum budget lagane ke liye ready hain", 5) == "R3"
    )  # voice transcript
    assert part19.buying_signal("kab shuru kar sakte hain", 3) == "R3"


def test_bs3_budget_ready_needs_a_brief_and_a_plain_yes():
    assert part19.buying_signal("Hum budget lagane ke liye ready hain", 1) is None
    assert part19.buying_signal("budget nahi hai abhi", 5) is None


@pytest.mark.parametrize(
    "said", ["kitna nuksan hota hai hamara", "the cashiers come late", "quote nahi chahiye"]
)
def test_other_words_are_not_signals(said):
    assert part19.buying_signal(said, 3) is None


@pytest.mark.parametrize(
    "said",
    [
        "mera budget kam hai",  # a small budget is not a buying signal
        "budget tight hai abhi",
        "kab shuru hota hai shift",  # when does the shift start
        "the order is ready to go",
        "kitne ka maal kharab hua is mahine",  # the owner's own waste
        "I don't know how much is going out every month",
        "kitna maal zaya hota hai",
        "quote lagana do hafte mein",  # "do" is two here
        "I need a quote from my supplier, please",
    ],
)
def test_audit_false_positives_are_not_signals(said):
    assert part19.buying_signal(said, 5) is None


def test_audit_a_price_question_with_a_problem_in_it_is_not_dropped_as_a_problem():
    said = (
        "customers keep asking the price before they visit and then we lose them because nobody "
        "answers on WhatsApp fast, what should I do?"
    )
    assert part19.not_a_problem([said]) is None


def test_audit_wants_are_redacted_like_a_problem_note():
    brief = part19.merge_wants({}, ["pay by card 4111 1111 1111 1111", "call me on 0300 1234567"])
    assert not any(ch.isdigit() for want in brief["wants"] for ch in want)


def test_audit_a_signal_reply_never_carries_a_price_and_ends_with_no_question():
    facts = {
        "can_approve": True,
        "problem_count": 2,
        "problem_refs": ["a", "b"],
        "brief": {},
        "buying_signal": "R1",
        "message_id": "m1",
    }
    decision = decisions.decide(decisions.State.S3_NOTED, "mujhay quote do abhi", "roman_ur", facts)
    assert decision is not None and decision.why == "R-OFFER-03"
    reply = f"{decision.reply}\n{part19.covers_lines('roman_ur', ['ads', 'online payment'])}"
    assert not any(ch.isdigit() for ch in reply)
    assert "?" not in reply
    for banned in ("price", "qeemat", "$", "Rs", "bank", "account"):
        assert banned not in reply


def _gate(said, covers=1):
    """What production passes to the decision gate (service_conversation.brain_decision)."""
    return decisions.decide(
        decisions.State.S3_NOTED,
        said,
        "roman_ur",
        {
            "can_approve": True,
            "problem_count": 1,
            "problem_refs": ["a"],
            "brief": {},
            "buying_signal": part19.gate_signal(said, covers),
            "message_id": "m1",
        },
    )


def test_bs_an_explicit_quote_ask_starts_the_quote_through_the_decision_gate():
    decision = _gate("mujhay quote do abhi")
    assert decision is not None and decision.why == "R-OFFER-03"
    assert "request_solution" in decision.effects
    assert not any(c.isdigit() for c in decision.reply)  # BS4: no price number


@pytest.mark.parametrize(
    "said",
    ["kitna kharcha hoga yeh usb karnay ka?", "how much will it cost?", "how much would it cost?"],
)
def test_bs1_a_price_question_is_an_offer_signal_but_does_not_start_the_quote(said):
    # D-1 (approved by the owner, delegated recommended decisions 2026-10-31): deviates from spec v1.6 19.2 BS1/BS6
    assert part19.buying_signal(said, 1) == "R1"
    assert part19.gate_signal(said, 1) is None
    decision = _gate(said)
    assert decision is None or "request_solution" not in decision.effects


@pytest.mark.parametrize(
    "said,expected",
    [
        ("send me the quote", True),
        ("mujhay quote do abhi", True),
        ("give me the quote", True),
        ("how much will it cost?", False),
        ("kitna kharcha hoga yeh usb karnay ka?", False),
        ("I send the quote to customers late", False),
        ("we give the quote after two days", False),
        ("quote nahi chahiye", False),
        ("send me the quote later", False),
        # statements about the owner's own work, or about others: never a request (audit H1)
        ("customers ask me to send the quote", False),
        ("my team forgets to send the quote", False),
        ("it takes me hours to send a quote", False),
        ("customers ko quote chahiye hota hai, mujhe banane mein time lagta hai", False),
        ("don't send the quote", False),
        ("give me the price", False),  # D-1: a price ask does not start the quote
        # real asks with a lead-in or a trailing remark (audit M1)
        ("I sent you the details, send me the quote", True),
        ("I said give me the quote", True),
        ("maine bata diya, ab quote do", True),
        ("main ne sab bata diya, mujhay quote do abhi", True),
        ("humne sab bata diya, quote bhejo", True),
        ("send me the quote, I am short of time", True),
        ("We need a quote, send me the quote", False),  # fail closed: not one imperative clause
        ("can you send me the quote?", True),
        # audit round 3: fail closed
        ("Our orders get lost, we need a quote system that tracks them", False),
        ("My staff is slow. We need a quote template for every customer", False),
        ("Customers wait for days, so I need a quote tool", False),
        ("We want a document scanner for the shop", False),
        ("We told you we need a quote system", False),
        ("Don't send me the quote now. I need a quote only when I say so", False),
        ("I can't pay yet, I need a quote template", False),
        ("Customers ask for the price, we need a quote each time", False),
        ("My customers say, send me the quote", False),
        ("no, don't send the quote", False),
        ("catering ke liye quote bhej dein", False),  # GAP-2: accepted false negative
        ("So send me the quote", True),
        ("But send the quote", True),
        ("aur quote bhej dein", True),
        ("send me the rough quote", True),
        ("send me the final proposal please", True),
        ("quote bhej dein na", True),
        ("send me the quote, no rush", True),
        ("I already told you, send me the quote", True),
        ("I want you to send me the quote", True),
        ("please prepare the solution document now", True),
        # audit round 4: process statements and conditionals fail closed
        ("Every morning I check the orders and make a quote", False),
        ("Customer calls, I note the details, prepare the quote", False),
        ("We take the order and send the quote", False),
        ("If I like the idea, send me the quote", False),
        ("Once I decide, send me the quote", False),
        ("When I'm ready, send me the quote", False),
        ("jab main kahoon, quote bhej do", False),
        ("agar theek laga, quote bhej do", False),
        ("I need a quote system that tracks orders", False),
        ("We need a quote template for every customer", False),
        ("Quote banane mein bohat time lagta hai", False),
        ("Hamein quote chahiye hota hai", False),
        ("I gave you everything, send me the quote", True),
        ("maine sab bata diya, quote bhej do", True),
        ("please send me the quote", True),
        ("mujhay quote do abhi", True),
    ],
)
def test_asks_for_the_quote_is_an_explicit_ask_only(said, expected):
    assert part19.asks_for_the_quote(said) is expected


def test_bs5_a_thin_set_adds_the_one_line_to_widen_and_a_full_one_does_not():
    thin = part19.covers_lines("roman_ur", ["Sales kam hain"])
    full = part19.covers_lines("roman_ur", ["ads", "payment"])
    assert "shamil karni ho" in thin
    assert "shamil karni ho" not in full
    assert "ads" in full and "?" not in thin + full


# --- 19.3 direct questions -----------------------------------------------------------------------
def test_dq3_listen_again_gets_a_playback_of_what_was_understood():
    assert part19.asks_replay("Yeh wapis sunay please")
    line = part19.playback("roman_ur", ["Ideas pehle ho chuke", *WANTS[:2]])
    assert line.startswith("Ji, jo maine suna") and "online payment" in line


def test_dq4_one_message_with_two_questions_must_answer_both():
    texts = ["Aap ko iskay baray mai kuch pata hai? Aap ye sab kaam kar denge hamein?"]
    assert turn_coverage.skipped_question("Theek hai. Ab batayein.", texts)
    covered = "Abhi nahi, link bhej dein. Haan, Workzap ye sab kaam kar sakta hai."
    assert turn_coverage.skipped_question(covered, ["Salam"]) is None


# --- 19.4 what counts as a problem ---------------------------------------------------------------
def test_pr1_a_price_question_creates_no_problem():
    assert part19.not_a_problem(["kitna kharcha hoga yeh usb karnay ka?"])


def test_pr2_frustration_with_pi_creates_no_problem_and_is_a_repair_signal():
    said = "bhai kitni baar bataon mai ik he baat"
    assert part19.not_a_problem([said])
    from app.modules.pi import box_signals

    assert box_signals.REPEAT_COMPLAINT.search(said)  # trust falling


def test_pr4_a_goal_alone_is_not_a_problem_but_a_problem_with_a_goal_is():
    assert part19.not_a_problem(["apni sales badhani hai"])
    assert part19.not_a_problem(["sales are low and we want to grow"]) is None


def test_pr3_the_voice_note_problems_are_not_filtered():
    for words in (
        "ye hum already karte hain lekin isse koi faida nahi ho raha humey sales ka",
        "Referring say sirf, teen mahine mein ek bhi paid kaam nahi bana",
    ):
        assert part19.not_a_problem([words]) is None


def test_pr_check_ops_drops_a_price_question_made_into_a_problem():
    note = problems.ProblemNote(
        title="Cost of the USB",
        user_words=["kitna kharcha hoga yeh usb karnay ka?"],
        category="cash_collections",
    )
    issue = problems.check_ops([problems.ProblemOp(op="create", note=note)], set(), True)
    assert issue and "question about price" in issue


def test_pr_wants_are_kept_apart_without_repeats():
    brief = part19.merge_wants({}, WANTS[:3])
    brief = part19.merge_wants(brief, ["Online payment", "ads that bring customers", "onboarding"])
    assert brief["wants"] == [*WANTS[:3], "onboarding"]


def test_pr_wants_need_a_wording_that_says_so():
    assert part19.want_cue(
        "Hamein ads chalani hain aur customer ki payment online karvani hai website ke saath"
    )
    assert not part19.want_cue("Referring say sirf")


# --- 19.5 the owner's number ---------------------------------------------------------------------
def test_nu1_a_reply_to_zero_uses_the_number():
    bad = "Here is what I have noted so far. Is anything wrong or missing?"
    good = "Zero ka matlab hai ke referral hi ek source hai aur teen mahine mein ek bhi paid kaam nahi bana. Enquiries kam aati hain?"
    assert part19.number_used(bad, "Zero")
    assert part19.number_used(good, "Zero") is None
    assert part19.number_used("ek bhi nahi bana", "Zero") is None
    assert (
        part19.number_used("anything", "How many referral enquiries became paid jobs?") is None
    )  # a question


# --- 19.6 no dead ends ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "reply",
    [
        "Wo sab yahan note hai. Ab main koi naya sawal nahi poochhunga.",  # DE1, DE2
        "Is masle ke liye yahan itne hi ideas hain.",  # DE3
        "Those are the ideas I have for this here.",
        "Inme se abhi kuch bhi hal nahi hua.",
        "Here is what I have noted. None of it is solved yet.",
    ],
)
def test_de_dead_ends_and_false_claims_are_caught(reply):
    assert part19.dead_end(reply)


def test_de_the_fixed_lines_are_not_dead_ends_and_end_in_one_question():
    for table in (NO_MORE_IDEAS, NO_IDEA_AGAIN, NO_IDEA_THIRD):
        for language, line in table.items():
            assert part19.dead_end(line) is None, (language, line)
            assert line.count("?") + line.count("؟") == 1


def test_de_the_repair_steps_never_promise_to_stop_asking():
    for step in (4, 5):
        assert (
            "Never" in style.REPAIR[step]
            and "stop asking" in style.REPAIR[step]
            or "no more questions" in style.REPAIR[step]
        )


# --- 19.7 summaries ------------------------------------------------------------------------------
def context(sent_at=None, ai=12):
    return {
        "brief": {"summary_at": sent_at} if sent_at is not None else {},
        "history": [{"role": "ai", "text": "x"}] * ai,
    }


def test_sm1_a_quote_request_never_gets_a_summary():
    ctx = context()
    assert part19.summary_blocked(ctx, "mujhay quote do abhi", "document_asked")
    assert part19.checkpoint_due(ctx, "kitna kharcha hoga?", 4) is None
    assert part19.summary_blocked(ctx, "mujhay quote do abhi", "checkpoint")


def test_sm2_no_repeat_within_ten_messages():
    assert part19.summary_blocked(context(sent_at=5, ai=12), "ok theek hai", "done")
    assert not part19.summary_blocked(context(sent_at=2, ai=12), "ok theek hai", "done")
    assert part19.checkpoint_due(context(sent_at=8, ai=12), "ok", 4) is None  # fewer than 8 since
    assert part19.checkpoint_due(context(sent_at=2, ai=12), "ok", 4) == "checkpoint"
    assert part19.checkpoint_due(context(), "ok", 2) is None  # fewer than 3 problems
    assert part19.checkpoint_due(context(), "kya hua?", 5) is None  # mid-question


def test_sm_a_number_is_not_answered_with_a_summary():
    assert part19.summary_blocked(context(), "Zero", "checkpoint")
    assert problems.summary_due("Zero", 4, 4) is None


def test_sm3_an_explicit_ask_lists_every_problem_and_the_wants_with_one_question():
    assert problems.summary_due("List down all the problems i have discussed here", 3, 3) == "show"
    items = [{"category": "sales_revenue", "title": f"Problem {n}"} for n in range(1, 16)]
    text = problems.summary_message(items, "en", WANTS)
    assert all(f"Problem {n}" in text for n in range(1, 16))  # none hidden, however many
    assert all(w in text for w in WANTS)
    assert text.count("?") == 1 and text.rstrip().endswith("?")
    lowered = text.lower()
    assert "none of it is solved" not in lowered and "wrong or missing" not in lowered


def test_sm_the_old_summary_triggers_no_longer_fire_on_their_own():
    assert problems.summary_due("hmm", 9, 9) is None
    assert problems.summary_due("ok", 3, 3, quiet_replies=5) is None
    assert problems.summary_due("that's all", 2, 0) == "done"  # an explicit end still shows it


# --- 19.8 the board is what was sent -------------------------------------------------------------
def test_bd_the_board_link_carries_the_groups_it_was_drawn_from():

    groups = [brain_visuals.Group("Sales", 3, ["referral only", "no pipeline"])]
    snap = brain_visuals.snapshot_of(groups)
    assert snap == [["Sales", 3, ["referral only", "no pipeline"]]]
    assert brain_visuals.snapshot_of([]) == []


# --- the four blocking findings of the rule audit (2026-10-30) ----------------------------------------
def test_audit_r3_opens_the_offer_and_never_starts_the_quote_without_the_yes():
    from app.modules.pi import box, box_signals

    said = "Hum budget lagane ke liye ready hain"
    assert part19.ready_to_buy(said) and box_signals.asks_who_or_how_long(
        said
    )  # R3 opens the offer
    allowed, rule, _ = box.can_offer(box.OfferFacts(asked_who_or_how_long=True))
    assert allowed and rule == "R3"
    # the production wiring passes only an R1 signal to the decision gate: with none, "budget ready"
    # alone is no yes and starts nothing
    facts = {"can_approve": True, "problem_count": 3, "problem_refs": ["a"], "brief": {}}
    decision = decisions.decide(decisions.State.S3_NOTED, said, "roman_ur", facts)
    assert decision is None or "request_solution" not in decision.effects
    assert not part19.ready_to_buy("mera budget kam hai")


def test_audit_one_question_per_message_when_the_offer_follows_a_fixed_no_ideas_line():
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import NO_MORE_IDEAS, brain_offer

    turn = SimpleNamespace(
        reply=NO_MORE_IDEAS["roman_ur"],
        _summary=False,
        _decision=None,
        awaiting_customer=False,
        problem_ops=[],
    )
    ctx = {
        "latest_customer_message": "mujhay quote do abhi",
        "flow": {"state": "S3_NOTED"},
        "noted_problems": [{"ref": "a", "title": "x"}],
        "brief": {},
        "history": [],
        "box_offer": True,
        "solution_asked": True,
        "reply_language": "roman_ur",
    }
    brain_offer(turn, ctx)
    assert turn.reply.count("?") + turn.reply.count("؟") == 1  # the offer is the only question
    assert turn.reply.rstrip().endswith("?") and NO_MORE_IDEAS["roman_ur"] not in turn.reply


def test_audit_the_fixed_no_ideas_lines_are_one_plain_question_and_claim_nothing_unsaid():
    for table in (NO_MORE_IDEAS, NO_IDEA_AGAIN, NO_IDEA_THIRD):
        for line in table.values():
            assert line.count("?") + line.count("؟") == 1, line
    assert "did not help" not in NO_MORE_IDEAS["en"]  # the owner may never have said so


def test_audit_a_phone_number_cut_at_the_boundary_does_not_escape_the_redactor():
    brief = part19.merge_wants({}, ["x" * 112 + " call 0300 1234567 now"])
    assert not any(ch.isdigit() for ch in brief["wants"][0])


def test_audit_the_wants_prompt_asks_for_roles_not_names():
    from app.modules.pi import problem_extract

    assert "Never write a person's name" in problem_extract.WANTS_SYSTEM


def test_audit_the_board_link_carries_no_words_of_the_owner():
    import base64
    import json
    import uuid
    from types import SimpleNamespace

    from pydantic import SecretStr

    settings = SimpleNamespace(secrets_encryption_key=SecretStr("k" * 32))
    link = brain_visuals.token(settings, uuid.uuid4(), "board", "en", message="m-1")
    claims = json.loads(base64.urlsafe_b64decode(link.split(".")[0] + "=="))
    assert claims["m"] == "m-1" and "g" not in claims
    groups = brain_visuals.groups_from_snapshot([["Sales", 2, ["referral only"]], "bad"])
    assert [(g.label, g.count) for g in groups] == [("Sales", 2)]


def test_audit_a_playback_is_never_the_first_message_and_urdu_dead_ends_are_caught():
    from types import SimpleNamespace

    turn = SimpleNamespace(
        reply="Hi, I'm pi.", _summary=False, _decision=None, awaiting_customer=False
    )
    part19.replay(turn, {"latest_customer_message": "Yeh wapis sunay please", "history": []})
    assert turn.reply == "Hi, I'm pi."
    assert part19.dead_end("میں کوئی نیا سوال نہیں پوچھوں گا")


# --- owner decision on R3, and the final assembled text (2026-10-30) ------------------------------------
def test_r3_never_goes_to_prepare_only_r1_does():
    base = {"can_approve": True, "problem_count": 3, "problem_refs": ["a"], "brief": {}}
    said = "Hum budget lagane ke liye ready hain"
    r3 = decisions.decide(
        decisions.State.S3_NOTED, said, "roman_ur", {**base, "buying_signal": "R3"}
    )
    assert r3 is None or "request_solution" not in r3.effects  # R3 gives no _prepare
    r1 = decisions.decide(
        decisions.State.S3_NOTED,
        "mujhay quote do abhi",
        "roman_ur",
        {**base, "buying_signal": "R1", "message_id": "m1"},
    )
    assert r1 is not None and r1.why == "R-OFFER-03" and "request_solution" in r1.effects


@pytest.mark.parametrize("said", ["ok", "hmm", "maybe", "let me think", "Ok.", "acha"])
def test_an_acknowledgement_is_never_an_explicit_yes(said):
    answer, sure = decisions.classify(said)
    assert not (answer == decisions.Answer.YES and sure >= decisions.YES_AT)


@pytest.mark.parametrize("table_name", ["NO_MORE_IDEAS", "NO_IDEA_AGAIN", "NO_IDEA_THIRD"])
@pytest.mark.parametrize("language", ["en", "roman_ur", "ar"])
def test_the_final_text_of_a_no_ideas_line_and_the_offer_has_one_question_and_it_is_last(
    table_name, language
):
    from types import SimpleNamespace

    from app.modules.pi import service_conversation as sc

    line = getattr(sc, table_name)[language]
    turn = SimpleNamespace(
        reply=line, _summary=False, _decision=None, awaiting_customer=False, problem_ops=[]
    )
    ctx = {
        "latest_customer_message": "mujhay quote do abhi",
        "flow": {"state": "S3_NOTED"},
        "noted_problems": [{"ref": "a", "title": "x"}],
        "brief": {},
        "history": [],
        "box_offer": True,
        "solution_asked": True,
        "reply_language": language,
    }
    sc.brain_offer(turn, ctx)
    final = turn.reply.rstrip()
    assert final.count("?") + final.count("؟") == 1, final
    assert final.endswith(("?", "؟")), final
    assert line not in final  # the fixed question gave way: the offer is the only question
    assert part19.dead_end(final) is None


def test_a_third_party_in_a_want_is_kept_as_a_role_and_nothing_downstream_sees_the_name():
    brief = part19.merge_wants({}, ["follow-up by my cashier Ahmed Khan on WhatsApp"])
    assert "Ahmed" not in brief["wants"][0]
    text = problems.summary_message([], "en", brief["wants"])
    assert "Ahmed" not in text
    assert "Ahmed" not in part19.playback("en", brief["wants"])
    assert "Ahmed" not in part19.covers_lines("en", brief["wants"])


def test_the_covers_lines_promise_nothing_in_any_language():
    for language in ("en", "roman_ur", "ar"):
        lines = part19.covers_lines(language, ["ads"])
        for banned in ("build on this", "bana dete", "نبني", "will cover", "aaye ga"):
            assert banned not in lines


# --- re-audit blockers: the FINAL text, and a model reply that already ends in a question -----------
LATE_QUESTIONS = {
    "en": "Welcome back. Shall we carry on?",
    "roman_ur": "Wapis khush aamdeed. Kya baat jaari rakhein?",
    "ar": "أهلاً بعودتك. هل نتابع؟",
}
MODEL_ENDS_IN_QUESTION = {
    "en": "Count how many enquiries come each week. Which source brings most of them?",
    "roman_ur": "Har hafte ki enquiries ginein. Sab se zyada kis source se aati hain?",
    "ar": "احسب عدد الاستفسارات كل أسبوع. من أي مصدر يأتي معظمها؟",
}


def _offer_context(language):
    return {
        "latest_customer_message": "mujhay quote do abhi",
        "flow": {"state": "S3_NOTED"},
        "noted_problems": [{"ref": "a", "title": "x"}],
        "brief": {},
        "history": [],
        "box_offer": True,
        "solution_asked": True,
        "reply_language": language,
    }


@pytest.mark.parametrize("language", ["en", "roman_ur", "ar"])
def test_a_model_reply_ending_in_a_question_loses_it_before_the_offer(language):
    from types import SimpleNamespace

    from app.modules.pi import service_conversation as sc

    turn = SimpleNamespace(
        reply=MODEL_ENDS_IN_QUESTION[language],
        _summary=False,
        _decision=None,
        awaiting_customer=False,
        problem_ops=[],
    )
    sc.brain_offer(turn, _offer_context(language))
    final = turn.reply.rstrip()
    assert final.count("?") + final.count("؟") == 1, final
    assert final.endswith(("?", "؟"))
    assert MODEL_ENDS_IN_QUESTION[language].split(".")[0] in final  # the statements stay


@pytest.mark.parametrize("language", ["en", "roman_ur", "ar"])
def test_the_final_text_after_the_late_lines_has_one_question_and_it_is_last(language):
    from types import SimpleNamespace

    from app.modules.pi import constitution
    from app.modules.pi import service_conversation as sc

    turn = SimpleNamespace(
        reply=MODEL_ENDS_IN_QUESTION[language],
        _summary=False,
        _decision=None,
        awaiting_customer=False,
        problem_ops=[],
    )
    sc.brain_offer(turn, _offer_context(language))
    # the lines the pipeline prepends or appends after the last lint: a welcome back with a question,
    # a handoff line, an open-items line, a notice
    late = f"{LATE_QUESTIONS[language]} {turn.reply}\n\nPlease note one thing. Is that fine?"
    final = constitution.final_one_question(late)
    assert final.count("?") + final.count("؟") == 1, final
    assert final.rstrip().endswith(("?", "؟")), final
    assert constitution.final_one_question("A statement only.") == "A statement only."
    assert constitution.final_one_question("One question?") == "One question?"


def test_the_pipeline_runs_the_final_check_after_the_last_append():
    import inspect

    from app.modules.pi import service_conversation as sc

    source = inspect.getsource(sc)
    tail = source[source.rindex("openingGate pass") :]
    before_return = tail.split("return turn")[0]
    assert "constitution.final_one_question(" in before_return
    assert 'keep=context.get("fixed_lines")' in before_return  # the fixed lines are protected


def test_the_cost_lines_name_the_review_and_listening_lines_name_no_document():
    from app.modules.pi import decisions
    from app.modules.pi import service_conversation as sc

    for language in ("en", "roman_ur", "ar"):
        text = decisions.text("preparing", language)
        assert any(w in text for w in ("review", "review", "يراجع")), text
        line = sc.NO_IDEA_LINES[language]
        assert "document" not in line.lower() and "وثيقة" not in line  # no document while listening


def test_kitna_lagega_for_time_is_not_a_price_ask():
    assert part19.buying_signal("kitna lagega yeh usb karnay ka?", 1) == "R1"
    assert part19.buying_signal("kitna lagega time is kaam mein", 1) is None


# --- third re-audit: Urdu script, durations, trailing closers, and links ---------------------------
def test_statement_only_keeps_every_sentence_and_turns_the_question_into_a_statement():
    line = "یہ آپ کا مسئلہ ہے۔ کیا آپ نے کوشش کی؟"
    assert part19.statement_only(line) == "یہ آپ کا مسئلہ ہے۔ کیا آپ نے کوشش کی."
    assert part19.statement_only("यह आपकी समस्या है। क्या आपने कोशिश की?") == (
        "यह आपकी समस्या है। क्या आपने कोशिश की."
    )
    assert part19.statement_only("Noted. Which one?") == "Noted. Which one."


@pytest.mark.parametrize(
    "said",
    [
        "kitna lagega ghante",
        "kitna lagega ghanta",
        "kitna lagega saal",
        "kitna lagega weeks",
        "kitna lagega months",
        "kitna lagega days",
        "kitna lagega hours",
        "kitna lagega minutes",
    ],
)
def test_a_duration_after_kitna_lagega_is_not_a_price_ask(said):
    assert part19.buying_signal(said, 1) is None


def test_a_closer_or_an_emoji_after_a_question_does_not_hide_it():
    from app.modules.pi import constitution

    final = constitution.final_one_question("First *Which one?* Then: Is that fine? 😊")
    assert part19.question_count(part19.normalise_question_marks(final)) == 1
    assert part19.ends_in_question(final)
    bold = "Intro.\n*Which one?*"
    assert constitution.final_one_question(bold) == bold  # one question, last: untouched
    wide = constitution.final_one_question("Is it A？ Or is it B⁇")
    assert part19.question_count(part19.normalise_question_marks(wide)) == 1


def test_a_question_mark_in_a_link_is_not_a_question_and_is_never_rewritten():
    from app.modules.pi import constitution

    link = "https://meet.example.com/j?id=42&pwd=x"
    kept = f"Your meeting link:\n*Zoom*\n{link}"
    assert constitution.final_one_question(kept) == kept  # no question at all
    two = f"Why? Link {link} bye. When?"
    fixed = constitution.final_one_question(two)
    assert link in fixed  # the query string survives
    assert part19.question_count(part19.protect_urls(fixed)[0]) == 1
    assert fixed.rstrip().endswith("?")
    bullets = f"Ideas:\n• see {link}\nWhich one? Or which other?"
    assert link in constitution.final_one_question(bullets)


# --- fourth re-audit: marks glued to emoji, protected questions, abbreviations, links ----------------
UNSPACED = [
    "Is it A?😊 Is it B?",
    "Is it A?\u200f Is it B?",
    "هل هذا أ؟\u200fهل هذا ب؟",
    "Is it A?\u200cIs it B?",
    "Is it A?\u200dIs it B?",
    "Is it A?😊Is it B?",
    "*Noted.* Which one? Or which other?",
    "Is it A？ Or B⁇ Or C?",
]


@pytest.mark.parametrize("text", UNSPACED)
def test_the_final_text_never_keeps_more_than_one_question(text):
    from app.modules.pi import constitution

    final = constitution.final_one_question(text)
    flat = part19.normalise_question_marks(part19.protect_urls(final)[0])
    assert part19.question_count(flat) <= 1, final


def test_a_question_sentence_that_discloses_the_ai_is_kept_as_a_statement():
    from app.modules.pi import constitution

    final = constitution.final_one_question(
        "I'm pi, an AI, what does your business do? Shall I make the quote?"
    )
    assert "I'm pi, an AI, what does your business do." in final
    assert final.rstrip().endswith("Shall I make the quote?")
    assert part19.question_count(final) == 1


def test_a_refusal_or_a_safety_line_is_kept_as_a_statement_too():
    from app.modules.pi import constitution

    refusal = constitution.final_one_question(
        "I never ask for a card number or a password, is that clear? What is your business?"
    )
    assert "I never ask for a card number or a password, is that clear." in refusal
    assert refusal.rstrip().endswith("What is your business?")
    safety = constitution.final_one_question(
        "Please call the emergency number 1122 and an ambulance now, is anyone hurt? Which city?"
    )
    assert "is anyone hurt." in safety and safety.rstrip().endswith("Which city?")


def test_a_fixed_line_given_to_the_check_is_kept():
    from app.modules.pi import constitution

    final = constitution.final_one_question(
        "Your reference is A1, is that right? What next?", keep=["Your reference is A1"]
    )
    assert "Your reference is A1, is that right." in final
    assert final.rstrip().endswith("What next?")


@pytest.mark.parametrize(
    ("text", "left"),
    [
        ("Is it e.g. a van?", "Is it e.g. a van."),
        ("Rs. 500 kitna?", "Rs. 500 kitna."),
        ("1. Which one?", "1. Which one."),
        ("*Noted.* Which one?", "Noted"),
        ("Noted.😊 Which one?", "Noted."),
        ("Is this your site https://x.com?", "Is this your site https://x.com."),
        ("Noted. Is it e.g. a van?", "Noted. Is it e.g. a van."),
    ],
)
def test_statement_only_splits_only_at_real_sentence_ends(text, left):
    kept = part19.statement_only(text)
    assert kept.replace("*", "").startswith(left)  # every sentence stays; only the mark changes
    assert part19.question_count(part19.normalise_question_marks(part19.protect_urls(kept)[0])) == 0


def test_a_url_ending_the_question_is_still_a_question_and_the_link_is_intact():
    from app.modules.pi import constitution

    text = "Is this your site https://x.com? Or this one https://y.com/a?b=1?"
    final = constitution.final_one_question(text)
    assert "https://y.com/a?b=1" in final
    flat = part19.normalise_question_marks(part19.protect_urls(final)[0])
    assert part19.question_count(flat) == 1


@pytest.mark.parametrize(
    "said",
    [
        "kitna lagega mahinay",
        "kitna lagega mahinon",
        "kitna lagega dinon",
        "kitna lagega 2 din",
        "kitna lagega 3 hafte",
        "kitna lagega haftoon",
        "kitna lagega ghanton",
    ],
)
def test_more_duration_forms_are_not_a_price_ask(said):
    assert part19.buying_signal(said, 1) is None


# --- the protected sentences, in every language (owner's list for the fourth commit) ----------------
PROTECTED = {
    "disclosure": {
        "en": (
            "I am pi, an AI from Workzap, what does your business do?",
            "Shall I make the quote?",
        ),
        "roman_ur": (
            "Main pi hoon, Workzap ka AI, aap ka business kya karta hai?",
            "Kya main quote bana doon?",
        ),
        "ar": ("أنا pi، ذكاء اصطناعي من Workzap، ما هو عملك؟", "هل أجهز عرض السعر؟"),
    },
    "refusal": {
        "en": (
            "I never ask for a card number or a password, is that clear?",
            "What is your business?",
        ),
        "roman_ur": (
            "Main kabhi card number ya password nahi poochhta, theek hai?",
            "Aap ka business kya hai?",
        ),
        "ar": ("لا أطلب أبدًا رقم البطاقة أو كلمة المرور، هل هذا واضح؟", "ما هو عملك؟"),
    },
    "safety": {
        "en": (
            "Please call the emergency number 1122 and an ambulance now, is anyone hurt?",
            "Which city are you in?",
        ),
        "roman_ur": (
            "Foran 1122 par call karein aur ambulance bulayein, kya koi zakhmi hai?",
            "Aap kis shehar mein hain?",
        ),
        "ar": ("اتصل بالإسعاف على الرقم 1122 فورًا، هل هناك مصاب؟", "في أي مدينة أنت؟"),
    },
}


@pytest.mark.parametrize("language", ["en", "roman_ur", "ar"])
@pytest.mark.parametrize("kind", ["disclosure", "refusal", "safety"])
def test_a_protected_question_sentence_is_kept_when_a_later_question_follows(kind, language):
    from app.modules.pi import constitution

    protected, later = PROTECTED[kind][language]
    final = constitution.final_one_question(f"{protected} {later}")
    stem = protected[:-1]  # the sentence without its question mark
    assert f"{stem}." in final, final  # kept, as a statement
    assert final.rstrip().endswith(later), final  # the later question is the one question
    assert part19.question_count(part19.normalise_question_marks(final)) == 1, final


@pytest.mark.parametrize("language", ["en", "roman_ur", "ar"])
def test_a_disclosure_question_after_the_offer_text_is_not_lost_either(language):
    from app.modules.pi import constitution

    protected, later = PROTECTED["disclosure"][language]
    final = constitution.final_one_question(f"{protected}\n\n{later}\n\nAnd one more? Really?")
    assert f"{protected[:-1]}." in final
    assert part19.question_count(part19.normalise_question_marks(final)) <= 1


@pytest.mark.parametrize(
    "said,why",
    [
        ("show me the cost", "show"),
        ("kitna kharcha hoga, dikhao", "show"),
        ("send me the quote", "document_asked"),
        ("how much will it cost?", "done"),
    ],
)
def test_a_summary_never_replaces_a_price_answer_or_a_quote_ask(said, why):
    assert part19.summary_blocked({"brief": {}, "history": []}, said, why)


@pytest.mark.parametrize(
    "said,why",
    [("list down all the problems", "show"), ("show my problem map", "map")],
)
def test_a_genuine_list_ask_still_gets_the_summary(said, why):
    assert not part19.summary_blocked({"brief": {}, "history": []}, said, why)


def test_the_cost_line_goes_after_the_disclosure_and_never_carries_a_figure():
    from app.modules.pi import service_conversation as sc

    line = decisions.cost_answer("roman_ur")
    plain = sc.put_cost_line("I need one more fact. Since when?", line)
    assert plain.startswith(line)
    first = sc.put_cost_line(
        "Hi, it's pi, the AI from Workzap. I need one more fact. Since when?", line
    )
    assert first.startswith("Hi, it's pi, the AI from Workzap.") and line in first
    assert not any(ch.isdigit() for ch in line)


@pytest.mark.parametrize("code", ["en", "roman_ur", "ur", "ar", "fr", "es", "fa"])
def test_the_cost_line_follows_the_disclosure_in_every_language(code):
    from app.modules.pi import constitution
    from app.modules.pi import service_conversation as sc
    from app.modules.pi.fixed_lines import LINES

    opening, cost = LINES["opening"][code], LINES["cost"][code]
    reply = sc.put_cost_line(f"{opening} Which team does it hit hardest?", cost)
    assert reply.startswith(opening)  # R-DISC-01: the disclosure stays the first sentence
    assert reply[len(opening) :].lstrip().startswith(cost)
    assert not any(ch.isdigit() for ch in cost)
    final = constitution.final_one_question(reply)
    assert final.count("?") + final.count("؟") == 1


def test_a_fixed_decision_reply_drops_a_stale_cost_line():
    from app.modules.pi import service_conversation as sc

    turn = sc.ServiceTurn(reply="the model reply")
    turn._cost_line = "stale cost line"
    context = {
        "flow": {"state": "S3_NOTED"},
        "latest_customer_message": "mujhay quote do abhi",
        "latest_message_id": "m1",
        "reply_language": "roman_ur",
        "noted_problems": [{"ref": "a", "title": "t", "group": "g"}],
        "brief": {},
    }
    sc.brain_decision(turn, context)
    assert turn.reply != "the model reply"  # the gate replaced the reply
    assert turn._cost_line == ""


def test_a_first_sentence_that_only_asks_about_ai_does_not_get_the_cost_line_after_it():
    from app.modules.pi import service_conversation as sc

    line = decisions.cost_answer("en")
    reply = sc.put_cost_line("Does AI help with quotes? Which team does it hit hardest?", line)
    assert reply.startswith(line)
    assert reply.rstrip().endswith("hardest?")


# the REAL gate: decisions.decide with a problem noted and a listening state (audit round 4)
DECIDE_STATEMENTS = [
    "I need a quote system that tracks orders",
    "We need a quote template for every customer",
    "Quote banane mein bohat time lagta hai",
    "Hamein quote chahiye hota hai",
    "Our orders get lost, we need a quote system that tracks them",
    "My staff is slow. We need a quote template for every customer",
    "Customers wait for days, so I need a quote tool",
    "We want a document scanner for the shop",
    "We told you we need a quote system",
    "My customers say, send me the quote",
    "customers ask me to send the quote",
    "my team forgets to send the quote",
    "it takes me hours to send a quote",
    "customers ko quote chahiye hota hai, mujhe banane mein time lagta hai",
    "I send the quote to customers late",
    "Every morning I check the orders and make a quote",
    "Customer calls, I note the details, prepare the quote",
    "We take the order and send the quote",
    "If I like the idea, send me the quote",
    "Once I decide, send me the quote",
    "When I'm ready, send me the quote",
    "jab main kahoon, quote bhej do",
    "agar theek laga, quote bhej do",
    "Don't send me the quote now. I need a quote only when I say so",
    "send me the quote later",
    "give me the price",
    "how much will it cost?",
]
DECIDE_STATEMENTS += [
    # Arabic and Urdu script statements, conditionals and "later" (audit round 5)
    "أرسل عرض سعر إذا أعجبتني الفكرة",
    "أرسل عرض سعر لاحقا",
    "أرسل عرض سعر بعد الاجتماع",
    "نريد وثيقة لكل طلب",
    "أحتاج مستند يتتبع الطلبات",
    "مجھے کوٹیشن بنانے میں بہت وقت لگتا ہے",
    "کوٹیشن بھیجنے میں دیر ہوتی ہے",
    "دستاویز چاہیے ہوتی ہے",
    "کوٹیشن بھیج دیں اگر پسند آئے",
    # Roman Urdu infinitive fragments and statements
    "Quote banana",
    "Quote banane",
    "Quote bhejna",
    "Quote bhejna parta hai",
    "Hamein quote chahiye hota hai",
]
DECIDE_ASKS = [
    "can I get the quote",
    "أرسل عرض سعر",
    "أرسل عرض السعر من فضلك",
    "کوٹیشن بھیج دیں",
    "براہ کرم کوٹیشن بھیج دیں",
    "bhej do quote",
    "quote bana do",
    "mujhay quote chahiye",
    "send me the quote",
    "please send me the quote",
    "mujhay quote do abhi",
    "quote bhej dein",
    "quote bhej dein na",
    "I said give me the quote",
    "maine bata diya, ab quote do",
    "I sent you the details, send me the quote",
    "send me the quote, no rush",
    "can you send me the quote?",
]


def _decide(said, state=None):
    from app.modules.pi import part19

    return decisions.decide(
        state or decisions.State.S3_NOTED,
        said,
        "en",
        {
            "can_approve": True,
            "problem_count": 2,
            "problem_refs": ["a", "b"],
            "brief": {},
            "buying_signal": part19.gate_signal(said, 2),
            "message_id": "m1",
        },
    )


@pytest.mark.parametrize("state", list(decisions.DIRECT_FROM))
@pytest.mark.parametrize("said", DECIDE_STATEMENTS)
def test_decide_never_starts_the_quote_on_a_statement(said, state):
    decision = _decide(said, state)
    assert decision is None or "request_solution" not in decision.effects
    assert decision is None or decision.next_state != decisions.State.S6_PREPARING


@pytest.mark.parametrize("said", DECIDE_ASKS)
def test_decide_starts_the_quote_on_an_explicit_imperative_ask(said):
    decision = _decide(said)
    assert decision is not None and "request_solution" in decision.effects
    assert decision.next_state == decisions.State.S6_PREPARING


@pytest.mark.parametrize(
    "unit",
    ["please ", "haan ji ", "yes ok ", "من فضلك ", "براہ کرم ", "quote bhej do "],
)
def test_a_long_run_of_lead_in_words_is_not_quadratic(unit):
    import time

    for text in (unit * 1000, unit * 3000 + "x"):  # a 7 KB message
        start = time.perf_counter()
        assert decisions.asks_for_document(text) is False
        assert time.perf_counter() - start < 0.1
    short = unit * 70  # under the length cap: the regex itself must stay fast
    start = time.perf_counter()
    decisions.asks_for_document(short + "x")
    decisions.DIRECT_DOCUMENT.match(short + "x")
    assert time.perf_counter() - start < 0.1


def test_a_fixed_reply_clears_the_need_fact_flag_and_the_cost_line():
    from app.modules.pi import service_conversation as sc

    turn = sc.ServiceTurn(reply="x")
    turn.reply = ""  # emptied by an earlier step
    turn._need_fact = True
    turn._cost_line = "cost line"
    context = {
        "reply_language": "en",
        "noted_problems": [{"ref": "a", "title": "t", "group": "g"}],
        "brief": {},
        "history": [],
        "latest_customer_message": "hmm",
    }
    sc.brain_never_empty(turn, context)
    assert turn._need_fact is False and turn._cost_line == ""
