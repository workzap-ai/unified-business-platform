"""L2-3: pure validators and the ranking for an options record (design: docs/pi-saas/
pi-solution-blueprint-design.md section 3.4 and 4; records in `blueprint_models`).

No database, no model, no owner-facing wording. Every function returns data: a list of `Issue`s
(empty means the record passes) or an ordered tuple. Nothing here is wired into the conversation or
the document yet; a later step calls it before any option is shown.

Rules (codes are stable; each has a test that fails when the rule is removed):

  OPT-ADDR        every option links to at least one stated problem id, and only known ones
  OPT-MONEY       no money in any text pi wrote (what, benefit, limits, trade-offs, risks,
                  dependencies, check reasons, rejection reason)
  OPT-COST        the cost source is staff and the amount is never filled by pi
  OPT-PROMISE     no promised result (the constitution's promise rule, and "will" without "not")
  OPT-CATALOGUE   a build or custom automation names its catalogue key
  OPT-ENUM        kind, effort, reversibility, status, check result, dependency kind, risk level
                  are from their lists
  OPT-REJECT      a rejected option names why, and only a rejected option has a reason
  OPT-RECOMMEND   a recommended option has no violated constraint, no blocking dependency and
                  evidence (a learn_first option needs none)
  OPT-CHECKS      every stated constraint has a check, even when the result is "unknown"
  OPT-CAUSE-FACT  a cause pi only inferred is never worded as a fact
  OPT-EVIDENCE    evidence words are whole words of the owner's own message
  SET-COUNT       two options are compared, unless the evidence supports only one (flagged)
  SET-SINGLE      the single-option flag is honest: only with one option, and with its reason
  SET-EMPTY       an empty set says why
  SET-RECOMMENDED one recommendation at most, and it is the first of the ranking
  SET-THIN        thin evidence needs a learn_first option
  CAUSE-STATUS    a cause status is from the list
  CAUSE-UNSUPPORTED  an owner_said or confirmed cause has the owner's own words as proof
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from app.modules.pi import blueprint_models as bm
from app.modules.pi import problem_fields as pf
from app.modules.pi.constitution import PROMISE

# A copy of `brain_docs.MONEY_IN_TEXT` (brain_docs.py:60), kept here because importing brain_docs
# pulls the database layer into a pure module and would make a cycle once brain_docs calls these
# rules. A unit test asserts the two patterns are identical.
MONEY_IN_TEXT = re.compile(
    r"\b(?:rs\.?|pkr|aed|cad|usd|dirhams?|rupees?|lakhs?|crores?)\b|[$€£₹]"
    r"|\b\d{1,3}(?:,\d{2,3})+(?:\.\d+)?\b"
    r"|\b\d+(?:\.\d+)?\s?(?:k|m|lakh|lac|crore|million|thousand)\b"
    r"|\b(?:cost|costs|price|priced|fee|fees|charge|charged|budget|pay|paying)\b\D{0,15}\d{3,}",
    re.IGNORECASE,
)
# A copy of `brain_docs.WILL` (brain_docs.py:69): option text says "would", not "will".
WILL = re.compile(r"\bwill\b(?! not)", re.IGNORECASE)
# Words that label a statement as a guess ("if", "may", "could", "shayad", ...).
HEDGE = re.compile(
    r"\b(?:if|may|might|could|possibly|perhaps|maybe|assuming|shayad|agar|ho sakta|ho sakti)\b",
    re.IGNORECASE,
)

RULE_CODES = (
    "OPT-ADDR",
    "OPT-MONEY",
    "OPT-COST",
    "OPT-PROMISE",
    "OPT-CATALOGUE",
    "OPT-ENUM",
    "OPT-REJECT",
    "OPT-RECOMMEND",
    "OPT-CHECKS",
    "OPT-CAUSE-FACT",
    "OPT-EVIDENCE",
    "SET-COUNT",
    "SET-SINGLE",
    "SET-EMPTY",
    "SET-RECOMMENDED",
    "SET-THIN",
    "CAUSE-STATUS",
    "CAUSE-UNSUPPORTED",
)


@dataclass(frozen=True)
class Issue:
    code: str
    option_id: str = ""
    detail: str = ""


@dataclass(frozen=True)
class _Ctx:
    problem_ids: frozenset[str]
    owner_text: str | None
    view: bm.ConstraintsView | None
    cause: bm.RootCause | None


# --- what pi wrote -------------------------------------------------------------------------------


def _own_texts(option: bm.Option) -> list[str]:
    """Every text pi wrote for an option. `expected_outcome` is the owner's own words and is not
    pi's claim, so it is left out."""
    texts = [option.what, option.benefit, option.rejected_because]
    texts += [*option.limits, *option.trade_offs]
    texts += [r.text for r in option.risks] + [d.text for d in option.dependencies]
    texts += [c.why for c in option.constraint_checks]
    return [t for t in texts if t]


def _claims(option: bm.Option) -> list[str]:
    """The texts that describe what the option is or does (not the check reasons)."""
    texts = [option.what, option.benefit, *option.limits, *option.trade_offs]
    return [t for t in texts if t]


# --- recommendable and ranking -------------------------------------------------------------------


def _blockers(option: bm.Option) -> list[str]:
    """Why an option cannot be the recommendation, from the record and nothing else."""
    out: list[str] = []
    if option.violated:
        out.append("violates")
    if option.blocking_dependencies:
        out.append("blocked")
    if option.kind in bm.BUILD_KINDS and not option.catalogue_key:
        out.append("no catalogue key")
    if option.kind != bm.LEARN_FIRST and option.evidence_strength == 0:
        out.append("no evidence")
    return out


def recommendable(option: bm.Option) -> bool:
    """Derived from code facts, never from the model's confidence."""
    return option.status != "rejected" and not _blockers(option)


def evidence_thin(options: Iterable[bm.Option]) -> bool:
    """True when no option other than learn_first has any owner evidence behind it (a rejected or
    violating option does not count): the honest first step is to learn, not to build."""
    return not any(
        o.evidence_strength >= 1
        for o in options
        if o.kind != bm.LEARN_FIRST and o.status != "rejected" and not o.violated
    )


def _effort_rank(option: bm.Option) -> int:
    return bm.EFFORTS.index(option.effort) if option.effort in bm.EFFORTS else len(bm.EFFORTS)


def _reversibility_rank(option: bm.Option) -> int:
    values = bm.REVERSIBILITY
    return values.index(option.reversibility) if option.reversibility in values else len(values)


def _unknown_flag(option: bm.Option) -> int:
    return 1 if option.unknown_checks else 0


def _tier(option: bm.Option, thin: bool) -> int:
    """0 learn_first while the evidence is thin; 1 reliable options; 2 learn_first when the evidence
    is strong; 3 visible but not recommendable (blocked, no evidence, no catalogue key); 4 violates
    a stated constraint; 5 rejected."""
    if option.status == "rejected":
        return 5
    if option.violated:
        return 4
    if _blockers(option):
        return 3
    if option.kind == bm.LEARN_FIRST:
        return 0 if thin else 2
    return 1


def rank_options(options: Iterable[bm.Option]) -> tuple[bm.Option, ...]:
    """The options in the order they are offered: smallest reliable first. Deterministic.

    Order, first rule that differs wins:
      1. tier: learn_first first only while the evidence is thin; then reliable options; then
         learn_first when the evidence is strong; then options that are visible but cannot be
         recommended (blocked, no evidence, no catalogue key); then options that violate a stated
         constraint; then rejected ones. A violation is never rescued by a good score.
      2. within a tier: no unknown constraint check before an unknown one (an unchecked option is
         not "reliable"; the reviewer sees it flagged);
      3. effort class, smallest first (none, small, medium, large);
      4. reversibility, easiest to undo first (reversible, partly, hard);
      5. evidence strength, strongest first (distinct owner messages behind it, capped);
      6. id, so ties never depend on input order.
    """
    items = tuple(options)
    thin = evidence_thin(items)
    return tuple(
        sorted(
            items,
            key=lambda o: (
                _tier(o, thin),
                _unknown_flag(o),
                _effort_rank(o),
                _reversibility_rank(o),
                -o.evidence_strength,
                o.id,
            ),
        )
    )


# --- option rules --------------------------------------------------------------------------------


def _rule_addr(option: bm.Option, ctx: _Ctx) -> list[Issue]:
    if not option.addresses:
        return [Issue("OPT-ADDR", option.id, "links to no problem")]
    unknown = [p for p in option.addresses if p not in ctx.problem_ids]
    return [Issue("OPT-ADDR", option.id, f"unknown problem {p}") for p in unknown]


def _rule_money(option: bm.Option, ctx: _Ctx) -> list[Issue]:
    return [
        Issue("OPT-MONEY", option.id, text[:60])
        for text in _own_texts(option)
        if MONEY_IN_TEXT.search(text)
    ]


def _rule_cost(option: bm.Option, ctx: _Ctx) -> list[Issue]:
    if option.cost.amount is not None or option.cost.source != bm.COST_SOURCE:
        return [Issue("OPT-COST", option.id, "the cost is staff's, never filled by pi")]
    return []


def _rule_promise(option: bm.Option, ctx: _Ctx) -> list[Issue]:
    return [
        Issue("OPT-PROMISE", option.id, text[:60])
        for text in _claims(option)
        if PROMISE.search(text) or WILL.search(text)
    ]


def _rule_catalogue(option: bm.Option, ctx: _Ctx) -> list[Issue]:
    if option.kind in bm.BUILD_KINDS and not option.catalogue_key:
        return [Issue("OPT-CATALOGUE", option.id, "a build names its catalogue key")]
    return []


def _rule_enum(option: bm.Option, ctx: _Ctx) -> list[Issue]:
    pairs: list[tuple[str, str, tuple[str, ...]]] = [
        ("kind", option.kind, bm.KINDS),
        ("effort", option.effort, bm.EFFORTS),
        ("reversibility", option.reversibility, bm.REVERSIBILITY),
        ("status", option.status, bm.STATUSES),
    ]
    pairs += [("check", c.result, bm.CHECK_RESULTS) for c in option.constraint_checks]
    pairs += [("dependency", d.kind, bm.DEPENDENCY_KINDS) for d in option.dependencies]
    pairs += [("risk", r.level, bm.RISK_LEVELS) for r in option.risks]
    return [
        Issue("OPT-ENUM", option.id, f"{name}: {value}")
        for name, value, allowed in pairs
        if value not in allowed
    ]


def _rule_reject(option: bm.Option, ctx: _Ctx) -> list[Issue]:
    if option.status == "rejected" and not option.rejected_because.strip():
        return [Issue("OPT-REJECT", option.id, "a rejected option names why")]
    if option.status != "rejected" and option.rejected_because.strip():
        return [Issue("OPT-REJECT", option.id, "only a rejected option has a rejection reason")]
    return []


def _rule_recommend(option: bm.Option, ctx: _Ctx) -> list[Issue]:
    if option.status != "recommended":
        return []
    return [Issue("OPT-RECOMMEND", option.id, why) for why in _blockers(option)]


def _rule_checks(option: bm.Option, ctx: _Ctx) -> list[Issue]:
    if ctx.view is None:
        return []
    checked = {c.constraint for c in option.constraint_checks}
    return [
        Issue("OPT-CHECKS", option.id, label) for label in ctx.view.labels() if label not in checked
    ]


def _rule_cause_fact(option: bm.Option, ctx: _Ctx) -> list[Issue]:
    cause = ctx.cause
    if cause is None or cause.stateable or not cause.text.strip():
        return []
    needle = " ".join(cause.text.casefold().split())
    return [
        Issue("OPT-CAUSE-FACT", option.id, "a guessed cause is worded as a fact")
        for text in _claims(option)
        if needle in " ".join(text.casefold().split()) and not HEDGE.search(text)
    ]


def _rule_evidence(option: bm.Option, ctx: _Ctx) -> list[Issue]:
    if ctx.owner_text is None:
        return []
    return [
        Issue("OPT-EVIDENCE", option.id, ref.msg)
        for ref in option.evidence
        if not (ref.words and pf.said_by_owner(list(ref.words), ctx.owner_text))
    ]


_OPTION_RULES: tuple[str, ...] = (
    "_rule_addr",
    "_rule_money",
    "_rule_cost",
    "_rule_promise",
    "_rule_catalogue",
    "_rule_enum",
    "_rule_reject",
    "_rule_recommend",
    "_rule_checks",
    "_rule_cause_fact",
    "_rule_evidence",
)


def _call(name: str, *args: Any) -> list[Issue]:
    """Look the rule up by name at call time, so a test can switch one rule off."""
    rule: Callable[..., list[Issue]] = globals()[name]
    return rule(*args)


def option_issues(
    option: bm.Option,
    problem_ids: Iterable[str],
    *,
    owner_text: str | None = None,
    view: bm.ConstraintsView | None = None,
    cause: bm.RootCause | None = None,
) -> list[Issue]:
    """Every rule broken by one option. `owner_text` (the owner's own messages) turns on the
    evidence check, `view` the constraint-check coverage, `cause` the guessed-cause check."""
    ctx = _Ctx(frozenset(problem_ids), owner_text, view, cause)
    return [issue for name in _OPTION_RULES for issue in _call(name, option, ctx)]


# --- set rules -----------------------------------------------------------------------------------


def _compared(options: tuple[bm.Option, ...]) -> int:
    """Options that were really weighed: a rejected one counts when it names its reason."""
    return sum(1 for o in options if o.status != "rejected" or o.rejected_because.strip())


def _set_empty(oset: bm.OptionSet) -> list[Issue]:
    if not oset.options and not oset.none_reason.strip():
        return [Issue("SET-EMPTY", "", "no option and no reason")]
    return []


def _set_count(oset: bm.OptionSet) -> list[Issue]:
    if oset.options and _compared(oset.options) < 2 and not oset.single_option:
        return [Issue("SET-COUNT", "", "fewer than two options compared")]
    return []


def _set_single(oset: bm.OptionSet) -> list[Issue]:
    if not oset.single_option:
        return []
    if _compared(oset.options) >= 2:
        return [Issue("SET-SINGLE", "", "flagged as single but two options were compared")]
    if not oset.single_reason.strip():
        return [Issue("SET-SINGLE", "", "the single-option flag has no reason")]
    return []


def _set_recommended(oset: bm.OptionSet) -> list[Issue]:
    marked = [o.id for o in oset.options if o.status == "recommended"]
    if len(marked) > 1:
        return [Issue("SET-RECOMMENDED", "", "more than one recommended option")]
    chosen = oset.recommended_id or (marked[0] if marked else None)
    if chosen is None:
        return []
    if marked and oset.recommended_id and marked[0] != oset.recommended_id:
        return [Issue("SET-RECOMMENDED", chosen, "the status and the recommended id differ")]
    first = next((o for o in rank_options(oset.options) if recommendable(o)), None)
    if first is None or first.id != chosen:
        return [Issue("SET-RECOMMENDED", chosen, "not the first of the ranking")]
    return []


def _set_thin(oset: bm.OptionSet) -> list[Issue]:
    live = [o for o in oset.options if o.status != "rejected"]
    if (
        oset.options
        and evidence_thin(oset.options)
        and not any(o.kind == bm.LEARN_FIRST for o in live)
    ):
        return [Issue("SET-THIN", "", "thin evidence and no learn_first option")]
    return []


_SET_RULES: tuple[str, ...] = (
    "_set_empty",
    "_set_count",
    "_set_single",
    "_set_recommended",
    "_set_thin",
)


def set_issues(
    oset: bm.OptionSet,
    problem_ids: Iterable[str],
    *,
    owner_text: str | None = None,
    view: bm.ConstraintsView | None = None,
    cause: bm.RootCause | None = None,
) -> list[Issue]:
    """The set rules, then the option rules of every option."""
    found = [issue for name in _SET_RULES for issue in _call(name, oset)]
    ids = tuple(problem_ids)
    for option in oset.options:
        found += option_issues(option, ids, owner_text=owner_text, view=view, cause=cause)
    return found


# --- the root cause ------------------------------------------------------------------------------


def _cause_status(cause: bm.RootCause, owner_text: str | None) -> list[Issue]:
    if cause.status not in bm.CAUSE_STATUSES:
        return [Issue("CAUSE-STATUS", "", cause.status)]
    return []


def _cause_unsupported(cause: bm.RootCause, owner_text: str | None) -> list[Issue]:
    if cause.status not in bm.OWNER_STATUSES:
        return []
    proof = cause.evidence_for
    if proof and all(pf.said_by_owner(list(e.words), owner_text) for e in proof):
        return []
    return [Issue("CAUSE-UNSUPPORTED", "", "the owner's own words are missing")]


_CAUSE_RULES: tuple[str, ...] = ("_cause_status", "_cause_unsupported")


def cause_issues(cause: bm.RootCause, owner_text: str | None) -> list[Issue]:
    """A cause the owner said or confirmed needs the owner's own words (whole words, in the owner's
    message, nothing else counts); a pi_inferred cause needs no proof and is never stated."""
    return [issue for name in _CAUSE_RULES for issue in _call(name, cause, owner_text)]


def may_state_as_fact(cause: bm.RootCause, owner_text: str | None) -> bool:
    """True only for an owner status with proof."""
    return cause.stateable and not cause_issues(cause, owner_text)


def advance_status(current: str, requested: str, *, by_owner: bool) -> str:
    """The status after a request to raise it: only the owner raises it, one step at a time
    (pi_inferred, owner_said, confirmed), and it is never lowered. An unknown value changes
    nothing."""
    order = bm.CAUSE_STATUSES
    if current not in order:
        return pf.PI_INFERRED
    if not by_owner or requested not in order:
        return current
    at, wanted = order.index(current), order.index(requested)
    return order[at + 1] if wanted > at else current
