"""Level 1 privacy: phone numbers in every common shape are redacted from stored requirement texts,
and budgets, figures and dates are left alone."""

import pytest

from app.modules.pi import problem_fields as pf

GONE = "[contact detail removed]"


@pytest.mark.parametrize(
    "text",
    [
        "call me on \u0660\u0663\u0660\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667 tomorrow",
        "phone \u06f0\u06f3\u06f0\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7 please",
        "+92 300 1234567 is my number",
        "0092-300-1234567",
        "0300 123 4567",
        "(042) 35761234 office",
        "042-111-222-333 helpline",
        "03 00 1234567 mine",
        "+971 50 123 4567",
        "+44 7911 123456",
        "+1 415 555 2671",
        "+966 50 123 4567",
        "+91 98765 43210",
        "mail ali [at] example [dot] com now",
    ],
)
def test_a_phone_or_address_is_redacted(text):
    out, changed = pf.clean(text, 300)
    assert changed and GONE in out
    assert (
        not any(ch.isdigit() and ch not in "0" for ch in out.replace(GONE, "")) or "budget" in out
    )


@pytest.mark.parametrize(
    "text",
    [
        "budget is 50000 rupees by 15 march 2026 and 120 members",
        "rs 1,200,000 per month",
        "30 days, 2026-03-15",
        "we have 3 shops and 45 staff, about 2,500 customers",
        "50,000 rupees a month",
    ],
)
def test_budgets_figures_and_dates_are_untouched(text):
    out, changed = pf.clean(text, 300)
    assert out == text and not changed
