"""List numbering in a pi reply is not a price: it becomes WhatsApp bullets and the reply
goes out. Real amounts are still refused in quote mode, and the retry is told exactly
which part to rewrite."""

import pytest

from app.modules.pi.guard import ReplyRejected
from app.modules.pi.service_conversation import (
    digit_fragments,
    tidy_list_numbers,
    validate_service_reply,
)


def test_numbered_lists_become_bullets_and_pass_in_quote_mode():
    draft = "Aap ke liye ideas:\n1. Modern logo\n2) Website design\nKaunsa pasand hai?"
    tidy = tidy_list_numbers(draft)
    assert tidy == "Aap ke liye ideas:\n• Modern logo\n• Website design\nKaunsa pasand hai?"
    assert validate_service_reply(tidy, 4000, "quote") == tidy
    assert tidy_list_numbers("Options: 1) Logo 2) Website") == "Options: • Logo • Website"


def test_text_without_list_numbers_is_unchanged():
    assert tidy_list_numbers("Version 2.0 is ready") == "Version 2.0 is ready"
    assert tidy_list_numbers("No numbers here") == "No numbers here"


@pytest.mark.parametrize(
    "reply",
    ["Price Rs 5000 hai", "Total 5000 rupay", "$50 per page", "3 concepts in 5 days"],
)
def test_amounts_and_other_digits_are_still_refused_in_quote_mode(reply):
    with pytest.raises(ReplyRejected):
        validate_service_reply(tidy_list_numbers(reply), 4000, "quote")


def test_the_retry_is_shown_exactly_what_to_rewrite():
    pieces = digit_fragments("Pehle 3 concepts, phir Rs 5000 total", limit=3)
    assert pieces and all(any(ch.isdigit() for ch in p) for p in pieces)
    assert digit_fragments("Slot: Mon 10:00", allowed=["Mon 10:00"]) == []
