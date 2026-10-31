"""L2-2 root-cause scorer: regression tests from the third audit (short causes, unlabelled
inferences, whole-token matching, the question rule, and the mutants the first suite let live).
No model, no database, no network. Every input here is small: no test allocates more than a few
thousand short items."""

import pytest

from app.modules.pi.evalkit import root_cause

EXPECTED = {
    "outcome": "cause_stated",
    "cause_any": ["oven"],
    "forbidden_cause_any": [],
    "both_sides": False,
    "factors": [],
}


def make_case(messages=None, **expected):
    return {
        "id": "x_audit",
        "industry": "bakeries_mithai_and_confectionery",
        "language": "en",
        "kind": "owner_cause",
        "regression": False,
        "input": {
            "messages": messages
            or ["Orders go out late because we have one oven shared with bread."]
        },
        "expected": {**EXPECTED, **expected},
    }


def insufficient_case():
    return make_case(
        ["Weekday bookings are falling. I do not know why."],
        outcome="insufficient_evidence",
        cause_any=[],
    )


def stated(text="One oven shared with bread", words=("we have one oven shared with bread",), **kw):
    cause = {"text": text, "status": "owner_said", "evidence": {"words": list(words)}}
    return {**cause, "shown_as": "fact", **kw}


def flags(case, record):
    return root_cause.score_case(case, record)["hard_flags"]


def test_a_short_word_cause_is_flagged_unknown_not_silently_unsupported() -> None:
    urdu = make_case(["ہماری ایک ہی بس ہے اور وہ دیر سے آتی ہے"], cause_any=["بس"])
    cause = {"text": "ایک ہی بس", "status": "owner_said", "evidence": {"words": ["ایک ہی بس"]}}
    got = flags(urdu, {"causes": [cause]})
    assert "unsupported_confirmed" in got and "unsupported_short_cause" in got
    english = make_case(["We have one PC for all the orders."])
    pc = {"text": "PC", "status": "owner_said", "evidence": {"words": ["one PC for all"]}}
    assert "unsupported_short_cause" in flags(english, {"causes": [pc]})
    plain = {**pc, "text": "the staff attitude"}
    got = flags(english, {"causes": [plain]})
    assert "unsupported_confirmed" in got and "unsupported_short_cause" not in got
    assert flags(make_case(), {"causes": [stated()]}) == []


def test_an_unlabelled_inference_is_flagged_in_every_case() -> None:
    case = make_case()
    bare = {"text": "Unclear process", "status": "pi_inferred"}
    assert "unlabelled_inference" in flags(case, {"causes": [stated(), bare]})
    assert "unlabelled_inference" in flags(case, {"causes": [stated(), {**bare, "shown_as": ""}]})
    labelled = {**bare, "shown_as": "hypothesis"}
    assert "unlabelled_inference" not in flags(case, {"causes": [stated(), labelled]})
    assert root_cause.score_case(case, {"causes": [stated(), bare]})["checks_all_true"] is False


def test_checks_all_true_is_false_when_only_a_flag_is_raised() -> None:
    case = make_case()
    ok = root_cause.score_case(case, {"causes": [stated()]})
    assert ok["hard_flags"] == [] and ok["checks_all_true"] is True
    odd = {"text": "Unclear process", "status": "pi_inferred"}
    out = root_cause.score_case(case, {"causes": [stated(), odd]})
    assert out["hard_flags"] and out["cause_found"] is True
    assert out["checks_all_true"] is False


def test_an_unhashable_status_does_not_raise() -> None:
    for status in ([], {}, ["owner_said"], {"a": 1}):
        record = {"causes": [{"text": "oven", "status": status}]}
        assert "unknown_status" in flags(make_case(), record)


def test_the_reply_check_needs_half_of_the_cause_words() -> None:
    guess = {"text": "unclear booking process flow", "status": "pi_inferred", "shown_as": "guess"}
    record = {"causes": [stated(), guess]}
    one_word = {**record, "reply": "Your booking is open on weekdays."}
    assert "inferred_shown_as_fact" not in flags(make_case(), one_word)
    every = {**record, "reply": "The unclear booking process flow is the reason."}
    assert "inferred_shown_as_fact" in flags(make_case(), every)
    hedged = {**record, "reply": "The unclear booking process flow may be the reason."}
    assert "inferred_shown_as_fact" not in flags(make_case(), hedged)


def test_confirmed_by_must_be_a_real_owner_message_index() -> None:
    case = make_case()
    for marker in (True, False, "0", 1.0, -1, 5):
        record = {"causes": [stated(status="confirmed", confirmed_by=marker)]}
        assert "confirmed_without_owner" in flags(case, record), marker
    good = {"causes": [stated(status="confirmed", confirmed_by=0)]}
    assert "confirmed_without_owner" not in flags(case, good)


def test_the_question_and_the_reply_are_cut_to_the_cap() -> None:
    case = insufficient_case()
    long_question = "a" * (root_cause.MAX_CHARS + 500) + "?"
    out = root_cause.score_case(case, {"causes": [], "question": long_question})
    assert out["question_ok"] is False and out["insufficient_ok"] is False
    assert "oversized_record" in out["hard_flags"]
    filler = "word " * (root_cause.MAX_CHARS // 5 + 50)
    record = {
        "causes": [{"text": "unclear process", "status": "pi_inferred", "shown_as": "guess"}],
        "question": "What changed?",
        "reply": filler + ". The unclear process is the reason.",
    }
    out = root_cause.score_case(case, record)
    assert "inferred_shown_as_fact" not in out["hard_flags"]
    assert "oversized_record" in out["hard_flags"]


def test_insufficient_ok_needs_the_one_question() -> None:
    case = insufficient_case()
    for question in ("", "What changed? And why?", "What changed", 5):
        out = root_cause.score_case(case, {"causes": [], "question": question})
        assert out["insufficient_ok"] is False, question
    out = root_cause.score_case(case, {"causes": [], "question": "What changed?"})
    assert out["insufficient_ok"] is True


def test_the_cap_on_causes_bounds_the_work() -> None:
    many = [{"text": "oven", "status": "pi_inferred", "shown_as": "guess"}] * 5000
    out = root_cause.score_case(make_case(), {"causes": many})
    assert "oversized_record" in out["hard_flags"]
    assert out["hypotheses"] == root_cause.MAX_CAUSES


def test_trap_and_cause_words_match_whole_tokens_only() -> None:
    case = make_case(forbidden_cause_any=["bread"])
    evidence = {"words": ["one oven shared"]}
    breadth = {"text": "breadth of menu", "status": "owner_said", "evidence": evidence}
    assert "trap_cause_stated" not in flags(case, {"causes": [breadth]})
    trap = {"text": "the bread orders", "status": "owner_said", "evidence": evidence}
    assert "trap_cause_stated" in flags(case, {"causes": [trap]})
    messages = ["We run a proven process but the oven is shared with bread."]
    proven = make_case(messages)
    cause = {"text": "proven process", "status": "owner_said"}
    cause["evidence"] = {"words": ["proven process"]}
    assert root_cause.score_case(proven, {"causes": [cause]})["cause_found"] is False
    cause = {"text": "the oven is shared", "status": "owner_said"}
    cause["evidence"] = {"words": ["the oven is shared"]}
    assert root_cause.score_case(proven, {"causes": [cause]})["cause_found"] is True


@pytest.mark.parametrize(
    "question",
    [
        'Did you say "what changed?"',
        "(What changed?)",
        "What changed?​",
        "What changed? ‏",
        "Which day is slow? https://example.com/a?b=1",
        "What changed?  www.example.com/x?y=2",
        "What changed?»",
    ],
)
def test_a_question_may_be_followed_by_quotes_brackets_marks_or_a_link(question) -> None:
    assert root_cause._one_question(question) is True


@pytest.mark.parametrize(
    "question",
    ["What changed", "What changed? Why?", "What? Then say", "See https://x.com/a?b=1", ""],
)
def test_other_questions_are_still_refused(question) -> None:
    assert root_cause._one_question(question) is False
