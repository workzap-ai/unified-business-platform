"""Price-disclosure policy: multilingual amounts are refused; discovery text passes."""

import pytest

from app.modules.pi.guard import ReplyRejected, validate_reply
from app.modules.pi.price_policy import check, disclosures, price_mode, redact_prices
from app.modules.pi.service_conversation import validate_service_reply

PRICES = [
    "Is website ki qeemat pachaas hazaar rupay hai.",  # Roman Urdu, written out
    "اس ویب سائٹ کی قیمت پچاس ہزار روپے ہے۔",  # Urdu script
    "The website costs fifty thousand.",
    "سعر الموقع خمسة آلاف درهم",  # Arabic
    "It will be around 50k",
    "Price: ٥٠٠٠",  # Arabic-Indic digits
    "Kul kharcha teen lakh hoga",
    "Das Angebot kostet fünfzig Euro",
    "Only $49 today",
]
DISCOVERY = [
    "Qeemat ke liye hamari team aap se rabta karegi. Aap ko website kab tak chahiye?",
    "Main aap ki baat team ko bata deta hoon, woh aap ke saath rabta karenge.",
    "What is your budget for this project, and when would you like to launch?",
    "Our team will prepare a quotation after reviewing your requirements.",
    "شکریہ! آپ کی ضروریات ہماری ٹیم کو بھیج دی گئی ہیں۔",
    "¿Para qué tipo de negocio es el sitio web?",
]


@pytest.mark.parametrize("text", PRICES)
@pytest.mark.parametrize("mode", ["quote", "ask_team", "hidden"])
def test_no_disclosure_modes_refuse_amounts_in_any_language(text: str, mode: str) -> None:
    assert disclosures(text)
    assert check(text, mode) == "PRICE_POLICY_BLOCKED"
    with pytest.raises(ReplyRejected):
        validate_service_reply(text, 4000, mode)


@pytest.mark.parametrize("text", DISCOVERY)
def test_discovery_and_budget_questions_are_allowed(text: str) -> None:
    assert disclosures(text) == []
    assert validate_service_reply(text, 4000, "quote") == text


def test_exact_mode_refuses_unverifiable_written_amounts_but_allows_evidence() -> None:
    assert check("Fifty thousand rupees", "exact") == "UNVERIFIABLE_AMOUNT"
    assert check("The router is 50.00 USD", "exact") is None
    assert validate_reply("The router is 50.00 USD", ['{"price": "50.00"}'], 4000)
    with pytest.raises(ReplyRejected):
        validate_reply("The router is Rs 500", ['{"price": "50.00"}'], 4000)
    assert validate_reply("The router is Rs 500", ['{"price": "500.00"}'], 4000)


def test_mode_defaults_and_redaction() -> None:
    assert price_mode({}, service=True) == "quote"
    assert price_mode({}, service=False) == "exact"
    assert price_mode({"price_disclosure": "hidden"}, service=False) == "hidden"
    data = {"items": [{"name": "Router", "price": "50.00", "variants": [{"unit_price": "1"}]}]}
    assert redact_prices(data) == {"items": [{"name": "Router", "variants": [{}]}]}


# Independent review 2026-09-29: teen number words next to price terms slipped through.
@pytest.mark.parametrize(
    "text",
    [
        "The fee is thirteen.",
        "The website costs fourteen.",
        "The price is sixteen.",
        "Qeemat pandrah hogi",
        "قیمت پندرہ ہے",
        "कीमत पंद्रह है",
        "El precio es quince",
    ],
)
@pytest.mark.parametrize("mode", ["hidden", "quote", "ask_team"])
def test_teen_amounts_are_refused_in_no_price_modes(text: str, mode: str) -> None:
    with pytest.raises(ReplyRejected):
        validate_service_reply(text, 4000, mode)


# The guard compares canonical amounts; a figure inside a larger one is not evidence.
@pytest.mark.parametrize(
    ("reply", "evidence"),
    [
        ("The router is Rs 50", '{"price": "150.00"}'),
        ("The router is Rs 15", '{"price": "150.00"}'),
        ("Total PKR 1,50", '{"total": "150.00"}'),
        ("It is Rs 4", '{"id": "a4f3", "price": "99.00"}'),
        ("That is 50.00", '{"price": "150.00"}'),
    ],
)
def test_amount_must_equal_an_evidence_value(reply: str, evidence: str) -> None:
    with pytest.raises(ReplyRejected):
        validate_reply(reply, [evidence], 4000)


@pytest.mark.parametrize(
    ("reply", "evidence"),
    [
        ("The router is Rs 150", '{"price": "150.00"}'),
        ("Total Rs 1,500", '{"total": "1500.00"}'),
        ("That will be 1500.00 PKR", '{"total": "1,500"}'),
        ("Kul Rs 1,50,000", '{"total": "150000.00"}'),
    ],
)
def test_equal_amounts_in_other_formats_are_supported(reply: str, evidence: str) -> None:
    assert validate_reply(reply, [evidence], 4000) == reply
