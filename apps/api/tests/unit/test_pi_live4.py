"""Live test 4 (owner, 2026-10-26): two chats with the exact customer words.

Chat 1, a clothing brand: "price asked in DM, then silence" must beat the attribution ideas; the
opener of a person who is not in a hurry is "Ji, ye do ideas abhi aazma sakte hain:" and "Workzap
could" never stays inside a Roman Urdu sentence.
Chat 2, a restaurant: theft, "raat ko stock kam nikalta hai, cash bhi kabhi kam hota hai" must get
the loss and cash ideas, never the shift rota because the word "staff" was there."""

from app.modules.pi import solution_ask, solution_ideas, solution_library, solutions
from app.modules.pi.service_conversation import roman_ideas_opener

CHAT1 = [
    {
        "group": "marketing_leads",
        "subtype": "few_leads",
        "title": "Views but no orders",
        "user_words": ["views aate hain par orders nahi aate"],
    },
    {
        "group": "sales_revenue",
        "subtype": "conversion_low",
        "title": "Price asked in DM, then silence",
        "user_words": ["sirf raqam puchty hain", "roz"],
    },
]
CHAT2 = [
    {"group": "people_staff", "subtype": "", "title": "Staff problems", "user_words": ["staff"]},
    {
        "group": "loss_security",
        "subtype": "theft_internal",
        "title": "Theft",
        "user_words": ["raat ko stock kam nikalta hai, cash bhi kabhi kam hota hai", "chori"],
    },
]


def words(item: dict) -> str:
    return " ".join([item["title"], *item["user_words"]])


def test_chat_1_the_price_problem_takes_the_overlay_entry_not_the_attribution_ideas() -> None:
    entries = solutions.load("fashion_and_apparel_brands")["problems"]  # type: ignore[index]
    best, chosen = -1, None
    for item in reversed(CHAT1):
        found = solution_ideas.match_problem(entries, item["group"], item["subtype"], words(item))
        if found is not None and solution_ideas.fit(found, words(item)) > best:
            best, chosen = solution_ideas.fit(found, words(item)), found
    assert chosen is not None and chosen["id"] == "x1_price_asked_then_silence"


def test_chat_2_theft_stock_and_cash_go_to_loss_and_cash_never_to_the_rota() -> None:
    order = solution_library.best_category(CHAT2)
    assert order[0] in ("loss_security", "stock_inventory", "cash_collections")
    assert order.index("loss_security") < order.index("people_staff")
    entries = solutions.load("restaurants")["problems"]  # type: ignore[index]
    for item in CHAT2:
        found = solution_ideas.match_problem(entries, item["group"], item["subtype"], words(item))
        assert found is None or found["category"] != "people_staff", item["title"]


def test_the_staff_word_alone_is_not_evidence() -> None:
    entry = {"words": "Staff roster clashes and shift swaps"}
    assert not solution_ideas.relevant(entry, "raat ko stock kam nikalta hai chori staff cash")
    assert solution_ideas.relevant(entry, "shift roster clashes between staff")


def test_the_opener_of_a_person_not_in_a_hurry_is_the_golden_one() -> None:
    said = "ap kya kr skty hain"
    assert not solution_ask.impatient(said) and not solution_ask.churn_risk(said)
    reply = "Theek hai, seedha solution.\n• Pehli idea.\n• Doosri idea."
    context = {
        "solution_asked": True,
        "solution_ideas": ["a", "b"],
        "latest_customer_message": said,
    }
    assert (
        roman_ideas_opener(reply, context).splitlines()[0]
        == "Ji, ye do ideas abhi aazma sakte hain:"
    )


def test_the_disclosure_line_stays_and_the_opener_follows() -> None:
    context = {
        "solution_asked": True,
        "solution_ideas": ["a"],
        "latest_customer_message": "solution do",
    }
    reply = "Hi, main pi hoon, Workzap ka AI.\n• Pehli idea."
    lines = roman_ideas_opener(reply, context).splitlines()
    assert lines[0].startswith("Hi, main pi hoon") and lines[1].startswith("Ji, ye do ideas")


def test_workzap_could_never_stays_in_a_roman_urdu_sentence() -> None:
    reply = "Workzap could aisa intezam kar sakta hai ke pata chale kaunsa ad kaam kar raha hai."
    assert roman_ideas_opener(reply, {}).startswith("Workzap aisa intezam kar sakta hai")
