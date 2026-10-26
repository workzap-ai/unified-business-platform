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
WEIGHT = 1.0  # overlap evidence against the pack score, both scaled to their own best


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


def fuse(found: industry_packs.Detection, texts: list[str]) -> industry_packs.Detection:
    """`found` with its primary re-chosen from the pack scores plus the problem-word overlap, for a
    person who did not state their trade. The same text always gives the same answer (sorted
    iteration, ties broken by key). A stated trade, a confident pack score, or no evidence at all
    is left alone, and an existing primary is replaced only when the overlap clearly favours the new
    one."""
    if found.stated or (found.primary and found.confidence >= CLEAN):
        return found
    evidence = overlap(" ".join(texts))
    top = max(evidence.values(), default=0.0)
    if top <= 0:
        return found
    best_pack = max(found.scores.values(), default=0.0) or 1.0
    keys = sorted(set(evidence) | set(found.scores))

    def blended(key: str) -> float:
        return round(
            WEIGHT * evidence.get(key, 0.0) / top + found.scores.get(key, 0.0) / best_pack, 6
        )

    primary = max(keys, key=lambda k: (blended(k), k))
    if primary == found.primary:
        return found
    if found.primary and evidence.get(primary, 0.0) < OVERRIDE * evidence.get(found.primary, 0.0):
        return found  # the old primary is nearly as well supported: keep it
    industries = [primary, *[k for k in found.industries if k != primary]]
    scores = {**found.scores, primary: max(found.scores.get(primary, 0.0), FLOOR)}
    return replace(found, industries=industries[: industry_packs.MAX_PACKS], scores=scores)
