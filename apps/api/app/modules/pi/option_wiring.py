"""PS-flow: the owner's stated requirements on the brain-mode turn context.

`requirements_context` turns what `requirements_read` read (once per turn) into plain data that
rides on the turn context; `requirements_from` rebuilds it. The gate itself runs in
`option_voice.voice` (one verdict path with PS-3 relevance). Pure: no database, no model.
"""

from typing import Any

from app.modules.pi.requirements_types import (
    Constraints,
    Limit,
    ProblemRequirements,
    Requirements,
    TriedItem,
)


def requirements_context(reqs: Requirements) -> dict[str, Any]:
    """Plain data for the turn context. Empty when the owner stated nothing and it was readable."""
    if reqs.columns_available and reqs.empty:
        return {}
    return {
        "columns_available": reqs.columns_available,
        "budget": [x.text for x in reqs.budgets],
        "staff": [x.text for x in reqs.staff],
        "deadline": [x.text for x in reqs.deadlines],
        "cannot_change": [x.text for x in reqs.cannot_change],
        "tried": [{"what": t.what, "outcome": t.outcome} for t in reqs.tried],
    }


def requirements_from(data: Any) -> Requirements:
    """Rebuild from `requirements_context`. No data means nothing stated and readable."""
    if not isinstance(data, dict) or not data:
        return Requirements()

    def one(key: str) -> Limit | None:
        items = [str(x) for x in data.get(key) or [] if str(x).strip()]
        return Limit(items[0]) if items else None

    constraints = Constraints(
        budget=one("budget"),
        staff=one("staff"),
        deadline=one("deadline"),
        cannot_change=tuple(
            Limit(str(x)) for x in data.get("cannot_change") or [] if str(x).strip()
        ),
    )
    tried = tuple(
        TriedItem(str(t.get("what") or ""), str(t.get("outcome") or ""))
        for t in data.get("tried") or []
        if isinstance(t, dict) and str(t.get("what") or "").strip()
    )
    problem = ProblemRequirements(constraints=constraints, tried=tried)
    return Requirements(
        problems=(problem,), columns_available=bool(data.get("columns_available", True))
    )
