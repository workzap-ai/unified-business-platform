"""GAP-3 and GAP-4 from the nine-industry scenarios: more fire and advice phrasings, and the
ordinary business text that must not trip them (retailers, fire-safety trade, statements)."""

import re

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
    "agar nahi bujhi to, aag lag gayi hai",  # a present fire stays caught
    "pichle saal ki baat hai, abhi phir aag lag gayi hai, log andar hain",
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
    ],
)
def test_ordinary_text_is_not_an_emergency(text):
    assert safety.emergency(text) is None


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
        "our labels are legally required, we need printing",
        "we are a legal entity registered in Lahore",
        "is this legal entity name available",
        "Legal Eagle Traders is our company name",
        "we are a legally registered company and want a website",
        "our shop catalogue lists a supplement range and protein tubs",
        "we sell vitamins and supplements wholesale",
    ],
)
def test_ordinary_text_is_not_advice(text):
    assert safety.advice_asked(text) is None


def test_the_positive_cases_failed_on_the_parent_commit():
    """The parent's patterns, copied here: the gap cases were missed, so the fix is the change."""
    old_fire = re.compile(
        r"\b(?:aag lag(?:i|gayi|gai|ayi)|(?:shop|godown|factory|dukan|dukaan) mein aag)\b",
        re.IGNORECASE,
    )
    assert not old_fire.search("showroom mein aag lag gayi hai, log andar hain")
    old_legal = re.compile(
        r"\b(?:is it (?:legal|illegal|allowed by law)|can i sue)\b", re.IGNORECASE
    )
    assert not old_legal.search(ADVICE[0][0])
    assert not old_legal.search(ADVICE[1][0])
    old_medical = re.compile(
        r"\b(?:which (?:medicine|tablet|drug|antibiotic)|what dose)\b", re.IGNORECASE
    )
    assert not old_medical.search(ADVICE[2][0])
