"""Vocabulary phrases pi may learn from customers (spec 8.5 job 4)."""

from app.modules.pi import learning_lexicon as lex
from app.modules.pi import learning_rules as rules


def test_short_plain_phrases_are_kept_and_the_rest_dropped():
    assert lex.phrase("Udhaar") == "udhaar"
    assert lex.phrase("khata book") == "khata book"
    assert lex.phrase("call me on 0300 1234567") is None
    assert lex.phrase("a b") is None
    assert lex.phrase("one two three four five") is None
    assert lex.phrase("mail a@b.com") is None


def test_the_lesson_names_the_category_in_plain_words():
    assert lex.lesson_text("udhaar", "cash_collections") == (
        'When someone says "udhaar", they usually mean a cash collections problem.'
    )


def test_five_businesses_and_ninety_percent_agreement_add_a_term():
    seen = [("udhaar", f"b{i}", "cash_collections") for i in range(5)]
    assert rules.lexicon_terms(seen) == {"udhaar": "cash_collections"}
    assert rules.lexicon_terms(seen[:4]) == {}
    split = seen + [("udhaar", f"x{i}", "people_staff") for i in range(5)]
    assert rules.lexicon_terms(split) == {}
