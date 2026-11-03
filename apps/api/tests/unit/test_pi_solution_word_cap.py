"""Book 2 4.1: a solution answer may run to 120 words (150 with the line on what Workzap would
build); it is not a 60-word listening reply. A compliant 70-word reply used to cost a rewrite, and
'Solution batao' (a short message) used to be told to answer in one or two short sentences."""

from app.modules.pi import constitution
from app.modules.pi.service_conversation import too_long

IDEAS = (
    "Bilkul. Do kaam is hafte karein.\n"
    "First, " + " ".join(["compare each shop's sales with the same day last week"] * 2) + ".\n"
    "Second, " + " ".join(["note why browsing customers leave without buying"] * 2) + ".\n"
    "Workzap could send the manager a message the day a best-seller runs low.\n"
    "Shall I get a solution document and a quote made for you? You can say no."
)


def rules(reply: str, **context) -> list[str]:
    ctx = {
        "latest_customer_message": "Solution batao",
        "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
        "flow": {"state": "S3_NOTED"},
        **context,
    }
    return [v.rule for v in constitution.lint(reply, ctx)]


def test_a_solution_reply_of_about_eighty_words_is_not_too_long():
    assert 60 < len(IDEAS.split()) <= 120
    assert "R-VOICE-01" not in rules(IDEAS, solution_asked=True)
    assert "R-VOICE-01" in rules(IDEAS)  # the same reply to no request is still a listening reply


def test_the_cap_is_a_hundred_and_fifty_with_the_build_line_and_never_unlimited():
    long = " ".join(["word"] * 140) + "?"
    assert "R-VOICE-01" not in rules(long, solution_asked=True, solution_build={"says": "x"})
    assert "R-VOICE-01" in rules(long, solution_asked=True)  # 140 > 120 without the build line
    huge = " ".join(["word"] * 200) + "?"
    assert "R-VOICE-01" in rules(huge, solution_asked=True, solution_build={"says": "x"})


def test_a_short_solution_request_is_not_told_to_answer_in_one_short_sentence():
    ctx = {"latest_customer_message": "Solution batao", "latest_message_kind": "text"}
    reply = "x " * 200
    assert too_long(reply, ctx) is not None
    assert too_long(reply, {**ctx, "solution_asked": True}) is None
    assert too_long(reply, {**ctx, "solution_howto": {"covers": "x"}}) is None


def test_the_final_checks_are_the_never_break_rules_only():
    """A.3 step 6: they run on the final reply. They must not include the offer-timing rules, or
    the application's own document confirmation would be rejected in a listening state."""
    assert constitution.FINAL_CHECKS == {"R-PAY-02", "R-PAY-03", "R-DISC-03", "R-BRAND-01"}
    confirmation = (
        "Thanks. I've asked Workzap to prepare your solution document and quote. "
        "I'll send them here once they're ready."
    )
    ctx = {
        "latest_customer_message": "dain solution document mujhay",
        "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
        "flow": {"state": "S3_NOTED"},
    }
    found = {v.rule for v in constitution.lint(confirmation, ctx)}
    assert not (found & constitution.FINAL_CHECKS)
    bad = "Please send me your card number and the CVV to confirm. Hi, I'm a mum too."
    found = {v.rule for v in constitution.lint(bad, ctx)}
    assert {"R-PAY-02", "R-DISC-03"} <= found
