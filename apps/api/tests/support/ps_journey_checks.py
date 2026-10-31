"""Pure assertions for the PS-flow journeys (no database, no model, no network).

Shared by `tests/unit/test_pi_ps_flow_journey_checks.py` (checks over the fixture text) and
`tests/integration/ps_journey_harness.py` (the same checks over what the real pipeline stored and
sent). Every check reads behaviour (strings, statuses, counts), never an internal name that a lane
may still rename.
"""

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[1] / "fixtures" / "ps_flow_journeys.json"
LANGUAGES = ("en", "roman_ur", "ur", "ar")
DIFFICULTY = (
    "connected",  # one cause drives two symptoms
    "conflict",  # budget vs deadline, staff cap vs a hire idea
    "missing_info",  # budget or staff never said
    "corrections",  # a figure corrected twice, a cause replaced
    "generic",  # an unrelated, generic idea that must not be recommended
    "reworded",  # a valid idea in other words than the owner's
    "violating",  # an idea that breaks a stated limit
    "unknown_limit",  # a limit the check cannot read: shown unknown, never satisfied
    "one_question",  # incomplete information: ONE targeted question
    "rerank",  # a recommendation rejected, then a changed requirement
    "approval",  # the exact scope is approved; vague replies are not
)
STAGES = (
    "problem",
    "corrections",
    "saved_facts",
    "root_causes",
    "ideas",
    "constraint_checks",
    "ranking",
    "blueprint",
    "approval",
)


def load(path: Path = FIXTURE) -> list[dict[str, Any]]:
    return list(json.loads(path.read_text("utf-8")))


# --- text ------------------------------------------------------------------------------------

_DIGITS = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_DIGITS.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})
_ARABIC = re.compile(r"[؀-ۿ]")
_URDU_ONLY = re.compile(r"[ٹڈڑںھہےکگپچژۓ]")
_LATIN = re.compile(r"[A-Za-z]")
_ROMAN_UR = re.compile(
    r"\b(?:aap|aapka|aapki|hai|hain|nahi|kya|kab|kitna|kitne|kaise|mein|se|ko|ka|ki|ke|"
    r"yeh|woh|kar|karein|karna|shukriya|masla|ek|aur|hum|mujhe|mera|meri|bhi|toh|lekin|"
    r"phir|abhi|ab|kuch|sab|raha|rahi|hota|hoti|hote|chahiye|zaroor|theek)\b",
    re.IGNORECASE,
)
_BRAND = re.compile(r"\b(?:pi|AI|Workzap|WhatsApp)\b")


def digits(text: str) -> str:
    """Eastern Arabic and Persian digits as ASCII, so a figure compares in any script."""
    return unicodedata.normalize("NFKC", text or "").translate(_DIGITS)


def has_figure(text: str, figure: str) -> bool:
    """The figure as a whole number in the text ('60' is not in '160' or '6.0' or '600')."""
    pattern = rf"(?<![0-9A-Za-z_,.-]){re.escape(digits(figure))}(?![0-9A-Za-z_]|[.,]\d)"
    return re.search(pattern, digits(text)) is not None


def figure_context(text: str, figure: str, width: int = 50) -> str:
    """A few words around the first place the figure stands (for a failure message)."""
    flat = digits(text)
    found = re.search(
        rf"(?<![0-9A-Za-z_,.-]){re.escape(digits(figure))}(?![0-9A-Za-z_]|[.,]\d)", flat
    )
    if not found:
        return ""
    return flat[max(0, found.start() - width) : found.end() + width]


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?؟۔])\s+|\n+", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def question_marks(text: str) -> int:
    return len(re.findall(r"[?؟]", text or ""))


def one_question_last(text: str) -> bool:
    """At most one question mark, and when there is one it ends the last sentence."""
    count = question_marks(text)
    if count == 0:
        return True
    if count > 1:
        return False
    last = sentences(text)[-1] if sentences(text) else ""
    return last.rstrip().endswith(("?", "؟"))


def detect_language(text: str) -> str:
    """en, roman_ur, ur or ar from the script and a short Roman Urdu word list. Brand words
    (pi, AI, Workzap, WhatsApp) are ignored."""
    body = _BRAND.sub(" ", text or "")
    arabic = len(_ARABIC.findall(body))
    latin = len(_LATIN.findall(body))
    if arabic > latin:
        return "ur" if _URDU_ONLY.search(body) else "ar"
    if _ROMAN_UR.search(body):
        hits = len(_ROMAN_UR.findall(body))
        words = max(1, len(re.findall(r"[A-Za-z']+", body)))
        if hits / words >= 0.12:
            return "roman_ur"
    return "en"


def language_matches(expected: str, text: str) -> bool:
    return detect_language(text) == expected


def american_spelling(text: str) -> list[str]:
    """American spellings of the production list (R-VOICE-14), for English replies."""
    from app.modules.pi import constitution

    return [m.group(0) for m in constitution.AMERICAN.finditer(text or "")]


def money_or_promise(text: str) -> list[str]:
    """A price, a saving or a promised result in pi's own words (never the owner's quoted ones)."""
    from app.modules.pi import blueprint_text as bt

    found: list[str] = []
    if bt.money_in(text):
        found.append("money")
    if bt.promise_in(text):
        found.append("promise")
    return found


_NORMAL = re.compile(r"[^\w؀-ۿ ]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _NORMAL.sub(" ", (text or "").casefold()).split() if len(t) > 1}


def last_question(text: str) -> str:
    for s in reversed(sentences(text)):
        if s.endswith(("?", "؟")):
            return s
    return ""


def repeated_questions(replies: list[str], threshold: float = 0.8) -> list[tuple[int, int]]:
    """Pairs of reply positions whose question is the same (token overlap above the threshold)."""
    asked = [(i, _tokens(last_question(r))) for i, r in enumerate(replies)]
    found = []
    for a in range(len(asked)):
        for b in range(a + 1, len(asked)):
            x, y = asked[a][1], asked[b][1]
            if x and y and len(x & y) / len(x | y) >= threshold:
                found.append((asked[a][0], asked[b][0]))
    return found


# --- the fixture itself ----------------------------------------------------------------------


def owner_texts(journey: dict[str, Any]) -> list[str]:
    return [t["owner"] for t in journey["turns"]]


def pi_replies(journey: dict[str, Any]) -> list[str]:
    return [t["pi"] for t in journey["turns"] if t.get("pi")]


def asked_again(journey: dict[str, Any]) -> list[tuple[int, str]]:
    """Replies that ask for a slot the owner had already said in an earlier turn (turn index,
    slot). The fixture says which slot a reply asks (`asks`) and in which turn each slot was said
    (`said`), so the check is about order, not about the wording of the question."""
    said = journey.get("said") or {}
    bad = []
    for n, turn in enumerate(journey["turns"]):
        slot = turn.get("asks")
        if slot and slot in said and said[slot] <= n:
            bad.append((n, slot))
    return bad


def figures_after_corrections(journey: dict[str, Any]) -> tuple[list[str], list[str]]:
    expect = journey["expect"]
    return list(expect.get("kept") or []), list(expect.get("gone") or [])


def covered(journey: dict[str, Any]) -> set[str]:
    """The difficulty types a journey declares (the suite needs each at least three times)."""
    return set(journey.get("difficulty") or [])
