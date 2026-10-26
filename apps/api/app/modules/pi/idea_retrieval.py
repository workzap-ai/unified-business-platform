"""Retrieval by problem and goal, not by words (platform spec Book 5, 7.3).

Query key: (industry, sub-type, goal verb, known cause). The industry is the entries' own file;
this module ranks the entries of that industry by how much of the rest of the key they match.
Words are only a tiebreak (the caller's word `fit` decides between equal keys). When the sub-type,
goal verb and cause are all unknown, or no entry matches the sub-type, every rank is 0 and the
caller keeps the behaviour it had before: the closest entry by words.

Pure functions."""

from typing import Any

from app.modules.pi import idea_filter, solution_ideas, taxonomy

SUBTYPE_POINTS = 4
GOAL_POINTS = 2
CAUSE_POINTS = 1


def target_subtype(subtype: str, goal_text: str) -> tuple[str, str]:
    """(sub-type, goal verb) the problem is sorted as: the goal verb's sort overrides the model's
    own guess (spec 7.2), else the sub-type the model gave."""
    sort = taxonomy.goal_sort(goal_text)
    if sort is not None:
        return sort.subtype, sort.goal_verb
    return subtype, ""


def key_rank(entry: dict[str, Any], subtype: str, goal_verb: str, cause: str) -> int:
    """How much of the query key the entry matches (0 when nothing of it is known or matches)."""
    cause_words = idea_filter.causes_in(cause)
    if not subtype or entry.get("subtype") != subtype:
        return 0
    if not goal_verb and not cause_words:
        return 0  # the model's own sub-type guess alone is no key: words decide, as before
    rank = SUBTYPE_POINTS
    if goal_verb:
        rank += GOAL_POINTS  # the sub-type was reached through the goal verb's sort
    if cause_words:
        text = " ".join(
            [
                str(entry.get("words") or ""),
                *[str(i) for i in entry.get("quick_ideas") or []],
                *[str(e.get("text") or "") for e in entry.get("extra_ideas") or []],
            ]
        )
        if cause_words & idea_filter.causes_in(text) or (
            solution_ideas._evidence(cause) & solution_ideas._evidence(text) - solution_ideas.WEAK
        ):
            rank += CAUSE_POINTS
    return rank


def preferred_entry(
    entries: list[dict[str, Any]], subtype: str, goal_text: str, cause: str, category: str = ""
) -> tuple[dict[str, Any], int] | None:
    """The entry of the problem's sub-type (and category, when given) that best matches the goal
    verb and the cause, with its rank; None when the sub-type is unknown or no entry has it (the
    caller then falls back as before, never to a nearby sub-type through this path)."""
    target, goal_verb = target_subtype(subtype, goal_text)
    if not target:
        return None
    best: tuple[dict[str, Any], int] | None = None
    for entry in entries:
        if category and entry.get("category") not in (category, "") and not goal_verb:
            continue
        rank = key_rank(entry, target, goal_verb, cause)
        if rank and (best is None or rank > best[1]):
            best = (entry, rank)
    return best
