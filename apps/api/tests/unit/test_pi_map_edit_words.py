"""Platform spec v1.4, 4.5 and G47: what the owner says that edits the map, and what pi says back
(never "noted", never "Thanks.", one question and it is the last sentence)."""

from types import SimpleNamespace

import pytest

from app.modules.pi import map_edit


def problem(number, title, words=()):
    return SimpleNamespace(
        id=number, number=number, title=title, title_local="", user_words=list(words), tags=[]
    )


@pytest.mark.parametrize(
    ("said", "action"),
    [
        ("ye jorr galat hai", "unlink"),
        ("this link is wrong", "unlink"),
        ("please remove the link between P1 and P2", "unlink"),
        ("ye masla hal ho gaya", "resolve"),
        ("the stock problem is solved now", "resolve"),
        ("ye masla chhor do", "park"),
        ("park this problem for now", "park"),
        ("pehle ye", "rank"),
        ("start with P3", "rank"),
        ("ce lien est faux", "unlink"),
        ("ya está resuelto el problema", "resolve"),
    ],
)
def test_the_spec_phrases_are_edits(said, action):
    assert map_edit.wants(said) == action


@pytest.mark.parametrize(
    "said",
    [
        "kya ye masla hal ho gaya?",  # a question is not an edit
        "ye masla hal nahi hua",  # a negation
        "my website link is not working",
        "stock kam ho jata hai",
        "chhor do",  # leaving an open item, not a problem
        "",
    ],
)
def test_questions_negations_and_other_talk_are_not_edits(said):
    assert map_edit.wants(said) is None


def test_a_problem_is_found_by_number_or_by_the_owners_words():
    a = problem(1, "Best-sellers run out", ["best sellers khatam"])
    b = problem(2, "Cashiers are late", ["cashier late aate hain"])
    assert map_edit.named_in("P2 hal ho gaya", [a, b]) == [b]
    assert map_edit.named_in("the cashier one is solved", [a, b]) == [b]
    assert map_edit.named_in("ye masla hal ho gaya", [a, b]) == []  # nothing to point at
    c = problem(3, "Cashiers refunds slow", ["cashier refund"])
    assert [p.number for p in map_edit.named_in("cashier problem is solved", [b, c])] == [
        2,
        3,
    ]  # a tie: ask


@pytest.mark.parametrize("language", ["en", "roman_ur", "ar", "fr", "fa", "es", "ur", "hi"])
def test_every_reply_line_exists_and_follows_the_reply_rules(language):
    for action in ("unlink", "which_link", "which_problem", "resolve", "park", "rank"):
        text = map_edit.line(action, language, a="Stock", b="Cash")
        assert text and "{" not in text
        lowered = text.lower()
        assert "noted" not in lowered and not text.startswith("Thanks")
        questions = text.count("?") + text.count("؟")
        assert questions == (1 if action in ("unlink", "which_link", "which_problem") else 0)
        if questions:  # one question, and it is the last sentence
            assert text.rstrip().endswith(("?", "؟"))
            assert text.count("?") + text.count("؟") == 1
