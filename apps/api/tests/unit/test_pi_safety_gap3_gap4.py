"""GAP-3 and GAP-4 from the nine-industry scenarios: more fire and advice phrasings, and the
ordinary business text that must not trip them (retailers, fire-safety trade, statements).

Fire is life-safety: when unsure, the emergency must fire. Quiet is only for text that is clearly
past, hypothetical or an insurance claim."""

import pytest

from app.modules.pi import safety

FIRE = [
    "showroom mein aag lag gayi hai, log andar hain",
    "aag lag gayi hai",
    "godown mein aag lag rahi hai",
    "dukan mein aag lag gai",
    "gaari mein aag lag gayi",
    "dukan mein aag hai",
    "ag lag gayi hai",
    "aag lagg gayi hai",
    "dukan mein aag lag gya",
    "dukan mein aag lag gyi",
    "aag lag gaee",
    "aaag lag gayi",
    "agg lag gayi",
    "aag lag gayi h",
    "aag lagne wali hai",
    "aag lag jayegi, jaldi aayen",
    "agar nahi bujhi to, aag lag gayi hai",  # a present fire stays caught
    "pichle saal ki baat hai, abhi phir aag lag gayi hai, log andar hain",
    # past or conditional words elsewhere in the message must not hide a live fire
    "jab main wahan pohcha aag lag gayi thi aur log andar hain",
    "dukan mein aag lag gayi thi, ab bhi dhuan hai, log andar hain",
    "pehle aag lag gayi thi ab phir lag gayi hai",
    "mera bhai andar phansa tha aur aag lag gayi",
    "aag lag gayi, agar jaldi na aaye to sab jal jayega",
    "jab tak fire brigade aaye aag lag gayi, log andar hain",
    "insurance wale aaye hain, godown mein aag lag rahi",
    "aag lag gayi h",
    "दुकान में आग लग गई है",
    "گودام میں آگ لگ گئی ہے",
    "هناك حريق في المعرض",
]


@pytest.mark.parametrize("text", FIRE)
def test_fire_is_an_emergency(text):
    assert safety.emergency(text) is safety.Emergency.FIRE


@pytest.mark.parametrize(
    "text",
    [
        "aag par chulha rakhna hai, stove ka quote chahiye",
        "hum fire insurance bechte hain",
        "aag lagane wala lighter ka stock chahiye",
        "fire extinguisher ka order dena hai",
        "fire alarm installation ka quote chahiye",
        "dukan mein aag se bachao ka extinguisher quote chahiye",
        "gaari mein aag bujhane ka system chahiye",
        "godown mein aag alarm lagwana hai",
        "pichle saal showroom mein aag lag gayi thi, insurance claim karna hai",
        "agar aag lag gayi to claim milega?",
        "aag lag gayi to extinguisher kaam karega?",
        "agar aag lag jaye to insurance cover karegi?",
    ],
)
def test_past_hypothetical_and_trade_text_is_not_an_emergency(text):
    assert safety.emergency(text) is None


def test_a_past_marker_hides_a_fire_only_in_its_own_clause():
    # same clause: quiet
    assert safety.emergency("pichle saal dukan mein aag lag gayi thi") is None
    # the marker sits in another clause: the fire clause has none, so it fires
    assert (
        safety.emergency("pichle saal claim kiya tha, dukan mein aag lag gayi")
        is safety.Emergency.FIRE
    )
    # a danger word anywhere in the message wins over a marker in the fire clause
    assert (
        safety.emergency("pichle saal showroom mein aag lag gayi thi, madad chahiye")
        is safety.Emergency.FIRE
    )


ADVICE = [
    ("can I legally hold the retailer's cheque if the tax invoice is wrong", safety.Advice.LEGAL),
    (
        "is this tablet formula legally allowed under drug law, tell me what the rules say",
        safety.Advice.LEGAL,
    ),
    (
        "which supplement should I tell my customer to take with this equipment",
        safety.Advice.MEDICAL,
    ),
    ("which supplement should I take", safety.Advice.MEDICAL),
    ("what medicine should I take for this", safety.Advice.MEDICAL),
    ("which tablet should I take", safety.Advice.MEDICAL),
    ("which medicine should my child take", safety.Advice.MEDICAL),
    ("which medicine should I give the guest for the food poisoning", safety.Advice.MEDICAL),
    ("am I legally required to pay the notice period", safety.Advice.LEGAL),
    ("is this legal?", safety.Advice.LEGAL),
    ("can I take him to court", safety.Advice.LEGAL),
]


@pytest.mark.parametrize(("text", "kind"), ADVICE)
def test_advice_asks(text, kind):
    assert safety.advice_asked(text) is kind


@pytest.mark.parametrize(
    "text",
    [
        "which supplements do you stock",
        "what protein powder should we stock in the shop",
        "which painkillers do you sell",
        "which vitamins can I order",
        "what supplements to import",
        "which vitamins can I recommend",
        "which protein powder should we recommend for my customers",
        "which vitamins can I give my customers as a free sample",
        "what supplement should we put on the shelf for my gym members",
        "which supplement should I stock for my gym members to take",
        "which medicine do you stock",
        "which tablet do you sell",
        "which drug do you recommend for the pharmacy",
        "which medicine should we stock for the pharmacy",
        "our labels are legally required, we need printing",
        "we are a legal entity registered in Lahore",
        "is this legal entity name available",
        "is this legal size paper in stock",
        "is this legal pad ruled",
        "Legal Eagle Traders is our company name",
        "we are a legally registered company and want a website",
        "our shop catalogue lists a supplement range and protein tubs",
        "we sell vitamins and supplements wholesale",
    ],
)
def test_ordinary_text_is_not_advice(text):
    assert safety.advice_asked(text) is None


# Strings from the third audit, with the result verified by running them.
AUDIT_FIRE_YES = [
    ("please come, aag lag gayi in the shop", "fire"),
    ("aag lag gayi in our godown we need to leave", "fire"),
    ("the godown mein aag lag gayi", "fire"),
    ("godown mein aag lag gayi please come to help", "fire"),
    ("mere ghar mein aag lag gayi thi, bacchay andar hain", "fire"),
    ("godown mein aag lag gayi thi bhai andar hai", "fire"),
    ("godown mein aag lag gayi thi aur mazdoor andar hain", "fire"),
    ("emergency hai, godown mein aag lag gayi thi", "fire"),
    ("help! godown mein aag lag gayi thi", "fire"),
    ("aag lag gayi agar jaldi na aaye to sab jal jayega", "fire"),
    ("log andar phas gaye", "generic"),
    ("andar fas gaye", "generic"),
    ("aag laga hai", "fire"),
    ("aag laga", "fire"),
    ("aag lg gayi", "fire"),
    ("aag lag gaii", "fire"),
    ("aag lag geyi", "fire"),
    ("aag lag gye", "fire"),
    ("aag lag ga", "fire"),
    ("aag achanak lag gayi", "fire"),
    ("aag dukan mein lag gayi hai", "fire"),
    ("aag to lag gayi", "fire"),
    ("fire lag gayi hai", "fire"),
    ("fire ho gayi hai", "fire"),
    ("dukan jal rahi hai", "fire"),
    ("jalne laga", "fire"),
    ("jal gaya", "fire"),
    ("ghar mein aag hai", "fire"),
    ("kitchen mein aag hai", "fire"),
    ("mill mein aag hai", "fire"),
    ("yahan aag hai", "fire"),
    ("kal aag lag gayi thi, bacha hua maal bechna hai", "fire"),
]

AUDIT_FIRE_NO = [
    "aag lagne wali cheezein ka quote chahiye",
    "pichle mahine aag lag gayi thi, ab claim file karna hai",
    "pichle saal showroom mein aag lag gayi thi, insurance claim karna hai",
    "agar aag lag gayi to claim milega?",
    "aag lag gayi to extinguisher kaam karega?",
    "agar aag lag jaye to insurance cover karegi?",
    "dukan mein aag se bachao ka extinguisher quote chahiye",
    "gaari mein aag bujhane ka system chahiye",
    "godown mein aag alarm lagwana hai",
    "aag par chulha rakhna hai, stove ka quote chahiye",
]

AUDIT_ADVICE_YES = [
    ("which medicine should I buy for my headache", "medical"),
    ("which tablet should I take, I keep getting fever", "medical"),
    ("which medicine should I take for my back pain from standing in the shop all day", "medical"),
    ("which tablet should I take, I put on weight", "medical"),
    ("is this legal notice valid", "legal"),
    ("is this legal document enforceable", "legal"),
    ("is that legal paper binding in court", "legal"),
    ("which tablet should I take", "medical"),
    ("which medicine should my child take", "medical"),
]

AUDIT_ADVICE_NO = [
    "is it legal size paper?",
    "is this legal size paper in stock",
    "is this legal pad ruled",
    "which medicine do you stock",
    "which tablet do you sell",
    "which drug do you recommend for the pharmacy",
    "which medicine should we stock for the pharmacy",
    "which supplement should I stock for my gym members to take",
    "which vitamins can I give my customers as a free sample",
    "which protein powder should we recommend for my customers",
    "what supplement should we put on the shelf for my gym members",
    "which supplements do you stock",
]


@pytest.mark.parametrize(("text", "kind"), AUDIT_FIRE_YES)
def test_audit_fire_fires(text, kind):
    assert safety.emergency(text).value == kind


@pytest.mark.parametrize("text", AUDIT_FIRE_NO)
def test_audit_fire_text_stays_quiet(text):
    assert safety.emergency(text) is None


@pytest.mark.parametrize(("text", "kind"), AUDIT_ADVICE_YES)
def test_audit_advice_asked(text, kind):
    assert safety.advice_asked(text).value == kind


@pytest.mark.parametrize("text", AUDIT_ADVICE_NO)
def test_audit_advice_not_asked(text):
    assert safety.advice_asked(text) is None


def test_a_salvage_message_after_a_fire_still_gets_the_emergency_reply():
    # decided: with no insurance/claim/period marker a past fire is treated as an emergency
    # ("when in doubt it fires"); with a claim marker the flow stays quiet.
    assert safety.emergency("kal aag lag gayi thi, bacha hua maal bechna hai") is not None
    assert safety.emergency("pichle mahine aag lag gayi thi, ab claim file karna hai") is None


def test_to_and_the_in_a_mixed_language_message_do_not_hide_a_fire():
    assert safety.emergency("godown mein aag lag gayi please come to help") is not None
    assert safety.emergency("the godown mein aag lag gayi") is not None


@pytest.mark.parametrize(
    "text",
    [
        "aag lag gayi",
        "aag",
        "Aag!",
        "aag aag",
        "fire",
        "fire!",
        "dhuan",
        "dhuan dhuan",
        "jal gaya",
        "aag lagi thi",
        "aag lag gayi thi",
        "kal aag lag gayi",
        "agar aag lag jaye",
    ],
)
def test_ambiguous_fire_messages_are_never_quiet(text):
    assert safety.emergency(text) is not None


@pytest.mark.parametrize(
    "text",
    [
        "fire extinguisher",
        "fire insurance",
        "dhuan nikalne ka pankha chahiye",
    ],
)
def test_a_trade_phrase_with_a_fire_word_is_not_a_bare_cry(text):
    assert safety.emergency(text) is None
