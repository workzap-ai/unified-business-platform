"""L1 audit K: phone numbers are redacted from stored requirement texts, in Pakistani forms too."""

import pytest

from app.modules.pi import problem_fields as pf

NUMBERS = [
    "0300-1234567",
    "03001234567",
    "+92 300 1234567",
    "+923001234567",
    "+92-300-1234567",
    "0092 300 1234567",
    "0300 123 4567",
    "0300-123-4567",
    "(0300) 1234567",
    "0321 1234567",
    "042-35761234",
]


@pytest.mark.parametrize("number", NUMBERS)
@pytest.mark.parametrize(
    "frame",
    [
        "{}",
        "call me on {}",
        "my number is {} for the budget",
        "bajet {} se baat karo",
        "رابطہ {} پر",
        "اتصل على {} لو سمحت",
    ],
)
def test_a_phone_number_is_never_stored(number, frame):
    text, changed = pf.clean(frame.format(number), 300)
    assert number not in text and "123" not in text.replace("[contact detail removed]", "")
    assert changed


@pytest.mark.parametrize(
    "text",
    [
        "budget 300000 rupees",
        "deadline 20240115",
        "we lose 3,000,000 rupees a year",
        "only 2 supervisors and 14 staff",
        "stock of 1234567 units",
        "کرایہ 45000 روپے",
    ],
)
def test_plain_figures_are_not_taken_for_phone_numbers(text):
    assert pf.clean(text, 300) == (text, False)
