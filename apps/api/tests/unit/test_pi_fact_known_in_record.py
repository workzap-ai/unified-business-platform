"""S5 (B6 root cause 5): a question about when it began or how often, asked while every noted
problem already holds that fact, is sent back. The record lives for the whole customer, so this
holds after the 20-message window and in a new chat, which the text-only check cannot do."""

import pytest

from app.modules.pi import reply_gates
from app.modules.pi.service_conversation import part18_problem


def problem(title="Cash does not match", missing=None):
    return {
        "ref": "p1",
        "title": title,
        "missing": ["where", "impact"] if missing is None else missing,
    }


KNOWN = problem(missing=["where", "impact"])  # since and how_often are known
UNKNOWN = problem(missing=["where", "how_often", "impact", "since"])


@pytest.mark.parametrize(
    "reply",
    [
        "Cash not matching is costly. Since when has this been happening?",
        "How long has this been going on?",
        "Ye kab se ho raha hai?",
        "How often does it happen?",
        "Ye kitni baar hota hai?",
    ],
)
def test_a_question_the_record_already_answers_is_blocked(reply: str) -> None:
    reason = reply_gates.known_in_record(reply, [KNOWN])
    assert reason and "already" in reason


def test_a_question_about_a_missing_fact_is_allowed() -> None:
    assert reply_gates.known_in_record("Since when has this been happening?", [UNKNOWN]) is None
    assert reply_gates.known_in_record("How often does it happen?", [UNKNOWN]) is None


def test_one_problem_still_missing_the_fact_keeps_the_question_open() -> None:
    both = [KNOWN, problem("Staff come late", missing=["since", "how_often"])]
    assert reply_gates.known_in_record("Since when has this been happening?", both) is None


def test_no_noted_problem_means_nothing_is_known() -> None:
    assert reply_gates.known_in_record("Since when has this been happening?", []) is None


def test_a_record_without_the_gaps_list_is_not_trusted() -> None:
    assert reply_gates.known_in_record("How often?", [{"ref": "p1", "title": "Cash"}]) is None


def test_other_questions_are_not_touched() -> None:
    assert reply_gates.known_in_record("Which shops is it in?", [KNOWN]) is None
    assert reply_gates.known_in_record("What does it cost you each day?", [KNOWN]) is None
    assert reply_gates.known_in_record("Cash not matching is costly.", [KNOWN]) is None


def _context(**extra: object) -> dict:
    return {
        "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
        "latest_customer_message": "ok",
        "noted_problems": [KNOWN],
        **extra,
    }


def test_the_live_check_works_only_when_the_workspace_turned_it_on() -> None:
    reply = "Cash not matching is costly. Since when has this been happening?"
    assert part18_problem(reply, _context()) is None  # off by default
    on = part18_problem(reply, _context(fact_ask=True))
    assert on and "already" in on
