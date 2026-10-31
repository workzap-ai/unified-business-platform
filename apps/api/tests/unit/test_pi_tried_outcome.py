"""L1 follow-up (live path): a failed earlier attempt is read from the owner's own words in five
languages and stored as tried[].outcome == "failed" with the owner's wording in `what`."""

import pytest

from app.modules.pi import tried_outcome as to
from app.modules.pi.problems import ProblemBook, ProblemNote

ROMAN = "rang wale folder try kiye lekin mix ho gaye"


def test_the_roman_urdu_failed_attempt_is_read_with_the_owners_wording():
    found = to.failed_attempt(ROMAN)
    assert found is not None
    assert found.what == "rang wale folder" and "mix ho gaye" in found.cue


@pytest.mark.parametrize(
    "text",
    [
        "we tried a discount before and it did not work",
        "rang wale folder pehle istemal kiye, kaam nahi aaya",
        "folder aazmaye, fayda nahi hua",
        "ghalat nikla",  # a weak cue alone is not enough...
        "ناکام رہا",
        "کوئی فائدہ نہیں",
        "لم ينجح",
        "لم يفد",
        "काम नहीं आया",
    ],
)
def test_failure_cues_in_five_languages(text):
    if text == "ghalat nikla":
        assert to.outcome_of(text) == "unclear"
        assert to.outcome_of("humne try kiya, ghalat nikla") == "failed"
    else:
        assert to.outcome_of(text) == "failed"


def test_weak_cues_need_an_attempt_word():
    assert to.failed_attempt("bekaar raha") is None
    assert to.failed_attempt("folder try kiye, bekaar raha") is not None


def test_a_plain_statement_is_unclear_and_a_good_result_is_worked():
    for text in ("kaam bohat hai", "the folders are on the shelf", ""):
        assert to.outcome_of(text) == "unclear"
    assert to.outcome_of("it worked well") == "worked"
    assert to.outcome_of("it did not work") == "failed"  # failure wins


def values(note, owner_text):
    got, _ = ProblemBook.requirement_values(note, None, "m1", owner_text)
    return got


def test_the_save_path_stores_what_and_failed_for_a_model_tried_item():
    note = ProblemNote(
        title="Files get mixed up", tried=[{"what": "rang wale folder", "outcome": ""}]
    )
    (entry,) = values(note, ROMAN)["tried"]
    assert entry["what"] == "rang wale folder" and entry["outcome"] == "failed"


def test_the_save_path_finds_the_failed_attempt_when_the_model_wrote_no_tried_item():
    note = ProblemNote(title="Customer files get mixed up", user_words=["files mix ho gaye"])
    (entry,) = values(note, ROMAN)["tried"]
    assert entry["what"] == "rang wale folder" and entry["outcome"] == "failed"


def test_an_unrelated_failed_attempt_is_not_attached_to_this_problem():
    note = ProblemNote(title="Sales are down", user_words=["bikri kam hai"])
    assert "tried" not in values(note, ROMAN)


def test_an_outcome_the_owner_gave_is_kept_and_a_model_only_text_proves_nothing():
    kept = ProblemNote(title="t", tried=[{"what": "ads", "outcome": "some leads"}])
    assert values(kept, "ads did not work")["tried"][0]["outcome"] == "some leads"
    guess = ProblemNote(title="t", tried=[{"what": "ads", "outcome": ""}])
    assert values(guess, "bikri kam hai")["tried"][0]["outcome"] == ""  # no owner words, no outcome


def test_a_successful_attempt_is_stored_as_worked_never_failed():
    note = ProblemNote(title="Files", tried=[{"what": "folders", "outcome": ""}])
    for text in ("folders try kiye aur bahut kaam aaya", "we used folders and it worked well"):
        (entry,) = values(note, text)["tried"]
        assert entry["outcome"] == "worked", text


def test_a_mixed_message_marks_each_attempt_correctly():
    note = ProblemNote(
        title="Files",
        tried=[
            {"what": "rang wale folder", "outcome": ""},
            {"what": "whatsapp reminders", "outcome": ""},
        ],
    )
    text = "rang wale folder try kiye lekin mix ho gaye. whatsapp reminders it worked well"
    got = {e["what"]: e["outcome"] for e in values(note, text)["tried"]}
    assert got == {"rang wale folder": "failed", "whatsapp reminders": "worked"}


def test_an_unrelated_tried_item_stays_unset():
    note = ProblemNote(title="Files", tried=[{"what": "ads", "outcome": ""}])
    assert values(note, ROMAN)["tried"][0]["outcome"] == ""


def test_a_repeat_check_skips_attempts_the_owner_said_worked():
    stored = [
        {"what": "rang wale folder", "outcome": "failed"},
        {"what": "whatsapp reminders", "outcome": "worked"},
        {"what": "ads", "outcome": ""},
        "plain",
    ]
    kept = to.not_worked(stored)
    assert [t["what"] if isinstance(t, dict) else t for t in kept] == [
        "rang wale folder",
        "ads",
        "plain",
    ]
    assert to.not_worked(None) == []
