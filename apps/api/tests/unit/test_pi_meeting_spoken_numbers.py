"""A phone or card number that the speech service writes as words or as single spaced digits is
removed from a meeting line, in English, Roman Urdu, Urdu and Hindi, and ordinary speech about small
numbers is left alone."""

import pytest

from app.modules.pi.memory_ledger import redacted
from app.modules.pi_meetings.recording_routes import join_spoken_digits

REMOVED = "[contact detail removed]"


def stored(line: str) -> str:
    return redacted(join_spoken_digits(line), 400)


@pytest.mark.parametrize(
    ("line", "leaked"),
    [
        ("my number is 0 3 0 0 1 2 3 4 5 6 7 thanks", "5 6 7"),
        ("my number is zero three zero zero one two three four five six seven thanks", "seven"),
        ("mera number zero teen sau, ek do teen char paanch chhe saat hai.", "saat"),
        ("mera number sifar teen sau ek do teen char panch che saat hai", "saat"),
        ("میرا نمبر صفر تین صفر صفر ایک دو تین چار پانچ چھ سات ہے", "سات"),
        ("मेरा नंबर शून्य तीन शून्य शून्य एक दो तीन चार पाँच छह सात है", "सात"),
        ("my number is 0300, 1 2 3 4 5 6 7", "0300"),
    ],
)
def test_a_number_spoken_as_words_or_single_digits_is_removed(line: str, leaked: str) -> None:
    out = stored(line)
    assert out.count(REMOVED) == 1
    assert leaked not in out


@pytest.mark.parametrize(
    "line",
    [
        "Mera number 0300 1234567 hai.",
        "میرا نمبر ۰۳۰۰۱۲۳۴۵۶۷ ہے",
        "my number is 03001234567",
    ],
)
def test_digits_written_as_digits_are_still_removed(line: str) -> None:
    assert REMOVED in stored(line)


@pytest.mark.parametrize(
    "line",
    [
        "We have three or four orders and two customers waiting.",
        "Delivery takes 3 5 days, sometimes 7.",
        "mujhe ek system chahiye, do teen din mein, char log kaam karte hain.",
        "ہمارے پاس ایک دو تین آرڈر ہیں",
        "Order 1 2 3 are late.",
    ],
)
def test_ordinary_talk_about_small_numbers_is_left_alone(line: str) -> None:
    assert stored(line) == line


def test_text_around_the_number_is_kept() -> None:
    out = stored("call me on zero three zero zero one two three four five six seven after lunch")
    assert out == f"call me on {REMOVED} after lunch"
