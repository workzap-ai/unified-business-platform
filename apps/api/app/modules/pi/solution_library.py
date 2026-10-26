# ruff: noqa: E501  (the cue lists read better on one line each)
"""The generic Solution Library (platform spec Book 2 Part 7.4, retrieval order in Book 3 Part 2.1).

When a person asks for a solution and the industry entries have nothing for the problem (no industry
known yet, a trade the entries do not name, a problem none of them covers), pi still gives two
ideas: those of the problem's category in this library. The ideas are the spec's own, kept only if
they pass pi's idea guard (scripts/build_generic_library.py), so no idea here is edited.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

LIBRARY = Path(__file__).parent / "packs" / "library" / "generic_library.json"
SAME_IDEA = 0.75  # word overlap at which an idea counts as already said


@lru_cache(maxsize=1)
def load() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(LIBRARY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dict(data.get("categories") or {})


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w{3,}", (text or "").lower()))


# Words that say which category a problem is in, in the owner's own words (English and Roman Urdu):
# a category is chosen by what they said, not only by the group the model filed the problem under
# ("staff" in a theft problem is not a scheduling problem, live test 4).
CUES: dict[str, str] = {
    "loss_security": "theft chori stolen steal thief fraud loss missing leak shrinkage void refund nuksan kam",
    "cash_collections": "cash owed udhaar credit payment collect receivable balance deposit paisa wusooli",
    "stock_inventory": "stock maal shelf expiry inventory count shortage low warehouse godown clearance",
    "sales_revenue": "sales price rate raqam views orders buy browse offer conversion silence reply sale",
    "marketing_leads": "ads instagram reels leads enquiry reach followers promotion campaign views",
    "customers_retention": "repeat review complaint regular return loyal feedback",
    "orders_fulfilment": "delivery order dispatch courier parcel rider shipping",
    "people_staff": "shift rota schedule attendance late training hire leave",
}


def best_category(noted: list[dict[str, Any]]) -> list[str]:
    """The library categories for the noted problems, best fit first: each problem's own words
    score against the cue words of every category (and the group the model filed it under counts a
    little). Only categories that have ideas are returned; the latest problem wins a tie."""
    from app.modules.pi.solution_ideas import _evidence

    have = load()
    scored: list[tuple[int, int, str]] = []
    for age, item in enumerate(reversed(noted)):
        said = _evidence(
            " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("title_local") or ""),
                    *[str(w) for w in item.get("user_words") or []],
                ]
            )
        )
        for category, cues in CUES.items():
            hits = len(said & _evidence(cues))
            prior = 1 if str(item.get("group") or "") == category else 0
            if (hits or prior) and have.get(category, {}).get("ideas"):
                scored.append((hits * 3 + prior, -age, category))
    ordered: list[str] = []
    for _score, _age, category in sorted(scored, reverse=True):
        if category not in ordered:
            ordered.append(category)
    for item in reversed(noted):  # whatever the model filed, as before, when no cue matched
        group = str(item.get("group") or "")
        if group not in ordered:
            ordered.append(group)
    return ordered


def already_said(idea: str, given: list[str]) -> bool:
    mine = _words(idea)
    return bool(mine) and any(len(mine & _words(g)) / len(mine) >= SAME_IDEA for g in given)


MODERN = Path(__file__).parent / "packs" / "library" / "modern_ideas.json"
MODERN_WEIGHT = 1  # a modern idea wins a tie with an older one; it never hides one


@lru_cache(maxsize=1)
def modern() -> dict[str, list[dict[str, str]]]:
    """The owner's modern ideas by library category (modern_ideas.json), each with a stable id."""
    try:
        data = json.loads(MODERN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, list[dict[str, str]]] = {}
    for item in data.get("ideas") or []:
        out.setdefault(str(item["category"]), []).append(item)
    return out


def idea_id(category: str, text: str) -> str:
    """The id learning scores an idea under: the modern idea's own, else one from its position."""
    for item in modern().get(category, []):
        if item["text"] == text:
            return item["id"]
    ideas = (load().get(category) or {}).get("ideas") or []
    return f"library:{category}:{ideas.index(text) + 1}" if text in ideas else f"library:{category}"


def ideas_for(
    category: str, given: list[str] | None = None, count: int = 2, said: str = ""
) -> list[str]:
    """Up to `count` ideas of the category not yet given. The ones that share the most evidence with
    the person's words come first (a modern idea before an older one on a tie), then the spec's
    order. Only ideas the reply rules would let pi say are used."""
    from app.modules.pi import solution_lint
    from app.modules.pi.solution_ideas import _evidence

    entry = load().get(category) or {}
    pool = [(item["text"], MODERN_WEIGHT) for item in modern().get(category, [])]
    pool += [(str(idea), 0) for idea in entry.get("ideas") or []]
    heard = _evidence(said)
    ranked = sorted(
        enumerate(pool),
        key=lambda pair: (-(len(heard & _evidence(pair[1][0])) + pair[1][1]), pair[0]),
    )
    taken = list(given or [])
    chosen: list[str] = []
    for _n, (idea, _weight) in ranked:
        if solution_lint.passes(idea) and not already_said(idea, taken + chosen):
            chosen.append(idea)
        if len(chosen) == count:
            break
    return chosen


def build_keys(category: str) -> list[str]:
    return [str(k) for k in (load().get(category) or {}).get("build_keys") or []]


def never_say(category: str) -> str:
    return str((load().get(category) or {}).get("never_say") or "")
