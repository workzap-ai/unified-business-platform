"""The problem taxonomy, the model's problem ops and the sorted summary (pi Brain spec Part 4)."""

from decimal import Decimal

import pytest

from app.modules.pi import flow, industry_packs, problems, taxonomy
from app.modules.pi.flow import State as S
from app.modules.pi.problems import ProblemNote, ProblemOp
from app.modules.pi.service_conversation import (
    BRAIN_DECISIONS,
    BRAIN_PROBLEMS,
    BRAIN_VOICE,
    ServiceTurn,
    system_for,
)


def test_the_taxonomy_has_the_spec_nineteen_categories():
    assert len(taxonomy.CATEGORIES) == 19
    assert taxonomy.CATEGORIES[0].key == "stock_inventory"
    assert taxonomy.CATEGORIES[-1].key == taxonomy.OTHER
    assert len(taxonomy.KEYS) == 19
    for category in taxonomy.CATEGORIES:
        assert category.en and category.roman_ur and category.ur and category.ar
        assert len(set(category.subtypes)) == len(category.subtypes)
        assert all(s == s.lower() and " " not in s for s in category.subtypes)
    assert taxonomy.BY_KEY["stock_inventory"].subtypes[0] == "stockout"
    assert taxonomy.BY_KEY["other"].subtypes == ()


def test_every_industry_pack_problem_uses_a_master_category():
    used = {
        item["category"]
        for pack in industry_packs.load_packs().values()
        for item in pack["problems"]
    }
    assert used <= taxonomy.KEYS


def test_labels_follow_the_language_and_unknown_keys_fall_back():
    assert taxonomy.label("stock_inventory") == "Stock"
    assert taxonomy.label("stock_inventory", "roman_ur") == "Maal"
    assert taxonomy.label("cash_collections", "ar") == "النقد والتحصيل"
    assert taxonomy.label("nonsense", "en") == "Other"
    assert taxonomy.normalise_category("sales_revenue") == "sales_revenue"
    assert taxonomy.normalise_category("invented") == "other"
    assert taxonomy.normalise_category(None) == "other"
    assert taxonomy.is_master_subtype("stock_inventory", "stockout")
    assert not taxonomy.is_master_subtype("stock_inventory", "made_up")


def test_severity_follows_the_spec_formula():
    # daily (3) x lost sales (3) x all locations (3) x "high" (1.3) = 35.1
    top = taxonomy.severity_score(["lost_sales"], "daily", "all", "high")
    assert top == Decimal("35.1") and taxonomy.severity_band(top) == "critical"
    # everything unknown: 1.5 x 1.5 x 1.5 x 1 = 3.4
    unknown = taxonomy.severity_score([], "unknown", "unknown")
    assert unknown == Decimal("3.4") and taxonomy.severity_band(unknown) == "low"
    weekly = taxonomy.severity_score(["lost_time"], "weekly", "some")
    assert weekly == Decimal("10.0") and taxonomy.severity_band(weekly) == "medium"
    # the worst impact counts, not the sum
    assert taxonomy.severity_score(["stress", "lost_money"], "once", "one") == Decimal("4.5")
    assert taxonomy.severity_band(Decimal("20")) == "high"


@pytest.mark.parametrize(
    ("title", "fine"),
    [
        ("Best-sellers run out in two shops", True),
        ("Cash doesn't match till at Shop C", True),
        ("Stock problems in every single branch we have right now", False),  # over 8 words
        ("Manager is lazy about stock", False),
        ("Warehouse thief takes stock", False),
        ("We need an app for orders", False),
        ("", False),
    ],
)
def test_title_rules(title, fine):
    assert (problems.title_problem(title) is None) is fine


def test_clean_title_clips_and_trims():
    assert problems.clean_title("one two three four five six seven eight nine ten.") == (
        "one two three four five six seven eight"
    )
    assert problems.clean_title("  Stock runs out. ") == "Stock runs out"


def test_redaction_removes_cards_ids_accounts_emails_and_phones():
    text = (
        "card 4111 1111 1111 1111, mail ali@example.com, call +92 300 1234567, "
        "CNIC 35202-1234567-1, PK36SCBL0000001123456702"
    )
    cleaned, changed = problems.redact(text)
    assert changed
    for secret in ("4111", "ali@example.com", "1234567", "35202", "SCBL"):
        assert secret not in cleaned
    assert "[card number removed]" in cleaned and "[email removed]" in cleaned
    plain, untouched = problems.redact("Stock runs out in two of four shops, about 40 items.")
    assert plain.startswith("Stock runs out") and not untouched


def test_scope_class():
    assert problems.scope_class(["Shop B", "Shop D"], "2 of 4 shops") == "some"
    assert problems.scope_class([], "3 of 4 shops") == "most"
    assert problems.scope_class([], "4 of 4") == "all"
    assert problems.scope_class(["Gulberg"], "") == "one"
    assert problems.scope_class(["a", "b"], "") == "some"
    assert problems.scope_class([], "") == "unknown"
    assert problems.scope_class([], "har shop mein") == "all"


def note(**changes):
    base = {
        "title": "Best-sellers run out in two shops",
        "user_words": ["We keep running out of our best-selling items."],
        "category": "stock_inventory",
        "confidence": 0.9,
    }
    return ProblemNote(**{**base, **changes})


def test_good_ops_pass_the_check():
    ops = [ProblemOp(op="create", note=note())]
    assert problems.check_ops(ops, set(), noted_in_reply=True) is None


def test_bad_ops_are_listed_for_a_rewrite():
    refs = {"abc12345"}
    bad_title = ProblemOp(op="create", note=note(title="Lazy manager never counts stock here"))
    assert "blames" in problems.check_ops([bad_title], refs, True)
    no_words = ProblemOp(op="create", note=note(user_words=[]))
    assert "user_words" in problems.check_ops([no_words], refs, True)
    no_category = ProblemOp(op="create", note=note(category=""))
    assert "no category" in problems.check_ops([no_category], refs, True)
    assert "unknown problem ref" in problems.check_ops(
        [ProblemOp(op="update", ref="zzz")], refs, True
    )
    assert "merge needs" in problems.check_ops([ProblemOp(op="merge", ref="abc12345")], refs, True)
    assert "two known refs" in problems.check_ops(
        [ProblemOp(op="link", ref="abc12345", to="x")], refs, True
    )
    one = ProblemOp(op="split", ref="abc12345", notes=[note()])
    assert "at least two" in problems.check_ops([one], refs, True)


def test_a_low_confidence_note_needs_a_confirming_question():
    shaky = ProblemOp(op="create", note=note(confidence=0.4))
    assert "ask one question" in problems.check_ops([shaky], set(), noted_in_reply=False)
    assert problems.check_ops([shaky], set(), noted_in_reply=True) is None


def test_ops_that_do_not_parse_are_dropped_not_fatal():
    raw = [
        {"op": "create", "note": {"title": "ok", "confidence": 0.5}},
        {"op": "explode"},
        "junk",
        7,
    ]
    assert len(problems.tolerate_ops(raw)) == 1
    assert problems.tolerate_ops(None) == [] and problems.tolerate_ops("x") == []
    turn = ServiceTurn.model_validate({"reply": "Noted.", "problem_ops": raw})
    assert [op.op for op in turn.problem_ops] == ["create"]
    assert ServiceTurn.model_validate({"reply": "Noted."}).problem_ops == []


def items(*pairs):
    return [{"category": c, "title": t, "score": s} for c, t, s in pairs]


def test_the_summary_groups_counts_and_ends_with_one_question():
    text = problems.summary_message(
        items(
            ("stock_inventory", "Best-sellers running out", 9),
            ("stock_inventory", "Transfers between shops go missing", 4),
            ("people_staff", "Cashiers late on weekends", 3),
            ("cash_collections", "Daily cash doesn't match the till", 3),
        )
    )
    lines = text.splitlines()
    assert lines[0] == "Here's what I've noted and sorted so far. None of it is solved yet."
    assert "*Stock* (2)" in lines and "*Staff* (1)" in lines and "*Cash & payments* (1)" in lines
    assert lines.index("*Stock* (2)") < lines.index("*Staff* (1)")  # biggest group first
    assert lines[lines.index("*Stock* (2)") + 1] == "• Best-sellers running out"  # worst first
    assert lines[-1] == "Is anything wrong or missing?"
    assert text.count("?") == 1


def test_a_long_summary_shows_two_lines_a_group():
    many = items(*[("stock_inventory", f"Stock problem number {i}", 10 - i) for i in range(8)])
    many += items(*[("people_staff", f"Staff problem number {i}", 10 - i) for i in range(6)])
    text = problems.summary_message(many)
    assert text.count("•") == 4
    assert "…and 10 more." in text
    assert text.count("?") == 1


def test_a_summary_line_is_ten_words_at_most():
    long = "one two three four five six seven eight nine ten eleven twelve"
    text = problems.summary_message(items(("other", long, 1)))
    assert "• one two three four five six seven eight nine ten\n" in text + "\n"


def test_the_summary_speaks_the_persons_language():
    roman = problems.summary_message(items(("stock_inventory", "Maal khatam", 1)), "roman_ur")
    assert "Ab tak jo maine note aur sort kiya hai" in roman and "*Maal* (1)" in roman
    assert roman.endswith("Kuch ghalat hai ya reh gaya hai?")
    assert "*اسٹاک* (1)" in problems.summary_message(items(("stock_inventory", "x", 1)), "ur")
    assert "*المخزون* (1)" in problems.summary_message(items(("stock_inventory", "x", 1)), "ar")


@pytest.mark.parametrize(
    ("said", "why"),
    [
        ("that's all", "done"),
        ("bas yahi", "done"),
        ("nothing else for now", "done"),
        ("aur kuch nahi", "done"),
        ("so what can you do?", "what_now"),
        ("how much would it cost", "what_now"),
        ("ab kya karna hai", "what_now"),
        ("Aap jaldi solution do na mujhe, sawal hi poochti rahogi kya?", "what_now"),
        ("Batao kuch kar sakte hain ya nahi kar sakte?", "what_now"),
        ("Kya solution hai tumhare paas?", "what_now"),
        ("just give me the solution", "what_now"),
        ("why so many questions", "what_now"),
        ("Can you tell me the solution", "what_now"),
        ("Upper btaiya tw hua Dekho chat", "show"),
        ("I already told you", "show"),
        ("pehle bata chuka hoon", "show"),
    ],
)
def test_when_the_summary_is_due(said, why):
    assert problems.summary_due(said, noted=2, since_summary=2) == why


def test_the_summary_waits_for_a_noted_problem_or_seven_new_ones():
    assert problems.summary_due("that's all", noted=0, since_summary=0) is None
    assert problems.summary_due("the cashier is late", noted=3, since_summary=3) is None
    assert problems.summary_due("the cashier is late", noted=7, since_summary=7) == "many"
    assert problems.summary_due("the cashier is late", noted=9, since_summary=2) is None


def test_the_trade_question_is_asked_once_after_two_problems():
    assert problems.shape_question_due(2, industry_known=False, already_asked=False)
    assert not problems.shape_question_due(1, False, False)
    assert not problems.shape_question_due(3, True, False)
    assert not problems.shape_question_due(3, False, True)


def test_the_listening_loop_notes_and_sorts():
    assert flow.after_turn(S.S1_LISTENING, asked_question=False, noted=True) == S.S3_NOTED
    assert flow.after_turn(S.S2_CLARIFYING, asked_question=True, noted=True) == S.S3_NOTED
    assert flow.after_turn(S.S0_NEW, asked_question=False, noted=True) == S.S3_NOTED
    assert flow.after_turn(S.S3_NOTED, asked_question=True, noted=True) == S.S3_NOTED
    assert flow.after_turn(S.S3_NOTED, asked_question=False, summary=True) == S.S4_SORTED_SUMMARY
    assert flow.after_turn(S.S1_LISTENING, asked_question=True, summary=True) == S.S4_SORTED_SUMMARY
    assert flow.after_turn(S.S4_SORTED_SUMMARY, asked_question=True) == S.S4_SORTED_SUMMARY
    # a new problem after the summary goes back to listening, then is noted
    assert flow.after_turn(S.S4_SORTED_SUMMARY, asked_question=False, noted=True) == S.S3_NOTED


def test_the_brain_prompt_lists_every_category_and_sub_type():
    assert system_for({}) != system_for({"pi_mode": "brain"})
    prompt = system_for({"pi_mode": "brain"})
    assert prompt.endswith(BRAIN_PROBLEMS + BRAIN_DECISIONS + BRAIN_VOICE)
    for category in taxonomy.CATEGORIES:
        assert f"{category.key}" in prompt
    assert "stock_inventory: stockout, overstock_dead_stock" in prompt
    assert "user_words" in prompt and "problem_ops" in prompt


@pytest.mark.parametrize(
    "said",
    ["Glt ma ny asa kch bh NH kha", "galat, wo nahi", "maine aisa nahi kaha", "I never said that"],
)
def test_saying_a_note_is_wrong_is_a_correction(said):
    assert problems.corrects_noted(said, noted=1)
    assert not problems.corrects_noted(said, noted=0)  # nothing noted: nothing to correct


def test_an_ordinary_answer_is_not_a_correction():
    assert not problems.corrects_noted("haan, roz hota hai", noted=2)
    assert not problems.corrects_noted("the cashier is wrong about the cash", noted=2)


@pytest.mark.parametrize(
    "said",
    [
        "customers ask too many questions on WhatsApp",
        "customer itne sawal karte hain",
        "customer sawal hi poochte rehte hain",
        "they never stop asking about delivery",
        "online order kar sakte hain ya nahi, pata nahi chalta",
        "koi hal hai nahi abhi tak",
        "suppliers never give me a fix date",
        "I already told the supplier twice",
        "staff check the chat late",
        "maine supplier ko pehle bata diya tha",
        "main staff ko bata chuka hoon",
        "Galat order deliver ho jata hai",
        "Ghalat bill banta hai",
        "Wrong items get packed every week",
        "I didn't mention it, but delivery is also slow",
    ],
)
def test_describing_a_problem_never_cuts_listening_short(said):
    assert problems.summary_due(said, noted=2, since_summary=2) is None
    assert not problems.says_wrong(said)


@pytest.mark.parametrize(
    "said", ["Upar bataya tha", "upar likha hai dekho", "Aap ko pehle bata chuka hoon"]
)
def test_upar_and_told_you_phrasings_show_the_summary(said):
    assert problems.summary_due(said, noted=2, since_summary=2) == "show"


def test_said_wrong_needs_no_note_but_withdrawing_does():
    assert problems.says_wrong("Glt ma ny asa kch bh NH kha")
    assert not problems.corrects_noted("Glt ma ny asa kch bh NH kha", noted=0)
