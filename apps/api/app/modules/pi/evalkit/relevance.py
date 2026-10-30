"""Scripted relevance scorer for candidate ideas (FT-A3). No model, deterministic.

Not a quality gate and not a learning reward. Scorer agreed 55% with an independent grader on
the borderline set; exact-token matching after crude stemming, no negation, no numbers, limit
keywords are fixture data.

Known limits, stated so nobody reads more into a verdict than it holds: words are matched as
exact tokens after a crude stem (ASCII tokens lose a plural "s" and are cut to five letters;
Arabic loses a leading "ال"), so inflected Urdu, Hindi and Arabic forms do not match; there is no
negation ("do not hire" and "hire" look alike); a numeric limit ("not above 20000") cannot be
expressed, and numbers are matched only as whole tokens ('20000' and '200000' stay distinct).

A plan case carries the owner's brief and candidate ideas with an expected verdict. For each
idea this module computes one of five verdicts from the text alone:

  violates_constraint  a CONFIRMED stated limit is broken (hard failure, whatever the link score)
  restates_owner       the idea only repeats what the owner said
  relevant             it links to the stated problem and reuses its facts
  generic              it would fit any business (no link, a generic phrase)
  irrelevant           specific, but unrelated to the stated problem

"No idea" is a valid result: `pick_ideas` returns only relevant ideas and never pads to a quota.
This is a scripted code-path check of the scorer and the case files. It is not a measure of how
well pi solves problems, and its agreement with a grader or with people is computed elsewhere
(`relevance_calibration`). Layer B plan fields (steps, dependencies, roles, next_action) are
ignored.

A stated limit is `{"kind", "text", "blocks": [phrases], "status": "confirmed" | "assumed"}`; only
confirmed limits reject an idea, an assumed one never does. The `blocks` phrases are fixture
data: the words an idea would use to break the limit.
"""

import re
from typing import Any

from app.modules.pi.evalkit import scorers, splits

VERDICTS = ("relevant", "irrelevant", "generic", "violates_constraint", "restates_owner")
DISCLAIMER = (
    "Not a quality gate and not a learning reward. Scorer agreed 55% with an independent grader "
    "on the borderline set; exact-token matching after crude stemming, no negation, no numbers, "
    "limit keywords are fixture data."
)
LINK_MIN = (
    2  # shared content words (problem plus facts) an idea needs, one of them from the problem
)
RESTATE_RATIO = 0.7  # share of an idea's words already said by the owner
RESTATE_MIN_WORDS = 3

_SPLIT = re.compile(r"[\s‌-‏⁠.,;:!?؟،۔।()\[\]{}\"'“”«»\-–—/\\|]+")
_STOP = {
    # English
    "the", "and", "for", "with", "that", "this", "from", "into", "your", "you", "our", "are",
    "was", "were", "will", "each", "every", "all", "any", "not", "but", "one", "per", "its",
    "they", "them", "their", "than", "then", "when", "what", "who", "how", "has", "have", "had",
    "can", "let", "get", "put", "give", "use", "make", "keep", "also", "only", "more", "most",
    # Roman Urdu
    "hai", "hain", "hota", "hoti", "hote", "kar", "karo", "kare", "karna", "karne", "kiya", "diya",
    "liye", "wala", "wale", "wali", "aur", "par", "mein", "men", "ka", "ki", "ke", "ko", "se",
    "jab", "tak", "pehle", "baad", "har", "ek", "hi", "bhi", "nahi", "nahin", "taake", "kyunke",
    "jaye", "jata", "jati", "raha", "rahi", "rahe", "hum", "humare", "hamare", "hamara", "aap",
    "tum", "yeh", "ye", "wo", "woh", "iss", "uss", "kuch", "bohat", "bahut", "kaun", "kya", "dena",
    # Urdu
    "کا", "کی", "کے", "کو", "سے", "میں", "پر", "اور", "ہے", "ہیں", "نہیں", "ایک", "ہر", "یہ",
    "وہ", "کہ", "تک", "بعد", "لیے", "ہو", "کر", "کریں", "کرے", "رہا", "رہی", "ہمارے", "ہمارا",
    # Arabic
    "في", "من", "على", "إلى", "عن", "مع", "كل", "هذا", "هذه", "ثم", "أو", "لا", "ما", "كان",
    "عندنا", "لدينا", "نحن",
    # Hindi
    "का", "की", "के", "को", "से", "में", "पर", "और", "है", "हैं", "नहीं", "एक", "हर", "वाली",
    "वाले", "ताकि", "यह", "वह", "हम", "हमारे", "हमारा", "भेजे", "करें", "करे",
}  # fmt: skip

_GENERIC = {
    "en": [
        "better software", "new technology", "use technology", "go digital",
        "improve your business",
        "grow your business", "best practices", "use ai", "social media", "marketing",
        "work smarter", "improve the clinic", "improve your farm",
    ],
    "roman_ur": [
        "behtar software", "naya software", "technology istemal", "business behtar",
        "business barhao", "marketing karo", "digital ho", "behtar tareeqa",
    ],
    "ur": ["بہتر سافٹ ویئر", "نئی ٹیکنالوجی", "کاروبار بہتر", "مارکیٹنگ", "ڈیجیٹل"],
    "ar": ["برنامج أفضل", "تكنولوجيا جديدة", "تحسين العمل", "التسويق", "تسويق", "رقمي"],
    "hi": ["बेहतर सॉफ्टवेयर", "नई तकनीक", "व्यापार बेहतर", "मार्केटिंग", "डिजिटल"],
}  # fmt: skip


# A number keeps its separators: '20,000' is the token '20000' and '1.5' stays '1.5', so a figure is
# never cut into pieces ('Rs.20000' gives 'rs' and '20000').
_NUMBER = re.compile(r"\d+(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def _words(text: str) -> list[str]:
    return [t for t in _SPLIT.split(text) if t]


def tokens(text: str) -> list[str]:
    folded = (text or "").casefold()
    out: list[str] = []
    pos = 0
    for found in _NUMBER.finditer(folded):
        out += _words(folded[pos : found.start()])
        out.append(found.group().replace(",", ""))
        pos = found.end()
    return out + _words(folded[pos:])


def _stem(token: str) -> str:
    if any(ch.isdigit() for ch in token):
        return token  # a figure is never truncated: '20000' and '200000' stay distinct
    if token.isascii():
        if token.endswith("s") and len(token) > 3:
            token = token[:-1]
        return token[:5]
    if token.startswith("ال") and len(token) > 3:
        return token[2:]
    return token


def _keep(token: str) -> bool:
    if token in _STOP:
        return False
    if token.isdigit():
        return True  # a figure is a fact an idea may reuse
    return len(token) >= (3 if token.isascii() else 2)


def stems(text: str) -> set[str]:
    return {_stem(t) for t in tokens(text) if _keep(t)}


def _vocab(brief: dict[str, Any], problem: str | None) -> tuple[set[str], set[str]]:
    """(the owner's own words about the problem, the other stated facts)."""
    problems = brief.get("problems") or []
    chosen = [p for p in problems if p.get("id") == problem] or problems
    owner: set[str] = set()
    facts: set[str] = set()
    for p in chosen:
        owner |= stems(" ".join([p.get("title", ""), *p.get("user_words", [])]))
        facts |= stems(" ".join([*p.get("facts", []), *p.get("figures", [])]))
    facts |= stems(" ".join([*brief.get("roles", []), *brief.get("systems", [])]))
    return owner, facts - owner


def violated(brief: dict[str, Any], idea: set[str]) -> str | None:
    """The first CONFIRMED limit the idea breaks; an assumed limit never rejects an idea."""
    for problem in brief.get("problems") or []:
        for limit in problem.get("constraints") or []:
            if limit.get("status", "confirmed") != "confirmed":
                continue
            for phrase in limit.get("blocks") or []:
                need = stems(phrase)
                if need and need <= idea:
                    return str(limit.get("text", ""))
    return None


def _generic(language: str | None, idea: set[str]) -> bool:
    banks = [_GENERIC[language]] if language in _GENERIC else list(_GENERIC.values())
    return any((need := stems(marker)) and need <= idea for bank in banks for marker in bank)


def score_candidate(
    brief: dict[str, Any],
    text: str,
    problem: str | None = None,
    owner_text: str = "",
    language: str | None = None,
) -> dict[str, Any]:
    idea = stems(text)
    owner, facts = _vocab(brief, problem)
    link = len(idea & owner)
    reuse = len(idea & facts)
    broken = violated(brief, idea)
    said = owner | facts | stems(owner_text)
    repeats = len(idea) >= RESTATE_MIN_WORDS and len(idea & said) / len(idea) >= RESTATE_RATIO
    if broken is not None:
        verdict = "violates_constraint"
    elif repeats:
        verdict = "restates_owner"
    elif link >= 1 and link + reuse >= LINK_MIN:
        verdict = "relevant"
    elif _generic(language, idea):
        verdict = "generic"
    else:
        verdict = "irrelevant"
    return {
        "verdict": verdict,
        "problem_link": link,
        "fact_reuse": reuse,
        "violated": broken,
        "restates": repeats,
    }


def pick_ideas(
    brief: dict[str, Any],
    texts: list[str],
    wanted: int | None = None,
    owner_text: str = "",
    language: str | None = None,
) -> list[str]:
    """The relevant ideas only. Never padded: with nothing relevant the answer is no idea."""
    good = [
        t
        for t in texts
        if score_candidate(brief, t, owner_text=owner_text, language=language)["verdict"]
        == "relevant"
    ]
    return good if wanted is None else good[:wanted]


def score_case(case: dict[str, Any], *, held_out_ok: bool = False) -> dict[str, Any]:
    """Score one plan case. A Held-out case is refused at runtime unless the caller says it has
    already logged the read (`held_out_ok`), as the report does after writing its access line."""
    if splits.split_of(case) == splits.HELD_OUT and not held_out_ok:
        raise PermissionError("scoring a Held-out case needs an access log: use the report")
    brief = case["input"]["brief"]
    owner_text = " ".join(case["input"].get("messages") or [])
    rows = []
    for cand in case["expected"]["candidates"]:
        got = score_candidate(
            brief,
            cand["text"],
            problem=cand.get("problem"),
            owner_text=owner_text,
            language=case.get("language"),
        )
        rows.append(
            {
                "id": cand["id"],
                "expected": cand["verdict"],
                "got": got["verdict"],
                "problem_link": got["problem_link"],
                "fact_reuse": got["fact_reuse"],
            }
        )
    return {
        "id": case["id"],
        "language": case.get("language", "en"),
        "industry": case["industry"],
        "kind": case.get("kind", "solution_relevance"),
        "candidates": len(rows),
        "agree": sum(1 for r in rows if r["expected"] == r["got"]),
        "false_relevant": sum(
            1 for r in rows if r["got"] == "relevant" and r["expected"] != "relevant"
        ),
        "missed_relevant": sum(
            1 for r in rows if r["expected"] == "relevant" and r["got"] != "relevant"
        ),
        "hard_misses": sum(
            1
            for r in rows
            if r["expected"] == "violates_constraint" and r["got"] != "violates_constraint"
        ),
        "results": rows,
    }


def aggregate(scores: list[dict[str, Any]]) -> dict[str, Any]:
    """Totals for a group of case scores; `measured` is False below the evalkit minimum."""
    n = len(scores)
    total = sum(s["candidates"] for s in scores)
    return {
        "cases": n,
        "measured": n >= scorers.MIN_CASES,
        "candidates": total,
        "accuracy": sum(s["agree"] for s in scores) / total if total else None,
        "false_relevant": sum(s["false_relevant"] for s in scores),
        "missed_relevant": sum(s["missed_relevant"] for s in scores),
        "hard_misses": sum(s["hard_misses"] for s in scores),
    }
