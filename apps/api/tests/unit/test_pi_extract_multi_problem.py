"""Live Audit 5, A52: the owner's four-line message must become four problems, none dropped."""

import asyncio
from types import SimpleNamespace

from app.modules.pi import problem_extract as pe

FOUR_LINES = (
    "Sales: uses QB. Stock: about 10 crore, written on paper. "
    "Staff: no track of who comes and goes. Cash: in and out don't match."
)
NOTES = [
    ("Sales tracked only in QuickBooks", "Sales: uses QB", "sales_revenue"),
    (
        "Stock of about 10 crore kept on paper",
        "about 10 crore, written on paper",
        "stock_inventory",
    ),
    ("No record of staff coming and going", "no track of who comes and goes", "people_staff"),
    ("Cash in and out do not match", "in and out don't match", "cash_collections"),
]


class Manager:
    def __init__(self, notes: list[pe.SimpleNote]) -> None:
        self.notes = notes
        self.payload: dict = {}

    async def complete_structured(self, scope, model, **kwargs):  # noqa: ANN001, ANN003
        import json

        self.payload = json.loads(kwargs["messages"][1].content)
        return SimpleNamespace(value=pe.Extracted(found=self.notes))


def note(title: str, words: str, category: str) -> pe.SimpleNote:
    return pe.SimpleNote(
        title=title, title_local=title, user_words=[words] if words else [], category=category
    )


def context() -> dict:
    return {
        "pi_mode": "brain",
        "latest_customer_message": FOUR_LINES,
        "history": [],
        "noted_problems": [],
        "reply_language": "en",
    }


def run(manager: Manager) -> list:
    return asyncio.run(pe.extract(manager, None, context()))


def test_a52_four_problems_in_one_message_are_all_kept() -> None:
    ops = run(Manager([note(*n) for n in NOTES]))
    assert [op.note.title for op in ops] == [n[0] for n in NOTES]


def test_a52_one_bad_note_does_not_drop_the_good_ones() -> None:
    bad = note("Stock", "", "stock_inventory")  # no user_words: check_ops rejects it
    ops = run(Manager([note(*NOTES[0]), bad, note(*NOTES[3])]))
    assert [op.note.title for op in ops] == [NOTES[0][0], NOTES[3][0]]


def test_a52_a_long_message_is_sent_whole() -> None:
    manager = Manager([note(*NOTES[0])])
    long_text = " ".join(f"Problem {i}: something is wrong with item {i}." for i in range(60))
    ctx = context() | {"latest_customer_message": long_text}
    asyncio.run(pe.extract(manager, None, ctx))
    assert manager.payload["latest"] == long_text[: pe.MAX_MESSAGE_CHARS]
    assert pe.MAX_MESSAGE_CHARS >= 2000
