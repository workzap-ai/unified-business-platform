"""One question per map message (spec v1.5 8): when the picture's caption already asks, no second
question is added; when another line asks (return, offer), the caption's question is dropped."""

from app.modules.pi import map_share

ASKING = (
    "Here is what I have so far: 3 problems, No links yet. Is this right? Tell me what to change."
)
PLAIN = "Version 2: 3 problems, 1 link."


def test_a_caption_that_asks_is_seen() -> None:
    assert map_share.caption_asks(ASKING)
    assert map_share.caption_asks("هل هذا صحيح؟")
    assert not map_share.caption_asks(PLAIN)


def test_the_question_is_cut_from_the_caption_when_another_line_asks() -> None:
    assert map_share.without_ask(ASKING) == "Here is what I have so far: 3 problems, No links yet."
    assert "?" not in map_share.without_ask(ASKING)


def test_a_caption_without_a_question_is_left_alone() -> None:
    assert map_share.without_ask(PLAIN) == PLAIN


def test_a_caption_that_is_only_a_question_is_kept_whole() -> None:
    assert map_share.without_ask("Is this right?") == "Is this right?"
