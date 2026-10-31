"""GAP-3 and GAP-4 from the nine-industry scenarios: more fire and advice phrasings, and the
ordinary business text that must not trip them (retailers, fire-safety trade, statements).

Fire is life-safety: when unsure, the emergency must fire. Quiet is only for text that is clearly
past, hypothetical or an insurance claim."""

import importlib.util
import subprocess
from pathlib import Path

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


def _parent_safety():
    """safety.py as committed in 7ea978f (before the life-safety audit fixes)."""
    root = Path(__file__).resolve().parents[2]
    try:
        src = subprocess.run(
            ["git", "show", "7ea978f:apps/api/app/modules/pi/safety.py"],
            cwd=root,
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("commit 7ea978f is not available here")
    spec = importlib.util.spec_from_loader("safety_parent", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(src, "safety_parent.py", "exec"), module.__dict__)
    return module


def test_the_audit_cases_were_wrong_on_the_previous_commit():
    parent = _parent_safety()
    # live fires the whole-message marker search hid
    for text in (
        "jab main wahan pohcha aag lag gayi thi aur log andar hain",
        "insurance wale aaye hain, godown mein aag lag rahi",
        "dukan mein aag lag gya",
    ):
        assert parent.emergency(text) is None, text
    # retailer questions the old medicine pattern turned into a refusal
    assert parent.advice_asked("which medicine do you stock").value == "medical"
    assert parent.advice_asked("which tablet do you sell").value == "medical"
