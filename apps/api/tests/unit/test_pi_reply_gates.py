"""Spec v1.5, Part 18: openingGate (OG), noEmptyOpener (EO), alreadyAnswered (AA), offer text."""

from app.modules.pi import reply_gates as g

NEW = {"history": [], "brief": {}}
OLD = {"history": [{"role": "ai", "text": "Hi"}], "brief": {}}


def test_og1_hello_gets_ai_line_and_identity_question_without_problem_question() -> None:
    ok = (
        "Hi, I'm pi, an AI from Workzap. "
        "What is your business called and what does it make or sell?"
    )
    assert g.opening_problem(ok, NEW) is None
    bad = "Hi, I'm pi, an AI from Workzap. What's going wrong in your business?"
    assert g.opening_problem(bad, NEW)


def test_og2_old_greeting_is_blocked_in_every_language() -> None:
    for line in (
        "Tell me what's going wrong in your business and I'll start on it.",
        "Aap ke business mein kya masla chal raha hai?",
        "آپ کے کاروبار میں کیا مسئلہ ہے؟",
    ):
        assert g.forbidden_opening(line)
    assert g.forbidden_opening("What does your business do?") is None


def test_og_missing_ai_line_or_identity_question_is_blocked() -> None:
    assert "AI" in (g.opening_problem("Hello! What does your business do?", NEW) or "")
    assert g.opening_problem("Hi, I'm pi, an AI from Workzap. Welcome.", NEW)


def test_og_gate_passes_when_the_business_is_already_said_or_the_chat_is_old() -> None:
    reply = "Hi, I'm pi, an AI from Workzap. Which of those costs you most?"
    assert g.opening_problem(reply, NEW, business_known=True) is None
    assert g.opening_problem("Which costs most?", OLD) is None


def test_og4_force_opening_makes_an_old_number_a_new_one() -> None:
    assert g.opening_problem("Which costs most?", {**OLD, "force_opening": True})


def test_og_a_number_with_a_confirmed_business_is_returning() -> None:
    ctx = {"history": [], "brief": {"business_profile": {"business_name": "Dalal & Co"}}}
    assert g.opening_problem("Which costs most?", ctx) is None


def test_eo1_empty_openers_are_caught_and_content_openers_pass() -> None:
    for bad in (
        "Understood. Is it about people?",
        "Internal issues, understood. Is it more about work?",
        "That covers a lot of ground. What went wrong?",
        "Here are some ideas for you: count stock.",
        "Noted — what next?",
    ):
        assert g.empty_opener(bad), bad
    assert g.empty_opener("Ten crore on paper is the heart of it. Which hurts most?") is None
    assert g.empty_opener("Understanding stock takes a count.") is None


def test_aa2_closed_list_of_areas_before_the_business_is_known() -> None:
    q = "Where do you notice it most: sales, stock, staff or cash?"
    assert g.closed_list_early(q, ["I run a business"], business_known=False)
    assert g.closed_list_early(q, ["I run a business"], business_known=True) is None
    assert g.closed_list_early(q, ["sales, stock, staff, cash are the issue"], False) is None


def test_of_say_no_is_removed_from_an_offer() -> None:
    out = g.without_say_no("Shall I get a quote made for these? You can say no.")
    assert out == "Shall I get a quote made for these?"
    assert g.without_say_no("Shall I get a quote?") == "Shall I get a quote?"


def test_og4_the_environment_flag_forces_the_opening(monkeypatch) -> None:
    monkeypatch.setenv("FORCE_OPENING", "true")
    assert g.is_first_reply({**OLD, "noted_problems": []})
    monkeypatch.setenv("FORCE_OPENING", "false")
    assert not g.is_first_reply(OLD)


def test_of4_i_already_told_you_blocks_the_offer_for_eight_messages() -> None:
    from app.modules.pi import box_signals as b

    told = {"history": [{"role": "customer", "text": "This I already told you the problems"}]}
    assert b.repeat_complaint_recent({**told, "latest_customer_message": "ok"})
    assert b.trust_and_upset({**told, "latest_customer_message": "ok"})[0] == "falling"
    old = [{"role": "customer", "text": "maine batayaa tha"}] + [{"role": "ai", "text": "x"}] * 8
    assert not b.repeat_complaint_recent({"history": old, "latest_customer_message": "ok"})


def test_il1_g12_drops_an_idea_when_no_problem_is_known() -> None:
    from app.modules.pi import idea_filter as f

    idea = "Count one shelf of stock against what the sales record shows."
    assert "G12" in f.failures(idea, "I run a business", f.IdeaContext(needs_problem=True))
    ctx = f.IdeaContext(needs_problem=True, nodes=("stock about 10 crore on paper",))
    assert "G12" not in f.failures(idea, "stock about 10 crore on paper", ctx)
