# ruff: noqa: E501  (the phrase bank reads better on one line each)
"""Industry solutions for pi (Addendum 2 to the pi Brain v3, Parts 1.9 and 2).

Each industry has packs/solutions/<industry_key>.json (built from the addendum by
scripts/build_industry_solutions.py, linked to the industry pack by key): the problems owners
raise in their own words, two quick ideas each (the free part), what Workzap would build (the
bridge), where the free part stops, the one question to ask first, what never to say in that
industry and a sample reply. This module holds the build catalogue and its phrase bank, loads
those files and finds the entry that matches a noted problem. It never changes pi's rules: the
value line (R-VAL, R-BUILD) is enforced by the linter in constitution.py.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

SOLUTIONS_DIR = Path(__file__).parent / "packs" / "solutions"

# The build catalogue (Addendum 1 Part 7.2 is not in the repository, so it is taken from the phrase
# bank in Addendum 2 Part 1.9, which names every build Part 4 may use). Each build is said as what
# the owner would notice: who gets what, when, where. Roman Urdu is the owner's own register.
CATALOGUE: dict[str, dict[str, str]] = {
    "nori_daily_read": {
        "en": "Each morning, one short message: what changed yesterday and the one thing worth a look",
        "roman_ur": "Har subah ek chhota message: kal kya badla aur aaj kis cheez par nazar daalni hai",
    },
    "dashboards_reports": {
        "en": "Every branch's numbers on your phone each morning, without asking anyone",
        "roman_ur": "Har branch ka hisaab har subah aap ke phone par, kisi se pooche baghair",
    },
    "stock_alerts": {
        "en": "The shop manager gets a message the day a best-seller runs low",
        "roman_ur": "Jis din best-seller kam ho, usi din manager ko message",
    },
    "transfer_tracking": {
        "en": "Anything sent between shops that doesn't arrive gets flagged to you the same day",
        "roman_ur": "Ek dukaan se doosri bheja maal na pohnche to usi din aap ko pata chale",
    },
    "cash_reconciliation": {
        "en": "Each evening you'd see if cash and deposits match, shop by shop",
        "roman_ur": "Har shaam pata chale har dukaan ka cash aur jama shuda paisa barabar hai ya nahi",
    },
    "order_capture": {
        "en": "Every WhatsApp and phone order lands in one list, so none slip",
        "roman_ur": "Har WhatsApp aur phone order ek list mein, koi miss na ho",
    },
    "lead_followup": {
        "en": "Every enquiry gets a reply and a reminder, so none go cold",
        "roman_ur": "Har inquiry ka jawab jaye aur yaad-dahani bhi, koi thanda na pare",
    },
    "customer_messaging": {
        "en": "Past customers hear from you when new stock lands",
        "roman_ur": "Nayi collection aaye to purane customers ko message pohanch jaye",
    },
    "attribution_codes": {
        "en": "You'd know which ad brought which customer in",
        "roman_ur": "Pata chale kaunsa ad kaun sa customer laya",
    },
    "reviews_collection": {
        "en": "Happy customers get a polite request for a review after their visit",
        "roman_ur": "Khush customer ko visit ke baad review ke liye narmi se message",
    },
    "loyalty_repeat": {
        "en": "Regular customers are recognised and rewarded without anyone keeping a notebook",
        "roman_ur": "Pakke customers pehchane jayein aur unhein inaam mile, register ke baghair",
    },
    "booking_scheduling": {
        "en": "Customers book themselves and get a reminder the day before",
        "roman_ur": "Customer khud booking karein aur ek din pehle yaad-dahani mile",
    },
    "field_checks": {
        "en": "Staff send each check from their phone with a photo, and you see who did it",
        "roman_ur": "Staff har check phone se photo ke saath bhejein, aap ko pata chale kis ne kiya",
    },
    "workflow_automation": {
        "en": "Staff enter it once and it reaches everyone who needs it",
        "roman_ur": "Staff ek dafa likhein, baaki sab tak khud pohanch jaye",
    },
    "integration": {
        "en": "Your two tools share the data, so nobody types it twice",
        "roman_ur": "Dono cheezein aapas mein data share karein, koi do dafa na likhe",
    },
    "credit_ledger": {
        "en": "Each customer's balance is kept for you, and a polite reminder goes out on time",
        "roman_ur": "Har customer ka baqaya likha rahe aur waqt par narmi se yaad-dahani chali jaye",
    },
    "job_tracking": {
        "en": "Every job has a status that you and the customer can both check",
        "roman_ur": "Har kaam ka status: aap ko bhi pata, customer ko bhi",
    },
    "website_digital": {
        "en": "Customers can order or book online without calling",
        "roman_ur": "Customer bina call kiye online order ya booking kar sakein",
    },
    "erp_nori_platform": {
        "en": "Stock, sales, cash and staff in one place you can check from your phone",
        "roman_ur": "Stock, sale, cash aur staff ek jagah, phone se dekh sakein",
    },
    "custom_build": {
        "en": "Described specifically for their problem, in the same 'who gets what, when' style",
        "roman_ur": "Unke masle ke hisaab se, isi andaaz mein",
    },
}

# RBUILD02: a view leads only when the problem is about not seeing. Everything else does work.
VIEW_BUILDS = frozenset({"dashboards_reports", "nori_daily_read"})
ACTION_BUILDS = frozenset(set(CATALOGUE) - VIEW_BUILDS)

# Bridge openers (Addendum 2 Part 1.9): rotate, never repeat in one conversation.
BRIDGE_OPENERS: tuple[dict[str, str], ...] = (
    {
        "en": "To have this happen every day without anyone remembering, Workzap could set it up so",
        "roman_ur": "Ye roz bina yaad rakhe ho, is ke liye Workzap aisa intezam kar sakta hai ke",
    },
    {
        "en": "If doing it by hand gets heavy, Workzap could",
        "roman_ur": "Haath se karna mushkil ho to Workzap",
    },
    {
        "en": "The lasting fix would be",
        "roman_ur": "Is ka pakka hal ye ho sakta hai ke",
    },
    {
        "en": "For all your shops at once, Workzap could",
        "roman_ur": "Sab dukaanon ke liye ek saath, Workzap",
    },
    {
        "en": "What Workzap would build here is simple:",
        "roman_ur": "Workzap yahan seedha sa kaam kar sakta hai:",
    },
    {"en": "", "roman_ur": ""},  # no opener: just the "what they'd notice" sentence
)

# RBUILD01: words that name the tool, not what the owner would notice. They may be used only when
# the person used them first.
TOOL_WORDS = (
    "dashboard", "system", "software", "platform", "ERP", "module", "automation",
    "integration", "CRM", "portal", "analytics", "app",
)  # fmt: skip
TOOL_WORD = re.compile(r"\b(" + "|".join(TOOL_WORDS) + r")s?\b", re.IGNORECASE)
# "automatically" and "khud-ba-khud" at most once per conversation (RBUILD04)
AUTOMATIC = re.compile(
    r"\bautomatic(?:ally)?\b|\bkhud[- ]?ba[- ]?khud\b|\bapne aap\b", re.IGNORECASE
)


def banned_tool_words(text: str, said: str = "") -> list[str]:
    """The RBUILD01 tool words in `text` that the person has not used themselves."""
    heard = said.lower()
    found: list[str] = []
    for match in TOOL_WORD.finditer(text or ""):
        word = match.group(1).lower()
        if word not in found and not re.search(rf"\b{re.escape(word)}s?\b", heard):
            found.append(word)
    return found


def build_phrase(key: str, language: str = "en") -> str:
    """What the owner would notice for one catalogue build, in their language."""
    entry = CATALOGUE.get(key) or CATALOGUE["custom_build"]
    return entry["roman_ur" if language == "roman_ur" else "en"]


@dataclass(frozen=True)
class Idea:
    """One quick idea of one problem of one industry: the arm learning chooses between."""

    arm_id: str
    industry: str
    problem_id: str
    text: str


@lru_cache(maxsize=256)
def load(industry_key: str) -> dict[str, Any] | None:
    """The solutions of one industry, or None when it has none."""
    path = SOLUTIONS_DIR / f"{industry_key}.json"
    if not re.fullmatch(r"[a-z0-9_]+", industry_key or "") or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@lru_cache(maxsize=1)
def industries() -> tuple[str, ...]:
    return tuple(sorted(p.stem for p in SOLUTIONS_DIR.glob("*.json")))


def ideas(industry_key: str, problem: dict[str, Any]) -> list[Idea]:
    """The two quick ideas of a problem entry, each with its stable arm id."""
    return [
        Idea(f"{industry_key}:{problem['id']}:q{n}", industry_key, problem["id"], text)
        for n, text in enumerate(problem.get("quick_ideas") or [], start=1)
    ]


def never_say(industry_keys: list[str]) -> list[str]:
    """What must never be said in these industries (Part 2.2), for the prompt and the reviewers."""
    lines: list[str] = []
    for key in industry_keys:
        lines += (load(key) or {}).get("never_say", [])
    return lines
