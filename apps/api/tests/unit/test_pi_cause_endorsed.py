"""L1 audit F: a cause is owner_said only when the OWNER endorsed it in their own words: not
negated, not hypothetical, not someone else's opinion, not pi's question said back, and the legacy
believes_cause path cannot promote a guess by function words or a first word."""

import pytest

from app.modules.pi import problem_fields as pf
from app.modules.pi.problems import ProblemBook, ProblemNote


def status(word, text):
    cause, _ = pf.merge_cause(None, word, True, [word], "m1", text)
    return cause["status"]


ENDORSED = [
    ("rent", "the rent is the problem"),
    ("rent", "I think it is the rent"),
    ("competitor", "mera competitor sasta hai"),
    ("competitor", "mujhe lagta hai competitor ki wajah se"),
    ("کرایہ", "مسئلہ کرایہ ہے"),
    ("المنافس", "المشكلة هي المنافس"),
    ("किराया", "समस्या किराया है"),
    ("rent", "sales are not growing, the rent is high"),
    ("staff", "my staff is slow"),
]
NOT_ENDORSED = [
    ("rent", "it is NOT the rent"),
    ("rent", "the rent is not the cause"),
    ("rent", "rent wajah nahi hai"),
    ("rent", "rent ki wajah nahi hai"),
    ("کرایہ", "کرایہ وجہ نہیں ہے"),
    ("الايجار", "ليس الايجار السبب"),
    ("किराया", "किराया वजह नहीं है"),
    ("rent", "if the rent were lower sales would grow"),
    ("rent", "agar rent kam hota to bikri barhti"),
    ("کرایہ", "اگر کرایہ کم ہو تو بکری بڑھے"),
    ("الايجار", "إذا كان الايجار أقل ستزيد المبيعات"),
    ("किराया", "अगर किराया कम हो तो बिक्री बढ़े"),
    ("rent", "my partner thinks it is the rent"),
    ("rent", "my wife says the rent is the cause"),
    ("rent", "bhai kehta hai rent wajah hai"),
    ("rent", "are you saying the rent is the cause?"),
    ("rent", "you are saying the rent is the cause"),
    ("rent", "kya rent wajah hai?"),
    ("rent", "aap keh rahe hain ke rent wajah hai"),
    ("الايجار", "هل الايجار هو السبب؟"),
    ("कुल", "क्या कुल किराया वजह है?"),
]


@pytest.mark.parametrize("word,text", ENDORSED)
def test_the_owners_own_claim_is_owner_said(word, text):
    assert status(word, text) == "owner_said", text


@pytest.mark.parametrize("word,text", NOT_ENDORSED)
def test_a_negated_hypothetical_borrowed_or_echoed_cause_is_pi_inferred(word, text):
    assert status(word, text) == "pi_inferred", text


def test_the_owner_who_says_it_after_a_negation_elsewhere_still_counts():
    text = "it is not the staff. the rent is the problem"
    assert status("rent", text) == "owner_said"
    assert status("staff", text) == "pi_inferred"


def legacy(believes, text):
    note = ProblemNote(title="Sales fell", believes_cause=believes)
    got, _ = ProblemBook.requirement_values(note, None, "m1", text)
    return got["cause"]["status"]


@pytest.mark.parametrize(
    "believes,text",
    [
        ("the supplier delays shipments", "the sales fell this month"),
        ("the supplier delays shipments", "the supplier is nice"),
        ("our competitor is cheaper than the others", "the shop is on the main road"),
        ("hai ye wajah hai ke supplier late hai", "bikri kam hai aur hai ye masla"),
        ("المنافس أرخص من الجميع", "المبيعات قلت هذا الشهر"),
    ],
)
def test_the_legacy_believes_cause_cannot_be_promoted_by_function_words(believes, text):
    assert legacy(believes, text) == "pi_inferred"


@pytest.mark.parametrize(
    "believes,text",
    [
        ("the supplier delays shipments", "the supplier delays shipments every week"),
        ("competitor sasta hai", "mera competitor sasta hai"),
        ("rent is high", "the rent is high and sales fell"),
    ],
)
def test_the_legacy_believes_cause_the_owner_really_said_is_owner_said(believes, text):
    assert legacy(believes, text) == "owner_said"


def test_function_words_are_never_evidence():
    assert pf.usable_words(["the", "rent", "hai"]) == ["rent"]
    cause, _ = pf.merge_cause(None, "the", True, ["the", "and"], "m", "the and the")
    assert cause["status"] == "pi_inferred"


def test_a_confirmed_or_owner_cause_is_not_replaced_by_a_guess_still():
    first, _ = pf.merge_cause(None, "rent", True, ["rent"], "m1", "the rent is high")
    assert first["status"] == "owner_said"
    again, _ = pf.merge_cause(first, "staff", True, ["staff"], "m2", "my partner thinks the staff")
    assert again is None  # a guess never touches what the owner said
