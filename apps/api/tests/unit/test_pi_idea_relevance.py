"""Live test 3: a fashion owner's "price asked in DM, then only 'sirf raqam', then silence" was
given the exchange problem's ideas, because the noted category matched. An entry is served only when it
shares a real content word with what the person said."""

import pytest

from app.modules.pi import solution_ideas, solutions

SAID = "price asked in DM sirf raqam then silence mostly instagram orders kam"


@pytest.fixture(scope="module")
def problems() -> list[dict]:
    data = solutions.load("fashion_and_apparel_brands")
    assert data is not None
    return data["problems"]


@pytest.mark.parametrize(
    ("category", "subtype"),
    [("customers_retention", "after_sales"), ("sales_revenue", "conversion_low"), ("", "")],
)
def test_the_exchange_ideas_are_not_given_for_a_price_problem(
    problems: list[dict], category: str, subtype: str
) -> None:
    found = solution_ideas.match_problem(problems, category, subtype, SAID)
    assert found is None or found["id"] != "p7_after_sales"


def test_the_price_problem_finds_its_own_entry(problems: list[dict]) -> None:
    found = solution_ideas.match_problem(problems, "sales_revenue", "conversion_low", SAID)
    assert found is not None
    assert found["id"] == "x1_price_asked_then_silence"


def test_the_exchange_problem_still_matches_its_own_words(problems: list[dict]) -> None:
    said = "exchange requests in DMs get lost, nobody replies to the exchange requests"
    found = solution_ideas.match_problem(problems, "customers_retention", "after_sales", said)
    assert found is not None
    assert found["id"] == "p7_after_sales"


def test_a_short_phrase_is_not_held_to_the_gate(problems: list[dict]) -> None:
    assert solution_ideas.relevant(problems[0], "kam sale")
