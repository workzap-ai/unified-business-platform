"""Scripted relevance scorer for candidate ideas (FT-A3). No model, deterministic.

Not a quality gate and not a learning reward; an offline measurement, connected to no live
gate. The 55% agreement (11 of 20) with an independent grader on the borderline set was measured
on the earlier scorer (exact tokens after crude stemming, no numbers, no negation). The current
scorer matches stemmed words, folds magnitude figures, compares numeric ceilings and reads modal
negation ('cannot buy X'); its current agreement with the agent-drafted labels is printed beside
this note. Negation inside an idea, spelled-out numbers and several languages are not
understood; limit keywords are fixture data.

Known limits, stated so nobody reads more into a verdict than it holds: matching is by stem
(`relevance_match`: English plural, -ing, -ed, -ly; Roman Urdu endings only when the case language
is `roman_ur`; ASCII stems are cut to five letters; Arabic loses a leading "ال"), so inflected
Urdu script, Hindi and Arabic forms still do not match and an irregular English form does not
either. Figures such as '3 lakh', '3,00,000' and '300000' are one token. A numeric ceiling in a
limit's text ('cannot spend more than 20000 rupees', 'up to 2 lakh') is compared as a number with
the idea's money figures; 'cannot buy X' and 'tried X before and it failed' texts are read as verb
plus object. Spelled-out numbers, floors ('at least'), negation inside an idea ("do not hire"
still looks like "hire") and verbs outside the listed groups are not understood.

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

from app.modules.pi.evalkit import access_log, scorers, splits
from app.modules.pi.evalkit import relevance_match as match

VERDICTS = ("relevant", "irrelevant", "generic", "violates_constraint", "restates_owner")
DISCLAIMER = (
    "Not a quality gate and not a learning reward; an offline measurement, connected to no live "
    "gate. The 55% agreement (11 of 20) with an independent grader on the borderline set was "
    "measured on the earlier scorer (exact tokens after crude stemming, no numbers, no negation). "
    "The current scorer matches stemmed words, folds magnitude figures, compares numeric ceilings "
    "and reads modal negation ('cannot buy X'); its current agreement with the agent-drafted "
    "labels is printed beside this note. Negation inside an idea, spelled-out numbers and "
    "several languages are not understood; limit keywords are fixture data."
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


# Numbers are standalone figures only: digits inside a word ('B2B', 'Q3', '24x7', 'order_1234')
# stay in it. Separators are read like this: Indian lakh grouping ('1,00,000', '20,00,000') and
# Western grouping ('20,000', '1,200,000') are one number each ('100000', '2000000', '20000',
# '1200000'); a list of 3-digit numbers ('120,150,180') stays three tokens,
# but one ending in 000 ('250,500,000') is one grouped figure; a single comma before
# one or two digits is a decimal comma ('1,5' becomes '1.5'); '1.5' stays; 'Rs.20000' gives 'rs'
# and '20000'. A token made only of zeros is never kept, so two lakh figures cannot link through
# '00000'.
_NUMBER = re.compile(
    r"(?<!\w)(?:"
    r"\d{1,2}(?:,\d{2})+,\d{3}(?:\.\d+)?"  # Indian: 1,00,000  20,00,000
    r"|\d{1,3}(?:,\d{3})+(?:\.\d+)?"  # Western: 20,000  1,200,000  (a list is split below)
    r"|\d+,\d{1,2}(?!\d)"  # decimal comma: 1,5
    r"|\d+(?:\.\d+)?"  # plain and decimal: 20000  1.5
    r")(?!\w)"
)


def _words(text: str) -> list[str]:
    return [t for t in _SPLIT.split(text) if t]


def _number_tokens(raw: str) -> list[str]:
    if "," not in raw:
        return [raw]
    whole, dot, fraction = raw.partition(".")
    groups = whole.split(",")
    if len(groups) == 2 and len(groups[1]) < 3:
        return [f"{groups[0]}.{groups[1]}"]  # a decimal comma
    is_list = len(groups[0]) == 3 and len(groups) >= 3 and groups[-1] != "000"
    if is_list:
        return [g for g in groups if g.strip("0")]  # '120,150,180' stays three numbers
    return ["".join(groups) + dot + fraction]


def tokens(text: str) -> list[str]:
    folded = (text or "").casefold()
    out: list[str] = []
    pos = 0
    for found in _NUMBER.finditer(folded):
        out += _words(folded[pos : found.start()])
        out += _number_tokens(found.group())
        pos = found.end()
    out += _words(folded[pos:])
    return [t for t in out if not (len(t) > 1 and t.isdigit() and not t.strip("0"))]


def _stem(token: str, language: str | None = None, full: bool = False) -> str:
    if any(ch.isdigit() for ch in token):
        return token  # a figure is never truncated: '20000' and '200000' stay distinct
    if token.isascii():
        whole = match.stem_ascii(token, language, full)
        return whole if full else whole[:5]
    if token.startswith("ال") and len(token) > 3:
        return token[2:]
    return token


def _keep(token: str) -> bool:
    if token in _STOP:
        return False
    if any(ch.isdigit() for ch in token):
        return True  # a figure ('20000') or a code ('b2b', 'q3', 'a4') is a fact an idea may reuse
    return len(token) >= (3 if token.isascii() else 2)


def stems(text: str, language: str | None = None, full: bool = False) -> set[str]:
    """Content stems. Magnitude figures are folded first ('3 lakh', '3,00,000' and '300000' are
    one token); English words lose plural, -ing, -ed and -ly, and with language 'roman_ur' the
    common Roman Urdu endings go too. The default (soft) stem of an ASCII word is cut to five
    letters and is used for overlap only; `full=True` keeps the whole stem and is the only space
    in which an idea is rejected (`violated`)."""
    return {_stem(t, language, full) for t in tokens(match.fold_magnitudes(text)) if _keep(t)}


def _full_stems(text: str, language: str | None) -> set[str]:
    """Full stems for matching a rule; verbs the stop list drops ('give', 'use', 'make') stay."""
    return {
        _stem(t, language, True)
        for t in tokens(match.fold_magnitudes(text))
        if _keep(t) or t in match.RULE_VERBS
    }


def _soft(token: str) -> str:
    return token if token.isdigit() or not token.isascii() else token[:5]


def _vocab(
    brief: dict[str, Any], problem: str | None, language: str | None = None
) -> tuple[set[str], set[str]]:
    """(the owner's own words about the problem, the other stated facts). The objects of a
    confirmed 'cannot VERB OBJECT' limit count as stated facts: the owner raised them."""
    problems = brief.get("problems") or []
    chosen = [p for p in problems if p.get("id") == problem] or problems
    owner: set[str] = set()
    facts: set[str] = set()
    for p in chosen:
        owner |= stems(" ".join([p.get("title", ""), *p.get("user_words", [])]), language)
        facts |= stems(" ".join([*p.get("facts", []), *p.get("figures", [])]), language)
        for limit in p.get("constraints") or []:
            if limit.get("status", "confirmed") == "confirmed":
                # the object of a confirmed 'cannot VERB OBJECT' limit is something the owner
                # stated, so an idea that reuses it ('rent a feed mill') reuses a stated fact
                for rule in match.parse_rules(str(limit.get("text", "")), language, _full_stems):
                    if rule.kind == "neg":
                        facts |= {_soft(o) for o in rule.objects}
    facts |= stems(" ".join([*brief.get("roles", []), *brief.get("systems", [])]), language)
    return owner, facts - owner


def _said_amounts(brief: dict[str, Any], owner_text: str) -> set[tuple[float, float, str]]:
    texts = [owner_text]
    for p in brief.get("problems") or []:
        texts += [p.get("title", ""), *p.get("user_words", []), *p.get("facts", [])]
        texts += list(p.get("figures", []))
    return match.said_amounts(texts)


def violated(
    brief: dict[str, Any],
    idea: set[str],
    language: str | None = None,
    text: str = "",
    owner_text: str = "",
) -> str | None:
    """The first CONFIRMED limit the idea breaks; an assumed limit never rejects an idea.

    A limit is broken by (1) one of its `blocks` phrases, unless the phrase is the object of the
    limit's own 'cannot VERB OBJECT' text and the idea uses a milder verb ('rent' against 'cannot
    buy'); (2) the verb group and object of a 'cannot VERB OBJECT' text; (3) the object of a
    'tried X before and it failed' text; (4) a figure above a numeric ceiling in the limit's text.
    All word matching here is in the full stem space of the idea's raw `text` (never the
    five-letter prefix); `idea`, the soft stems, is used only when no text is given."""
    full = _full_stems(text, language) if text else idea
    verbs = _full_stems(match.drop_noun_homographs(text), language) if text else idea
    said = _said_amounts(brief, owner_text)
    for problem in brief.get("problems") or []:
        for limit in problem.get("constraints") or []:
            if limit.get("status", "confirmed") != "confirmed":
                continue
            reason = str(limit.get("text", ""))
            rules = match.parse_rules(reason, language, _full_stems)
            if any(match.rule_hit(r, full, verbs) for r in rules):
                return reason
            for phrase in limit.get("blocks") or []:
                need = stems(
                    phrase, language, True
                )  # stop-list verbs ('give') are not required: as before
                if need and need <= full:
                    own = [
                        r for r in rules if match.rule_alternative(r, full) and need <= r.objects
                    ]
                    if not own:
                        return reason
            for ceiling in match.ceilings_of(reason, str(limit.get("kind", ""))):
                if match.over_ceiling(text, ceiling, said):
                    return reason
    return None


def _generic(language: str | None, idea: set[str]) -> bool:
    keys = [language] if language in _GENERIC else list(_GENERIC)
    return any(
        (need := stems(marker, language)) and need <= idea
        for key in keys
        for marker in _GENERIC[key]
    )


def score_candidate(
    brief: dict[str, Any],
    text: str,
    problem: str | None = None,
    owner_text: str = "",
    language: str | None = None,
) -> dict[str, Any]:
    idea = stems(text, language)
    owner, facts = _vocab(brief, problem, language)
    link = len(idea & owner)
    reuse = len(idea & facts)
    broken = violated(brief, idea, language, text, owner_text)
    said = owner | facts | stems(owner_text, language)
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


def score_case(
    case: dict[str, Any], *, held_out_ok: access_log.Pass | None = None
) -> dict[str, Any]:
    """Score one plan case. A Held-out case is refused at runtime unless the caller holds a
    `access_log.Pass`, which only `access_log.grant` mints after writing the access line; a plain
    True is not accepted."""
    if splits.split_of(case) == splits.HELD_OUT and not isinstance(held_out_ok, access_log.Pass):
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
