"""The same-turn rejection detector: a clear no to ONE offered idea, nothing when unclear."""

import pytest

from app.modules.pi import rejection_same_turn as rst

ONE = "Here is an idea:\n• Send every customer a reminder the day before.\nDoes that fit?"
TWO = (
    "Here are some ideas:\n• Send every customer a reminder the day before.\n"
    "• Keep a small stock list by the door.\nWhich helps more?"
)


@pytest.mark.parametrize(
    "said",
    [
        "no, not that",
        "dusra batao",
        "ye nahi ho sakta",
        "that won't work for us",
        "we can't do that",
        "یہ نہیں ہو سکتا",
        "هذا لا يناسبنا",
        "this is not for us",
    ],
)
def test_clear_rejection_of_the_single_idea(said):
    found = rst.detect(said, ONE)
    assert found is not None
    assert found.idea_text.startswith("Send every customer")
    assert found.owner_words == said


@pytest.mark.parametrize("said", ["ok", "hmm", "no", "maybe", "let me think", "haan", "nahi"])
def test_a_bare_word_is_not_a_rejection(said):
    assert rst.detect(said, ONE) is None


def test_no_idea_in_the_previous_reply_records_nothing():
    assert rst.detect("no, not that", "How many customers come in a day?") is None


def test_two_ideas_without_a_pointer_is_ambiguous():
    assert rst.detect("no, not that", TWO) is None
    assert rst.detect("dusra batao", TWO) is None


def test_two_ideas_with_a_pointer_picks_one():
    found = rst.detect("the second one won't work for us", TWO)
    assert found is not None and found.idea_text.startswith("Keep a small stock")
    found = rst.detect("number 1 won't work for us", TWO)
    assert found is not None and found.idea_text.startswith("Send every")


def test_a_take_back_is_not_a_rejection_and_is_recognised():
    assert rst.takes_back("actually yes, let's do that")
    assert rst.detect("actually yes, that won't work for us... no wait, let's do that", ONE) is None
    assert not rst.takes_back("no, not that")


def test_the_key_is_stable_per_wording():
    assert rst.key_of("Send a reminder.") == rst.key_of("send a reminder")
    assert rst.key_of("Send a reminder.").startswith("said:")
