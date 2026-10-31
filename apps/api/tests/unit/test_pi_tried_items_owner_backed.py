"""L1 audit A: a tried entry and its outcome are stored only if the owner's own words back them."""

import pytest

from app.modules.pi.problems import ProblemBook, ProblemNote


def stored(tried, owner_text, **note):
    got, _ = ProblemBook.requirement_values(
        ProblemNote(title="Sales fell", tried=tried, **note), None, "m1", owner_text
    )
    return got.get("tried") or []


def one(what, outcome, text):
    return stored([{"what": what, "outcome": outcome}], text)


def test_no_owner_text_means_the_older_behaviour_entries_as_given():
    got, _ = ProblemBook.requirement_values(
        ProblemNote(title="t", tried=[{"what": "ads", "outcome": "x"}]), None, "m", None
    )
    assert got["tried"][0]["outcome"] == "x"


@pytest.mark.parametrize(
    "what,text",
    [
        ("facebook ads", "bikri kam hai"),
        ("facebook ads", "we sell shoes and sales fell"),
        ("اشتہار", "ہماری سیل کم ہے"),
        ("الاعلانات", "المبيعات قلت"),
        ("विज्ञापन", "बिक्री कम है"),
    ],
)
def test_an_attempt_the_owner_never_mentioned_is_not_stored(what, text):
    assert one(what, "", text) == []


@pytest.mark.parametrize(
    "outcome,text",
    [
        ("worked", "we tried facebook ads"),
        ("failed", "we tried facebook ads"),
        ("brought a flood of leads", "we tried facebook ads"),
    ],
)
def test_a_model_outcome_with_no_owner_words_behind_it_is_unset(outcome, text):
    (entry,) = one("facebook ads", outcome, text)
    assert entry["what"] == "facebook ads" and entry["outcome"] == ""


@pytest.mark.parametrize(
    "what,text,expected",
    [
        ("facebook ads", "we tried facebook ads and it did not work", "failed"),
        ("facebook ads", "we tried facebook ads and it worked well", "worked"),
        ("rang wale folder", "rang wale folder try kiye lekin mix ho gaye", "failed"),
        ("rang wale folder", "rang wale folder try kiye aur bahut kaam aaya", "worked"),
        ("اشتہار", "ہم نے اشتہار آزمائے لیکن ناکام رہا", "failed"),
        ("الاعلانات", "جربت الاعلانات وفشل", "failed"),
        ("विज्ञापन", "मैंने विज्ञापन आजमाए लेकिन काम नहीं आया", "failed"),
    ],
)
def test_the_owners_clause_sets_the_outcome(what, text, expected):
    (entry,) = one(what, "", text)
    assert entry["outcome"] == expected


@pytest.mark.parametrize(
    "text",
    [
        "my competitor tried facebook ads and it failed",
        "if I tried facebook ads it would not work",
        "do you think facebook ads failed for others?",
        "agar main facebook ads try karun to kaam nahi aayega",
        "padosi ne facebook ads aazmaye, fayda nahi hua",
    ],
)
def test_a_third_party_or_hypothetical_attempt_is_not_the_owners(text):
    assert one("facebook ads", "failed", text) == []


def test_the_derived_failed_attempt_ignores_third_parties_and_hypotheticals():
    note = dict(title="Customer files get mixed up", user_words=["files mix ho gaye"])
    got, _ = ProblemBook.requirement_values(
        ProblemNote(**note), None, "m", "rang wale folder try kiye lekin mix ho gaye"
    )
    assert got["tried"][0]["what"] == "rang wale folder"
    for text in (
        "padosi ne rang wale folder try kiye lekin mix ho gaye",
        "agar main rang wale folder try karun to mix ho jayenge",
    ):
        got, _ = ProblemBook.requirement_values(ProblemNote(**note), None, "m", text)
        assert "tried" not in got, text


def test_a_mixed_message_marks_each_attempt_by_its_own_clause():
    text = "facebook ads try kiye lekin kaam nahi aaya. we tried flyers and it worked well"
    got = {
        e["what"]: e["outcome"]
        for e in stored([{"what": "facebook ads"}, {"what": "flyers"}], text)
    }
    assert got == {"facebook ads": "failed", "flyers": "worked"}
