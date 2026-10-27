"""Gaps closed in solutions that learn (Addendum 2, Parts 2 and 3): the parts with no database."""

import asyncio
from typing import Any

from app.modules.pi import (
    learning_gate,
    learning_solutions_grow,
    solution_context,
    solution_score,
    solution_versions,
    solutions,
    value_line,
)

PERSON = "Season sar pe hai aur sab kuch mere review pe atak jata hai. Koi solution batayein."


def test_not_tried_is_a_cue_worth_nothing_and_never_a_sales_signal():
    said = solution_score.classify("abhi nahi kiya, time nahi mila")
    assert said is not None and said.signal == "idea_not_tried" and said.score == 0
    assert solution_score.reaction_of_memory("idea_not_tried") == "none"
    # a clear "it worked" or "did not help" still beats it
    assert solution_score.classify("it worked, we had not tried before").signal == "idea_worked"
    assert solution_score.classify("I tried it and it did not help").signal == "idea_no_help"
    # offers, approvals and payments never score (SL8), whatever a caller passes
    for signal in ("offer_accepted", "quote_accepted", "paid", "document_sent", "quote_approved"):
        assert signal in solution_score.SALES_SIGNALS
        assert solution_score.score_of(["idea_will_try", signal]) == 3


def test_the_idea_budget_before_and_after_a_declined_offer():
    assert solution_context.allowance({}, 0) == value_line.IDEAS_BEFORE_OFFER
    assert solution_context.allowance({}, 4) == 4  # Book 5 decision 5: eight, two per problem
    assert solution_context.allowance({}, 8) == 0
    declined = {"declines": 1, "ideas_at_decline": 8}
    assert solution_context.allowance(declined, 8) == value_line.IDEAS_AFTER_DECLINE
    assert solution_context.allowance(declined, 10) == 0
    # the decline was seen before the budget was stamped: nothing taken yet
    assert solution_context.allowance({"declines": 1}, 3) == value_line.IDEAS_AFTER_DECLINE


def test_a_sample_reply_feeds_the_bank_without_its_offer_and_with_bullets():
    body = solution_versions.sample_body(
        "Yes. 1 Put every booking on one calendar this week. 2 Let one person confirm bookings. "
        "Shall I get a solution document and a quote made for you? You can say no."
    )
    assert "solution document" not in body and "say no" not in body
    assert body.startswith("Yes. • Put every booking") and "• Let one person" in body


def test_some_seed_samples_pass_the_bank_bar_and_a_bad_one_never_does():
    passing = [
        key
        for key in solutions.industries()
        if learning_solutions_grow.fit_for_bank(
            solutions.load(key)["sample_reply"]["person"], solutions.load(key)["sample_reply"]["pi"]
        )[0]
    ]
    assert passing  # the rest are refused by the linter or the redaction bar, as they should be
    ok, _ = learning_solutions_grow.fit_for_bank(
        "stock problem", "1 Count it. 2 Track it. 3 Tell staff. This will double your sales."
    )
    assert ok is False


def drafted(writer_says: dict[str, Any] | None) -> dict[str, Any]:
    async def draft(industry: str, words: str) -> dict[str, Any]:
        if writer_says is None:
            raise RuntimeError("model down")
        return writer_says

    async def write(*_: Any) -> list[str]:
        return []

    write.draft_entry = draft  # type: ignore[attr-defined]
    return asyncio.run(learning_solutions_grow.draft_entry_fields(write, "dairy", "milk drops"))


def test_a_drafted_entry_needs_catalogue_keys_a_clean_question_and_a_clean_stop():
    good = {
        "build_keys": ["stock_alerts"],
        "ask_first": "Which item runs out most often?",
        "free_stops": "Who gets told, and when, is in the solution document.",
    }
    got = drafted(good)
    assert got["workzap_build"]["keys"] == ["stock_alerts"]
    assert got["ask_first"].endswith("?") and got["free_stops"]
    assert drafted({**good, "build_keys": ["not_in_the_catalogue"]}) == {"invalid": True}
    assert drafted({**good, "build_keys": []}) == {"invalid": True}
    assert drafted({**good, "ask_first": "Tell me more."}) == {"invalid": True}
    assert drafted({**good, "ask_first": "Which dashboard do you use?"}) == {"invalid": True}
    assert drafted({**good, "free_stops": "Step 1, open the settings and click save."}) == {
        "invalid": True
    }
    assert drafted(None) == {"invalid": True}  # a failing model never breaks the run


def test_a_writer_without_the_entry_step_drafts_no_build_fields():
    async def write(*_: Any) -> list[str]:
        return []

    assert asyncio.run(learning_solutions_grow.draft_entry_fields(write, "x", "y")) == {}
    assert asyncio.run(learning_solutions_grow.draft_entry_fields(None, "x", "y")) == {}


def test_the_gate_result_carries_the_regression_replay():
    result = learning_gate.GateResult(True)
    assert result.as_dict()["regressions"] == {}
