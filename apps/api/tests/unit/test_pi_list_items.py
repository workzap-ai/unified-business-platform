"""B1: an item the owner listed is never lost between their message and the notes."""

from types import SimpleNamespace

import pytest

from app.modules.pi import list_items

BULLETS = """Problems this month:
- Cash at day end does not match, short by 4,000 rupees
- Cashiers come late on weekends
- Stock of rice runs out in two shops
- Suppliers deliver late every Monday
"""


def note(title: str, summary: str = "", user_words: list[str] | None = None):
    return SimpleNamespace(
        title=title, title_local="", summary=summary, user_words=user_words or []
    )


def test_a_bulleted_message_is_cut_into_items_in_order() -> None:
    found = list_items.items(BULLETS)
    assert [i.id for i in found] == ["c1", "c2", "c3", "c4"]
    assert found[0].figures == ("4000",)  # the figure travels with its item
    assert found[1].text == "Cashiers come late on weekends"


def test_numbered_lines_and_inline_numbers_are_lists() -> None:
    lines = "1) rice runs out every week\n2) the till is short most evenings\n3) staff keep leaving"
    assert len(list_items.items(lines)) == 3
    inline = "1. rice runs out every week 2. the till is short most evenings 3. staff keep leaving"
    assert len(list_items.items(inline)) == 3


def test_several_long_lines_without_markers_are_a_list() -> None:
    rant = "rice runs out every week\nthe till is short most evenings\nstaff keep leaving early"
    assert len(list_items.items(rant)) == 3


@pytest.mark.parametrize(
    "message",
    [
        "stock runs out in two shops",  # one sentence
        "hello\nthanks",  # short lines
        "- one thing only here",  # a single bullet
        "",
        "我的店库存经常不足\n收银员总是迟到\n供应商送货很晚",  # unspaced script: stay out of it
    ],
)
def test_what_is_not_a_list_gives_no_items(message: str) -> None:
    assert list_items.items(message) == []


def test_an_item_with_a_figure_is_covered_by_a_note_that_has_the_figure() -> None:
    item = list_items.items(BULLETS)[0]
    assert list_items.covered(item, ["Cash short 4,000 at day end"])
    assert not list_items.covered(item, ["Cashiers late"])


def test_nothing_is_dropped_when_every_item_is_noted() -> None:
    notes = [
        "Cash short at day end 4000",
        "Cashiers late on weekends",
        "Rice stock runs out in two shops",
        "Suppliers late every Monday",
    ]
    assert list_items.dropped([BULLETS], notes) == []


def test_the_dropped_item_is_named_in_the_reason() -> None:
    notes = ["Cash short at day end 4000", "Cashiers late on weekends", "Rice stock runs out"]
    missing = list_items.dropped([BULLETS], notes)
    assert [i.id for i in missing] == ["c4"]
    reason = list_items.reason(missing) or ""
    assert "Suppliers deliver late every Monday" in reason and "problem_ops" in reason


def test_a_long_report_is_cut_short_in_the_reason() -> None:
    many = "\n".join(f"- item number {n} about a different thing {n}00 rupees" for n in range(1, 8))
    reason = list_items.reason(list_items.dropped([many], [])) or ""
    assert "more)" in reason and reason.count("'") <= 8


def test_the_guard_is_off_unless_the_workspace_turned_it_on() -> None:
    context = {
        "pi_mode": "brain",
        "flow": {"state": "S1_LISTENING"},
        "latest_customer_message": BULLETS,
    }
    assert list_items.guard(context, [note("Cash short")]) is None
    on = list_items.guard(
        {**context, "list_guard": True}, [SimpleNamespace(note=note("Cash short 4000"))]
    )
    assert on and "Cashiers come late" in on


def test_the_guard_counts_problems_noted_in_earlier_turns() -> None:
    context = {
        "pi_mode": "brain",
        "list_guard": True,
        "flow": {"state": "S2_CLARIFYING"},
        "latest_customer_message": BULLETS,
        "noted_problems": [
            {"title": "Cashiers come late on weekends", "summary": ""},
            {"title": "Rice stock runs out in two shops", "summary": ""},
            {"title": "Suppliers deliver late every Monday", "summary": ""},
        ],
    }
    ops = [SimpleNamespace(note=note("Cash short at day end", user_words=["short by 4,000"]))]
    assert list_items.guard(context, ops) is None


def test_the_guard_stays_out_of_other_states_and_modes() -> None:
    base = {"list_guard": True, "latest_customer_message": BULLETS}
    assert (
        list_items.guard({**base, "pi_mode": "brain", "flow": {"state": "S5_READINESS"}}, [])
        is None
    )
    assert list_items.guard({**base, "flow": {"state": "S1_LISTENING"}}, []) is None
