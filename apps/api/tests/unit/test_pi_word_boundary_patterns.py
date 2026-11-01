"""Patterns that held a backspace instead of a word boundary and so never matched.

map_edit.STRONG_LINK (and the stance it drives) and the online-listing asset group in
idea_filter._ASSET_GROUPS. Both are live now, so these tests pin what they catch and, as important,
what they leave alone.
"""

import pytest

from app.modules.pi import idea_filter, map_edit

LISTING_IDEA, LISTING_OWNER = next(
    group for group in idea_filter._ASSET_GROUPS if "listing" in group[0].pattern
)
OWNER_WORDS = "I run a car showroom in Okara and sales are slow"


# ---------------------------------------------------------------- map_edit: STRONG_LINK itself


@pytest.mark.parametrize(
    "text",
    [
        "this connection is wrong",
        "that link is wrong",
        "ye jorr galat hai",
        "yeh jor theek nahi",
        "wrong arrow",
        "THIS CONNECTION is wrong",
        "woh rishta galat hai",
        "is taalluq ko hatao",
        "ye taaluq galat hai",
        "ye jarr galat hai",
        "ye jarh galat hai",
        "یہ جوڑ غلط ہے",
        "هذا الرابط خاطئ",
        "الربط غلط",
    ],
)
def test_strong_link_matches_map_link_talk(text: str) -> None:
    assert map_edit.STRONG_LINK.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "connection wrong hai",  # "connection" alone is not strong
        "the connection is wrong",
        "my internet connection",
        "the connections of the town",
        "disconnection fee",
        "narrower",
        "I sell tyres in Okara",
        "the price is wrong",
        "rishta bhejna hai",  # a marriage proposal, not a link
    ],
)
def test_strong_link_ignores_everything_else(text: str) -> None:
    assert not map_edit.STRONG_LINK.search(text)


# ---------------------------------------------------------------- owner sentences


def outcome(said: str, named: int = 0) -> str:
    """no-edit | none (the model answers) | ask (which link) | go (remove the one link)."""
    if map_edit.wants(said) != "unlink":
        return "no-edit"
    return map_edit.link_stance(said, named)


GO = [
    "this connection is wrong",
    "this link is wrong",
    "that link is wrong",
    "this arrow is wrong",
    "please remove this link",
    "delete that arrow",
    "ye jorr galat hai",
    "yeh jor galat hai",
    "is jor ko hatao",
    "woh taalluq galat hai",
    "ye rishta galat hai",
    "this connection is incorrect",
    "no, this link is wrong",  # "no," is a yes here, not a negation
    "these two are not connected, the arrow is wrong",
    "یہ جوڑ غلط ہے",
    "الرابط خاطئ",
    "هذا الربط غلط",
    "ce lien est faux",
]
NONE = [
    "my internet connection is wrong",
    "the wifi connection is wrong in my shop",
    "the connection is bad, please remove the old router",
    "remove my connection to that supplier",
    "delete my account connection",
    "my website link is wrong",
    "the link on my facebook page is wrong",
    "delete the link to the instagram page",
    "the electricity connection is wrong",
    "bijli ka connection galat hai",
    "network connection is wrong",
    "my supplier link is wrong",
    "انٹرنیٹ کا جوڑ غلط ہے",
    "الرابط في الموقع خاطئ",
    "رابط الحساب خاطئ",
]
ASK = [
    "connection wrong hai",
    "the connection is wrong",
    "wrong connection",
    "remove the connection",
    "delete the link",
    "that is a wrong link",
    "galat jor",
]
NO_EDIT = [
    "yeh jor galat nahi hai",
    "connection wrong nahi hai",
    "this link is not wrong",
    "this link isn't wrong",
    "this connection is not wrong",
    "don't remove this link",
    "never remove the arrow",
    "yeh jor galat nhi",
    "یہ جوڑ غلط نہیں ہے",
    "هذا الربط ليس غلط",
    "is this link wrong?",
    "ye jor galat hai kya?",
    "ये जोड़ गलत नहीं है",
    "my website link is not working",
    "the internet is slow today",
    "stock kam ho jata hai",
]


@pytest.mark.parametrize("said", GO)
def test_a_map_link_sentence_removes_the_link(said: str) -> None:
    assert outcome(said) == "go"


@pytest.mark.parametrize("said", NONE)
def test_another_kind_of_connection_is_never_a_map_edit(said: str) -> None:
    assert outcome(said) in {"none", "no-edit"}
    assert outcome(said) != "go"
    assert outcome(said) != "ask"


@pytest.mark.parametrize("said", ASK)
def test_a_vague_connection_asks_which_link_instead_of_removing(said: str) -> None:
    assert outcome(said) == "ask"


@pytest.mark.parametrize("said", NO_EDIT)
def test_a_negated_or_questioned_link_is_no_edit(said: str) -> None:
    assert outcome(said) == "no-edit"


def test_naming_two_problems_makes_it_the_maps_link_even_with_a_technical_word() -> None:
    assert outcome("remove the link between P1 and P2", named=2) == "go"
    assert outcome("the internet connection link between P1 and P2 is wrong", named=2) == "go"


def test_naming_one_problem_does_not_excuse_another_domain() -> None:
    assert outcome("my internet connection is wrong, P1", named=1) == "none"
    assert outcome("remove my connection to that supplier", named=1) == "none"
    assert outcome("the connection to P1 is wrong", named=1) == "go"


def test_the_ask_line_is_one_question_asking_which_link() -> None:
    text = map_edit.line("which_link", "en")
    assert "Which link do you mean" in text and text.count("?") == 1


def test_a_not_connected_phrase_is_still_an_edit_despite_its_own_negation() -> None:
    assert map_edit.wants("these two are not connected") == "unlink"
    assert map_edit.wants("ye dono related nahi hain") == "unlink"


# ---------------------------------------------------------------- idea_filter: idea side (strict)


def test_the_listing_group_is_the_one_under_test() -> None:
    assert "listing" in LISTING_IDEA.pattern and "googl" in LISTING_OWNER.pattern


@pytest.mark.parametrize(
    "idea",
    [
        "Claim your google listing and add photos",
        "Check how you show up when someone searches nearby",
        "Update your business listing hours",
        "Look at your online reviews each week",
        "Make sure people who search for you online find your showroom",
        "People search for your shop on their phones",
        "People search for us on their phones",
        "Customers search for them first, so be there",
        "Many people search for a shop before they drive over",
        "Buyers search for an honest dealer first",
        "Add the place to your map listing",
        "Fix your online presence first",
        "Open with google",
        "Fix the listing",
        "Tidy the business listing",
        "Check the google map listing",
    ],
)
def test_listing_idea_pattern_matches(idea: str) -> None:
    assert LISTING_IDEA.search(idea)


@pytest.mark.parametrize(
    "idea",
    [
        "Ask customers what stopped them buying",
        "Call the three customers who left",
        "Tidy the counter before opening",
        "Look at the showroom the way a stranger does when they search for it nearby",
        "We search for a cheaper supplier together",
        "Search for an hour of quiet time each week",
        "Check your listings",  # idea side stays whole-word
        "Ungoogleable means nothing here",
        "The googled answer is wrong",
        "Relisting is not needed",
        "Ask your mapper",
    ],
)
def test_listing_idea_pattern_ignores_normal_text(idea: str) -> None:
    assert not LISTING_IDEA.search(idea)


# ---------------------------------------------------------------- idea_filter: owner side (wide)


@pytest.mark.parametrize(
    "owner",
    [
        "people find me on google",
        "my website is old",
        "reviews are low",
        "our listings are wrong",
        "customers googled us",
        "we want to be found on gmaps",
        "gugal par hamari dukaan nahi milti",
        "we are on g-maps",
        "my gmap pin is off",
        "people are searching for tyres",
        "they searched last week",
        "he reviewed us badly",
        "I get reviewing emails",
        "I have an app",
        "put us on the map",
        "my page is dead",
        "websites cost a lot",
        "we sell online",
        "no internet at the shop",
        "I use facebook",
        "my fb is old",
        "insta is busy",
        "instagram helps",
        "I have whatsapp business",
        "people gogle us",
        "ہماری گوگل لسٹنگ پرانی ہے",
        "گوگل میپس پر نہیں ہیں",
        "ہماری ویب سائٹ نہیں ہے",
        "گاہک آن لائن ڈھونڈتے ہیں",
        "انٹرنیٹ پر نظر نہیں آتے",
        "جوجل پر نہیں",
        "قوقل خرائط",
        "الموقع قديم",
        "الزبائن يبحثون في الإنترنت",
        "गूगल पर नहीं हैं",
        "हमारी वेबसाइट पुरानी है",
        "ग्राहक ऑनलाइन ढूंढते हैं",
        "search results are bad",
    ],
)
def test_owner_listing_pattern_matches_the_owner_naming_the_web(owner: str) -> None:
    assert LISTING_OWNER.search(owner)


@pytest.mark.parametrize(
    "owner",
    [
        "rapport with staff is poor",
        "mapping the stock is slow",
        "I sell tyres",
        "we do research on tyres",
        "I use whatsapp for orders",
        "our roadmap is tight",
        "slippage in stock is high",
        "sales are slow",
        "customers walk in and leave",
        "the showroom is on the main road",
        "gadi ka rate poochte hain",
        "ہم گاڑیاں بیچتے ہیں",
    ],
)
def test_owner_listing_pattern_needs_whole_words_and_a_web_word(owner: str) -> None:
    assert not LISTING_OWNER.search(owner)


@pytest.mark.parametrize(
    ("idea", "owner"),
    [
        ("Check your listing hours", "our listings are wrong"),
        ("Check what customers see when they search online", "customers googled us"),
        ("Check what customers see when they search online", "we want to be found on gmaps"),
        ("Update your Google profile hours", "gugal par hamari dukaan nahi milti"),
        ("Check your listing hours", "ہماری گوگل لسٹنگ پرانی ہے"),
        ("Claim your google listing", "customers googled us"),
        ("Fix your online presence", "हमारी वेबसाइट पुरानी है"),
    ],
)
def test_an_owner_who_named_the_web_is_not_told_off_for_the_idea(idea: str, owner: str) -> None:
    assert idea_filter.invented_context(idea, owner) is None


@pytest.mark.parametrize(
    "idea",
    [
        "Claim your google listing today",
        "Update your business listing with the new hours",
        "Make sure people who search for you online find the showroom",
    ],
)
def test_an_idea_about_a_listing_is_flagged_when_the_owner_never_mentioned_one(idea: str) -> None:
    assert idea_filter.invented_context(idea, OWNER_WORDS) == "G2"


# ---------------------------------------------------------------- the 15 sentences, en and roman_ur


@pytest.mark.parametrize(
    "idea",
    [
        "Make sure people who search for you online find your showroom",
        "People search for your shop on their phones, so check what they see",
        "Check what comes up when customers search online for a showroom",
        "When people searches nearby for cars, be the first they see",
        "Claim your google listing and add three photos",
        "Update your business listing with the new opening hours",
        "Reply to your online reviews every Friday",
        "Jab log search for you online karein, to listing update karein",
        "Log aap ki dukaan online search for your shop karte hain, to listing update karein",
    ],
)
def test_g2_flags_an_idea_that_assumes_an_online_presence(idea: str) -> None:
    assert idea_filter.invented_context(idea, OWNER_WORDS) == "G2"


@pytest.mark.parametrize(
    "idea",
    [
        "Look at the showroom the way a stranger does when they search for it nearby, "
        "so you see what puts them off.",
        "Ask each of your last two buyers how they first heard of the showroom",
        "Call the three customers who left and ask what stopped them",
        "Gahak se poochain ke unhon ne dukaan kaise dhoondi",
        "Tidy the counter and greet each visitor within a minute",
        "Write down every price you quoted this week and the answer you got",
    ],
)
def test_g2_leaves_look_at_and_ask_ideas_alone(idea: str) -> None:
    assert idea_filter.invented_context(idea, OWNER_WORDS) is None
