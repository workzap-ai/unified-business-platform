"""Live test 6 (owner, clothing brand, 6 crore of unsold stock): the exact chat.

(1) "Hi" (2) "mera clothing brand hai mere baby and male cloths hain 6crore ka stock wo bechna
hai" (3) "warehouse and outlets" (4) "poore sets" (5) "solution dein ap".
The problem is stock to SELL OFF, not website and outlet stock out of sync; the chat stays
Roman Urdu."""

from types import SimpleNamespace

from app.modules.pi import solution_ideas, solution_library, solutions
from app.modules.pi.service_conversation import reply_language

NOTED = [
    {
        "group": "stock_inventory",
        "subtype": "overstock_dead_stock",
        "title": "Excess stock to sell off",
        "user_words": [
            "6crore ka stock wo bechna hai",
            "warehouse and outlets",
            "poore sets",
        ],
    }
]
WORDS = " ".join([NOTED[0]["title"], *NOTED[0]["user_words"]])
SYNC_ENTRY = "Website shows in stock but the outlet sold the last piece"


def test_stock_and_outlet_alone_are_not_evidence() -> None:
    entry = {"words": SYNC_ENTRY}
    assert not solution_ideas.relevant(entry, WORDS)


def test_the_fashion_pack_picks_the_clearance_entry_not_the_stock_sync_one() -> None:
    entries = solutions.load("fashion_and_apparel_brands")["problems"]  # type: ignore[index]
    found = solution_ideas.match_problem(entries, "stock_inventory", "overstock_dead_stock", WORDS)
    assert found is not None and found["id"] == "x2_excess_stock_to_sell"
    wrong = solution_ideas.match_problem(entries, "stock_inventory", "no_visibility", WORDS)
    assert wrong is None or wrong["id"] != "p2_no_visibility"


def test_the_library_gives_the_owners_clearance_ideas_for_unsold_stock() -> None:
    assert solution_library.best_category(NOTED)[0] == "stock_inventory"
    got = solution_library.ideas_for("stock_inventory", [], 2, WORDS)
    owner = [i["text"] for i in solution_library.modern()["stock_inventory"]]
    assert len(got) == 2 and all(idea in owner for idea in got)
    assert not any("buffer" in idea or "website" in idea.lower() for idea in got)


def test_the_five_clearance_ideas_are_all_in_the_library() -> None:
    ideas = [i["text"] for i in solution_library.modern()["stock_inventory"]]
    for start in (
        "Offer past buyers a first look at the unsold sets",
        "Show each ready set in a short video",
        "Display the slow sets at the front of the outlet",
        "Send a simple photo list of the sets to bulk buyers",
        "Group the unsold pieces into ready sets",
    ):
        assert any(i.startswith(start) for i in ideas), start


def said(body: str) -> SimpleNamespace:
    return SimpleNamespace(sender_type="customer", message_type="text", body=body)


def test_poore_sets_keeps_the_chat_in_roman_urdu() -> None:
    rows = [
        said("warehouse and outlets"),
        said(
            "mera clothing brand hai mere baby and male cloths hain 6crore ka stock wo bechna hai"
        ),
        said("Hi"),
    ]
    found = reply_language(SimpleNamespace(), said("poore sets"), rows)  # type: ignore[arg-type]
    assert found["reply_language"] == "roman_ur"
