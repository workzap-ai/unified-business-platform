"""GAP-3 and GAP-4 from the nine-industry scenarios: more fire and advice phrasings, and the
ordinary business text that must not trip them."""

import pytest

from app.modules.pi import safety


@pytest.mark.parametrize(
    "text",
    [
        "showroom mein aag lag gayi hai, log andar hain",
        "aag lag gayi hai",
        "godown mein aag lag rahi hai",
        "dukan mein aag lag gai",
        "gaari mein aag lag gayi",
        "दुकान में आग लग गई है",
        "گودام میں آگ لگ گئی ہے",
        "هناك حريق في المعرض",
    ],
)
def test_fire_is_an_emergency(text):
    assert safety.emergency(text) is safety.Emergency.FIRE


@pytest.mark.parametrize(
    "text",
    [
        "aag par chulha rakhna hai, stove ka quote chahiye",
        "hum fire insurance bechte hain",
        "aag lagane wala lighter ka stock chahiye",
        "fire extinguisher ka order dena hai",
    ],
)
def test_ordinary_text_is_not_an_emergency(text):
    assert safety.emergency(text) is None


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        (
            "can I legally hold the retailer's cheque if the tax invoice is wrong",
            safety.Advice.LEGAL,
        ),
        (
            "is this tablet formula legally allowed under drug law, tell me what the rules say",
            safety.Advice.LEGAL,
        ),
        (
            "which supplement should I tell my customer to take with this equipment",
            safety.Advice.MEDICAL,
        ),
        ("which vitamins can I recommend", safety.Advice.MEDICAL),
    ],
)
def test_advice_asks(text, kind):
    assert safety.advice_asked(text) is kind


@pytest.mark.parametrize(
    "text",
    [
        "we are a legal entity registered in Lahore",
        "Legal Eagle Traders is our company name",
        "we are a legally registered company and want a website",
        "our shop catalogue lists a supplement range and protein tubs",
        "we sell vitamins and supplements wholesale",
    ],
)
def test_ordinary_text_is_not_advice(text):
    assert safety.advice_asked(text) is None
