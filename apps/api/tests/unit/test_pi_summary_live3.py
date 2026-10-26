"""Live test 3 (B, D): the sorted summary of a Roman Urdu chat read in three scripts and listed one
problem three times; the board's caption repeated the summary's own opener."""

from types import SimpleNamespace

from app.modules.pi import brain_visuals, problems, taxonomy


def item(category: str, title: str, local: str = "") -> dict:
    return {"category": category, "title": title, "title_local": local, "score": 1}


def test_a_roman_urdu_summary_never_shows_urdu_script_titles_or_bilingual_headings() -> None:
    text = problems.summary_message(
        [
            item(
                "sales_revenue", "Price asked in DM, then silence", "انسٹاگرام پر پوچھے گئے سوالات"
            ),
            item("customers_retention", "Price-only chats stop", "Sirf price poochte hain"),
        ],
        "roman_ur",
    )
    assert not any("؀" <= ch <= "ۿ" for ch in text)
    assert "*Bikri* (1)" in text and "*Gahak* (1)" in text
    assert "/" not in text


def test_the_roman_urdu_category_names_are_roman_urdu_only() -> None:
    for category in taxonomy.CATEGORIES:
        assert "/" not in category.roman_ur, category.key


def test_the_board_caption_does_not_repeat_the_summary_opener() -> None:
    opener = problems.SUMMARY_TEXT["roman_ur"][0].lower()
    caption = brain_visuals.TEXT["roman_ur"]["caption"].lower()
    assert "note kiya" not in caption and "sort" not in caption
    assert caption not in opener


def test_one_symptom_filed_under_another_category_is_one_problem() -> None:
    old = SimpleNamespace(
        title="Price asked in Instagram DM, then silence",
        user_words=["DM mein price poochte hain", "phir reply nahi aata"],
    )
    assert problems.facet_overlap(
        old, "Price-only chats on Instagram stop", ["sirf price poochte hain"]
    )  # type: ignore[arg-type]
    assert not problems.facet_overlap(old, "Staff arrive late", ["staff late aate hain"])  # type: ignore[arg-type]
