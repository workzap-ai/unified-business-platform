"""PS-flow: put the L2-1 hard gate in the live brain-mode conversation path.

`requirements_context` turns what `requirements_read` read (once per turn) into plain data that
rides on the turn context; `requirements_from` rebuilds it. `gate_ideas` runs `option_gate` over the
candidate ideas that survived the idea filter and returns what the reply may show:

  * accepted ideas pass as they are;
  * `unknown` ideas are shown labelled "(not yet checked)", never as confirmed;
  * rejected ideas are dropped and named in a plain sentence with the owner's own limit;
  * nothing accepted and nothing unknown: ONE targeted question about the rule that rejected most,
    never a padded list.

Pure (no database, no model). Wording is English; the reply goes through the language step.
"""

from dataclasses import dataclass, field
from typing import Any

from app.modules.pi import constraint_check as cc
from app.modules.pi import option_gate
from app.modules.pi.requirements_types import (
    Constraints,
    Limit,
    ProblemRequirements,
    Requirements,
    TriedItem,
)

NOT_CHECKED = "(not yet checked against what you told me)"

ASK_ABOUT = {
    cc.RULE_BUDGET: "What is the most you can spend on this?",
    cc.RULE_CANNOT_CHANGE: "Which part of how you work could you change?",
    cc.RULE_TRIED: "What did you try before, and what happened?",
    cc.RULE_DEADLINE: "By when do you need this to start working?",
}
ASK_DEFAULT = "What would a workable fix look like for you?"


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


@dataclass
class Wired:
    shown: list[str] = field(default_factory=list)  # ideas to show, unknown ones labelled
    accepted: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    rejected: list[tuple[str, str, tuple[str, ...]]] = field(
        default_factory=list
    )  # idea, reason, evidence
    question: str = ""  # the one targeted question when nothing is left
    ask_about: str | None = None
    notice: str = ""  # one plain sentence on what was left out and why ("" when nothing was)

    @property
    def changed(self) -> bool:
        return bool(self.rejected or self.unknown or self.question)


def _because(rule: str, evidence: tuple[str, ...]) -> str:
    said = ", ".join(f'"{e}"' for e in evidence[:2] if e)
    if rule == cc.RULE_TRIED:
        return f"you already tried that ({said})" if said else "you already tried that"
    if rule == cc.RULE_BUDGET:
        return f"it goes past the budget you gave ({said})" if said else "it goes past your budget"
    if rule == cc.RULE_DEADLINE:
        return "it would take longer than the time you have"
    return (
        f"you said you cannot change this ({said})" if said else "you said you cannot change this"
    )


def gate_ideas(ideas: list[str], reqs: Requirements, language: str | None = None) -> Wired:
    """Never raises. With nothing stated and readable every idea is accepted unchanged."""
    result = option_gate.gate_options(list(ideas), reqs, language)
    wired = Wired(
        accepted=[g.option for g in result.accepted],
        unknown=[g.option for g in result.unknown],
        rejected=[(g.option, g.verdict.reason, g.verdict.evidence) for g in result.rejected],
        ask_about=result.ask_about,
    )
    # keep the model's order; an unknown idea is labelled, never shown as confirmed
    labelled = {g.option for g in result.unknown}
    for idea in ideas:
        if idea in labelled:
            wired.shown.append(f"{idea.rstrip('. ')} {NOT_CHECKED}")
        elif idea in wired.accepted:
            wired.shown.append(idea)
    if result.rejected:
        first = result.rejected[0]
        wired.notice = (
            "I left out an idea because "
            + _because(first.verdict.rule, first.verdict.evidence)
            + "."
        )
    if result.no_option_left:
        wired.question = ASK_ABOUT.get(result.ask_about or "", ASK_DEFAULT)
    return wired
