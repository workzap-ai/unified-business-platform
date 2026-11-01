# ruff: noqa: E501
"""Scope before money: an owner who asks for a whole system gets one question about what it must
cover (what they manage today, and roughly how many of each) BEFORE any question about budget,
staff or deadline. Production (1 Nov, a rental business: "a proper system to manage my entire
business") got a budget question straight after two free ideas, with no questions about the
properties, tenants, agreements, staff or payment records.

Data and one pure function; asked once per chat (the caller keeps the flag in the brief)."""

from __future__ import annotations

import re
from collections.abc import Sequence

MONEY_FIRST = frozenset(
    {"budget_ceiling", "budget_currency_period", "staff_headcount", "deadline_duration"}
)

# the owner asks for a system, software, an app, a platform, or to manage everything
WANTS_SYSTEM = re.compile(
    r"\b(?:system|software|app|application|platform|dashboard|portal|crm|erp|automat\w*|"
    r"manage (?:my |the )?(?:entire |whole |complete )?business)\b"
    r"|سسٹم|سافٹ ?ویئر|ایپ|نظام|برنامج|تطبيق",
    re.IGNORECASE,
)

QUESTION = {
    "en": "To plan this properly: what do you manage today, and roughly how many of each?",
    "roman_ur": "Isay theek se plan karne ke liye: aap aaj kya kya sanbhalte hain, aur har ek kitne hain?",
    "ur": "اسے ٹھیک سے پلان کرنے کے لیے: آپ آج کیا کیا سنبھالتے ہیں، اور ہر ایک کتنے ہیں؟",
    "ar": "لنخطط لهذا جيدا: ماذا تديرون اليوم، وكم عدد كل منها تقريبا؟",
}


def scope_question(
    pending_key: str | None,
    owner_messages: Sequence[str],
    already_asked: bool,
    language: str | None,
) -> str | None:
    """The scope question to put in place of a money question, or None."""
    if already_asked or pending_key not in MONEY_FIRST:
        return None
    if not any(WANTS_SYSTEM.search(m or "") for m in owner_messages):
        return None
    return QUESTION.get(language or "en", QUESTION["en"])
