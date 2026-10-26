# ruff: noqa: E501
"""The trade from the owner's own problem words (a signal for owners who tell problems, not a trade).

Most owners say what they do; some only say what goes wrong ("the carpenters take timber on credit
and do not pay"). The industry packs name the trade by its words, which a problem told in other
words never hits. Each industry's solution entries carry the words owners use for that trade's
problems, so the owner's text is also matched against those, weighted by how rare each word is among
the industries, and that evidence is added to the pack score. It is used only when the person did not
state their trade; a stated trade keeps the pack score alone.
"""

import math
import re
from collections import Counter
from dataclasses import replace
from functools import lru_cache

from app.modules.pi import industry_packs, solutions

STOP = frozenset(
    "the and for with from are was were been our your this that they them their have has had does did"
    " not can could would should will shall just very but about into than then there here what which"
    " who how when where why all any some more most much many also only own such ke ki ka ko se mein"
    " hai hain hua hui aur ya ye wo bhi nahi nhi koi kuch sab har par kar kya".split()
)
FLOOR = 7.3  # a pack score worth a confidence of about 0.6
CLEAN = 0.85  # a pack score this confident is never overridden
OVERRIDE = 1.3  # the overlap for a new primary against the old one, to replace it
NAME_BONUS = 0.3  # a word of the industry's own name was used
KEEP_BONUS = 0.4  # the industry already stored for this business
MIN_EVIDENCE = 1.1  # the best overlap needed before the problem words decide anything
WEAK = 0.75  # below this confidence the pack score is a hunch, not a finding
WEIGHT = 1.0
WEIGHT_BLIND = 3.0  # the same, when the pack scores found no trade at all  # overlap evidence against the pack score, both scaled to their own best


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z]{3,}", industry_packs._fold(text))
    return {industry_packs._stem(w) for w in words if w not in STOP}


@lru_cache(maxsize=1)
def _entries() -> tuple[dict[str, list[set[str]]], dict[str, float]]:
    packs: dict[str, list[set[str]]] = {}
    for key in solutions.industries():
        entry = solutions.load(key) or {}
        packs[key] = [
            _tokens(f"{p.get('words', '')} {str(p.get('subtype', '')).replace('_', ' ')}")
            for p in entry.get("problems") or []
        ]
    frequency: Counter[str] = Counter()
    for entries in packs.values():
        for word in set().union(*entries) if entries else set():
            frequency[word] += 1
    total = max(len(packs), 1)
    return packs, {w: math.log(1 + total / n) for w, n in frequency.items()}


def overlap(text: str) -> dict[str, float]:
    """industry key -> how much of the best-matching problem entry's rare words the text uses."""
    packs, weight = _entries()
    asked = _tokens(text)
    scores: dict[str, float] = {}
    for key in sorted(packs):
        best = 0.0
        for words in packs[key]:
            shared = asked & words
            if shared:
                total = sum(weight[w] for w in sorted(words)) ** 0.5 or 1.0
                best = max(best, sum(weight[w] for w in sorted(shared)) / total)
        scores[key] = round(best, 6)
    return scores


@lru_cache(maxsize=1)
def _names() -> dict[str, set[str]]:
    """industry key -> the words of its own name (all of them, even the ones shared with sibling
    trades such as "clinic": here they only add to the problem-word evidence)."""
    names: dict[str, set[str]] = {}
    for key in solutions.industries():
        entry = solutions.load(key) or {}
        plain = re.sub(r"\([^)]*\)", " ", str(entry.get("name") or key.replace("_", " ")))
        names[key] = {w for w in _tokens(plain) if len(w) >= 4}
    return names


def name_hits(text: str) -> dict[str, int]:
    asked = _tokens(text)
    return {key: len(asked & words) for key, words in sorted(_names().items()) if asked & words}


def fuse(
    found: industry_packs.Detection, texts: list[str], known: tuple[str, ...] = ()
) -> industry_packs.Detection:
    """`found` with its primary re-chosen from the pack scores plus the problem-word overlap and
    the trade words the person used, for a person who did not state their trade. The same text
    always gives the same answer (sorted iteration, ties broken by key). A stated trade, a
    confident pack score, or no evidence at all is left alone; each message counts on its own, so
    a generic reply ("it happens every week") cannot dilute the one that named the problem; an
    industry already stored is kept unless another is clearly better supported."""
    if found.stated or (found.primary and found.confidence >= CLEAN):
        return found
    evidence: dict[str, float] = {}
    for text in texts:
        for key, value in overlap(text).items():
            evidence[key] = max(evidence.get(key, 0.0), value)
    hits: dict[str, int] = {}
    for text in texts:
        for key, value in name_hits(text).items():
            hits[key] = max(hits.get(key, 0), value)
    top = max(evidence.values(), default=0.0)
    if top < MIN_EVIDENCE:
        return found  # a few shared common words are no evidence of a trade
    best_pack = max(found.scores.values(), default=0.0) or 1.0
    # with no pack score at all the person's problem words are all there is to go on
    weight = WEIGHT_BLIND if not found.primary or found.confidence < WEAK else WEIGHT
    keys = sorted(set(evidence) | set(found.scores) | set(hits))

    def blended(key: str) -> float:
        named = NAME_BONUS if hits.get(key) else 0.0
        stored = KEEP_BONUS if key in known else 0.0
        return round(
            weight * evidence.get(key, 0.0) / top
            + found.scores.get(key, 0.0) / best_pack
            + named
            + stored,
            6,
        )

    primary = max(keys, key=lambda k: (blended(k), k))
    if primary == found.primary:
        return found
    if found.primary and evidence.get(primary, 0.0) < OVERRIDE * evidence.get(found.primary, 0.0):
        return found  # the old primary is nearly as well supported: keep it
    industries = [primary, *[k for k in found.industries if k != primary]]
    scores = {**found.scores, primary: max(found.scores.get(primary, 0.0), FLOOR)}
    return replace(found, industries=industries[: industry_packs.MAX_PACKS], scores=scores)
