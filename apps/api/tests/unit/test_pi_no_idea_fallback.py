# ruff: noqa: E501
"""PS-flow: the no-idea fallback speaks Urdu script too and never asks what the record holds."""

import re

from app.modules.pi import service_conversation as sc

TABLES = (sc.NO_IDEA_LINES, sc.NO_MORE_IDEAS, sc.NO_IDEA_AGAIN, sc.NO_IDEA_THIRD)


def test_every_fallback_line_has_urdu_script_and_arabic():
    for table in TABLES:
        assert {"en", "roman_ur", "ur", "ar"} <= set(table)
        assert re.search(r"[\u0600-\u06ff]", table["ur"]) and not re.search(
            r"[A-Za-z]", table["ur"]
        )
        assert table["ur"].count("\u061f") + table["ur"].count("?") == 1


def test_a_record_that_holds_what_was_tried_gets_the_line_that_does_not_ask_it_again():
    again = sc.NO_IDEA_AGAIN["en"]
    assert "tried" not in again.lower()
    assert "tried" in sc.NO_IDEA_LINES["en"].lower()
