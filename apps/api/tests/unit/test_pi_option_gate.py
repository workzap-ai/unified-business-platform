"""L2-1: the option gate sorts options by the owner's hard limits and never fills a quota."""

import inspect

from app.modules.pi import option_gate
from app.modules.pi.option_gate import NextStep, gate_options
from app.modules.pi.requirements_types import (
    Constraints,
    Limit,
    ProblemRequirements,
    Requirements,
)


def reqs(budget=None, cannot=()):
    return Requirements(
        problems=(
            ProblemRequirements(
                constraints=Constraints(
                    budget=Limit(budget) if budget else None,
                    cannot_change=tuple(Limit(c) for c in cannot),
                )
            ),
        )
    )


OPTIONS = [
    "Buy a tablet for each cashier for Rs 90000",
    "Use a paper register at the counter",
    "Replace the POS system with a cloud one",
    "Buy a tablet for each cashier",
]


def test_options_are_sorted_into_accepted_rejected_and_unknown_with_reasons():
    result = gate_options(
        OPTIONS, reqs(budget="Rs 20000", cannot=["we cannot change our POS system"]), "en"
    )
    assert result.accepted_options == ("Use a paper register at the counter",)
    assert [g.option for g in result.rejected] == [OPTIONS[0], OPTIONS[2]]
    assert {g.verdict.rule for g in result.rejected} == {"budget", "cannot_change"}
    assert all(g.verdict.reason and g.verdict.evidence for g in result.rejected)
    assert [g.option for g in result.unknown] == [OPTIONS[3]]
    assert result.next_step is NextStep.USE_ACCEPTED


def test_a_violation_is_rejected_whatever_the_relevance_and_the_gate_takes_no_score():
    assert "score" not in " ".join(inspect.signature(gate_options).parameters)
    perfect = "Replace the POS system with the one every shop like yours uses"
    result = gate_options([perfect], reqs(cannot=["POS system"]), "en")
    assert result.rejected and not result.accepted


def test_no_option_left_is_a_valid_typed_result_never_a_filled_quota():
    result = gate_options(
        ["Replace the POS system", "Switch the POS system to a cloud one"],
        reqs(cannot=["we cannot change our POS system"]),
        "en",
    )
    assert result.accepted == () and result.unknown == ()
    assert len(result.rejected) == 2
    assert result.next_step is NextStep.ASK_TARGETED_QUESTION and result.no_option_left
    assert result.ask_about == "cannot_change"
    assert isinstance(result.next_step, str) and "?" not in result.next_step


def test_an_empty_list_of_options_also_asks_one_question():
    result = gate_options([], reqs(budget="Rs 5000"), "en")
    assert result.no_option_left and result.ask_about is None


def test_only_unknown_left_is_not_accepted_and_not_a_question():
    result = gate_options(["Buy a tablet for each cashier"], reqs(budget="Rs 20000"), "en")
    assert result.accepted == () and len(result.unknown) == 1
    assert result.next_step is NextStep.CHECK_UNKNOWN


def test_no_limits_accepts_everything_and_unreadable_limits_accept_nothing():
    assert gate_options(OPTIONS, Requirements(), "en").accepted_options == tuple(OPTIONS)
    result = gate_options(OPTIONS, Requirements(columns_available=False), "en")
    assert result.accepted == () and len(result.unknown) == len(OPTIONS)


def test_the_gate_is_deterministic_and_keeps_the_order():
    one = gate_options(OPTIONS, reqs(budget="Rs 20000"), "en")
    two = gate_options(list(OPTIONS), reqs(budget="Rs 20000"), "en")
    assert one == two


def test_the_module_is_pure():
    source = inspect.getsource(option_gate)
    assert "evalkit" not in source and "sqlalchemy" not in source


def test_the_gate_never_raises_on_malformed_options_or_requirements():
    import random

    rng = random.Random(11)
    junk = [None, 0, 2.5, b"b", [], {}, object(), "", "​" * 20, "Rs " * 100, "a" * 2000]
    for _ in range(500):
        options = rng.choice(
            [
                None,
                5,
                "a string",
                junk,
                [rng.choice(junk) for _ in range(rng.randint(0, 6))],
                OPTIONS,
                iter(OPTIONS),
            ]
        )
        requirement = rng.choice(
            [None, "x", 3, Requirements(), reqs(budget="Rs 20000"), reqs(cannot=["POS system"])]
        )
        result = gate_options(options, requirement, rng.choice([None, "en", 5]))
        assert result.next_step in set(NextStep)


def test_a_single_string_is_one_option_not_a_list_of_letters():
    result = gate_options("Replace the POS system", reqs(cannot=["POS system"]), "en")
    assert len(result.rejected) == 1 and result.rejected[0].option == "Replace the POS system"


def test_a_malformed_option_is_unknown_with_a_reason_never_accepted():
    result = gate_options([None, 5, "Use a paper register"], reqs(budget="Rs 20000"), "en")
    assert [g.option for g in result.accepted] == ["Use a paper register"]
    assert len(result.unknown) == 2 and all(g.verdict.reason for g in result.unknown)
