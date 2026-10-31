# ruff: noqa: E501
"""L2-1 regression found by PS-flow: a stated reason ("because of the contract") must not become part
of the limit, or the limit's objects grow and a plain violation reads as unknown."""

import pytest

from app.modules.pi import constraint_check as cc
from app.modules.pi.requirements_types import Constraints, Limit, ProblemRequirements, Requirements


def reqs(text):
    c = Constraints(cannot_change=(Limit(text),))
    return Requirements(problems=(ProblemRequirements(constraints=c),))


@pytest.mark.parametrize(
    "idea", ["Change the courier.", "Switch to a faster courier company for every order."]
)
def test_reason_clause_does_not_weaken_a_stated_limit(idea):
    limit = "we cannot change courier because of the contract"
    assert cc.check_option(idea, reqs(limit)).status == "violates"
    assert cc.check_option(idea, reqs("we cannot change courier")).status == "violates"


def test_limit_clauses_keep_the_limit_and_drop_the_bare_reason():
    assert cc.limit_clauses("we cannot change courier because of the contract") == [
        "we cannot change courier"
    ]


def test_idea_that_only_mentions_the_courier_is_not_rejected_by_a_promise_limit():
    idea = "Message each buyer when the parcel leaves with the courier tracking line."
    assert cc.check_option(idea, reqs("we cannot promise delivery days")).status != "violates"


def test_use_a_new_courier_breaks_we_cannot_change_courier():
    assert (
        cc.check_option(
            "Use a new courier.", reqs("we cannot change courier because of the contract")
        ).status
        == "violates"
    )
