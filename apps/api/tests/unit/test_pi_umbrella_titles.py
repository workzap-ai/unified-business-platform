"""Audit Run 2, R6 (Live Audit 6): one problem per owner line, in the owner's words. A title that
covers a whole message ("Internal business problems across several areas") is sent back."""

import pytest

from app.modules.pi import problems
from app.modules.pi.problems import ProblemNote, ProblemOp

FOUR_LINES = (
    "Sales: we currently use QB.\n"
    "Stock: have around 10 crore stock written on paper.\n"
    "Staff: no track of it who comes and goes at what time.\n"
    "Cash: cash in and out dont match"
)


def note(title: str, words: list[str] | None = None) -> ProblemNote:
    return ProblemNote(
        title=title, user_words=words or ["10 crore stock on paper"], category="stock_inventory",
        confidence=0.9,
    )  # fmt: skip


@pytest.mark.parametrize(
    "title",
    [
        "Internal business problems across several areas",
        "Various issues in the business",
        "General operational problems",
        "Multiple problems across all areas",
    ],
)
def test_a_catch_all_title_is_sent_back(title: str) -> None:
    issue = problems.check_ops([ProblemOp(op="create", note=note(title))], set(), False, FOUR_LINES)
    assert issue is not None and "umbrella" in issue


@pytest.mark.parametrize(
    "title",
    ["Stock of 10 crore kept on paper", "Sales records kept on QB", "Cash in and out do not match"],
)
def test_a_title_in_the_owners_words_goes_through(title: str) -> None:
    op = ProblemOp(op="create", note=note(title, ["cash in and out dont match"]))
    assert problems.check_ops([op], set(), False, FOUR_LINES) is None


def test_one_create_for_several_owner_lines_is_sent_back() -> None:
    words = [
        "Stock: have around 10 crore stock written on paper.",
        "Cash: cash in and out dont match",
    ]
    issue = problems.check_ops(
        [ProblemOp(op="create", note=note("Stock and cash records", words))],
        set(),
        False,
        FOUR_LINES,
    )
    assert issue is not None and "one create per line" in issue


def test_an_update_or_a_split_cannot_turn_a_problem_into_an_umbrella() -> None:
    umbrella = "Internal business problems across several areas"
    update = ProblemOp(op="update", ref="p1", note=note(umbrella))
    assert "umbrella" in (problems.check_ops([update], {"p1"}, False, FOUR_LINES) or "")
    split = ProblemOp(op="split", ref="p1", notes=[note(umbrella), note("Cash does not match")])
    assert "umbrella" in (problems.check_ops([split], {"p1"}, False, FOUR_LINES) or "")
