"""Patterns that held a backspace instead of a word boundary and so never matched:
map_edit.STRONG_LINK and the online-listing asset group in idea_filter._ASSET_GROUPS."""

import pytest

from app.modules.pi import idea_filter, map_edit

LISTING_IDEA, LISTING_OWNER = next(
    group for group in idea_filter._ASSET_GROUPS if "listing" in group[0].pattern
)


@pytest.mark.parametrize(
    "text",
    [
        "this connection is wrong",
        "ye jorr galat hai",
        "ye jor theek nahi",
        "wrong arrow",
        "connection wrong hai",
        "rishta galat hai",
    ],
)
def test_strong_link_matches_a_link_word(text: str) -> None:
    assert map_edit.STRONG_LINK.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "the connections of the town",  # plural: not the word
        "disconnection fee",
        "narrower",
        "I sell tyres in Okara",
        "the price is wrong",
    ],
)
def test_strong_link_ignores_ordinary_text(text: str) -> None:
    assert not map_edit.STRONG_LINK.search(text)


def test_the_listing_group_is_the_one_under_test() -> None:
    assert "listing" in LISTING_IDEA.pattern and "google" in LISTING_OWNER.pattern


@pytest.mark.parametrize(
    "idea",
    [
        "Claim your google listing and add photos",
        "Check how you show up when someone searches nearby",
        "Update your business listing hours",
        "Look at your online reviews each week",
    ],
)
def test_listing_idea_pattern_matches(idea: str) -> None:
    assert LISTING_IDEA.search(idea)


@pytest.mark.parametrize(
    "idea",
    [
        "Ask customers what stopped them buying",
        "Call the three customers who left",
        "Tidy the counter before opening",
    ],
)
def test_listing_idea_pattern_ignores_normal_text(idea: str) -> None:
    assert not LISTING_IDEA.search(idea)


@pytest.mark.parametrize(
    "owner", ["people find me on google", "my website is old", "reviews are low"]
)
def test_owner_listing_pattern_matches(owner: str) -> None:
    assert LISTING_OWNER.search(owner)


@pytest.mark.parametrize(
    "owner", ["rapport with staff is poor", "mapping the stock is slow", "I sell tyres"]
)
def test_owner_listing_pattern_needs_whole_words(owner: str) -> None:
    assert not LISTING_OWNER.search(owner)


def test_an_idea_about_a_listing_is_flagged_when_the_owner_never_mentioned_one() -> None:
    assert (
        idea_filter.invented_context("Claim your google listing today", "my shop is quiet") == "G2"
    )


def test_the_same_idea_passes_when_the_owner_said_it() -> None:
    assert (
        idea_filter.invented_context("Claim your google listing today", "people find me on google")
        is None
    )
