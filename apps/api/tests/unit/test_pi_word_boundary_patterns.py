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


OWNER_WORDS = "I run a car showroom in Okara and sales are slow"


@pytest.mark.parametrize(
    "idea",
    [
        "Make sure people who search for you online find your showroom",
        "People search for your shop on their phones, so check what they see",
        "Check what comes up when customers search online for a showroom",
        "When people searches nearby for cars, be the first they see",
        "Claim your google listing and add three photos",
        "Update your business listing with the new opening hours",
        "Reply to your online reviews every Friday",
        "Jab log search for you online karein, to listing update karein",
        "Log aap ki dukaan online search for your shop karte hain, to listing update karein",
    ],
)
def test_g2_flags_an_idea_that_assumes_an_online_presence(idea: str) -> None:
    assert idea_filter.invented_context(idea, OWNER_WORDS) == "G2"


@pytest.mark.parametrize(
    "idea",
    [
        "Look at the showroom the way a stranger does when they search for it nearby, "
        "so you see what puts them off.",
        "Ask each of your last two buyers how they first heard of the showroom",
        "Call the three customers who left and ask what stopped them",
        "Gahak se poochain ke unhon ne dukaan kaise dhoondi",
        "Tidy the counter and greet each visitor within a minute",
        "Write down every price you quoted this week and the answer you got",
    ],
)
def test_g2_leaves_look_at_and_ask_ideas_alone(idea: str) -> None:
    assert idea_filter.invented_context(idea, OWNER_WORDS) is None
