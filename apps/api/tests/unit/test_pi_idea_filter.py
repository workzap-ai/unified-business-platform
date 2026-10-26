"""Idea filter G1 (goal) and G2 (grounded), platform spec Book 5, 7.1, from the second live chat."""

from app.modules.pi import idea_filter, solution_free

STOCK = "mera clothing brand hai 6 crore ka stock bechna hai"


def test_a_buffer_idea_fails_for_someone_who_wants_to_clear_stock() -> None:
    assert idea_filter.failures("Keep a buffer of the fast sellers back.", STOCK) == ["G1"]


def test_a_discount_idea_fails_for_someone_who_wants_to_know_their_stock() -> None:
    assert idea_filter.goal_conflict(
        "Run a clearance sale on old lines.", "stock ka hisaab nahi milta"
    )


def test_online_launches_fail_when_the_owner_never_said_online() -> None:
    assert idea_filter.invented_context("Plan online launches for the new designs.", STOCK) == "G2"


def test_the_same_idea_passes_when_the_owner_did_say_it() -> None:
    said = STOCK + ", website par bhi hai"
    assert idea_filter.invented_context("Show the old sets on your website first.", said) is None


def test_an_idea_that_fits_the_goal_passes() -> None:
    idea = "Count the stock by age and speed of sale, so the oldest part leaves first."
    assert idea_filter.failures(idea, STOCK) == []


def test_vetted_drops_an_idea_that_works_against_the_goal() -> None:
    kept = solution_free.vetted(
        [
            "Keep a buffer of the fast-selling sets back for the stock you want to sell.",
            "Offer the oldest sets first to customers who bought before, stock bechna hai.",
        ],
        STOCK,
        [],
        {"stock", "sets", "customers"},
    )
    assert all("buffer" not in k for k in kept)
