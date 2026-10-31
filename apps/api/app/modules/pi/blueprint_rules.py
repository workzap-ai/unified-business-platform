"""L2-3: pure validators and the ranking for an options record (design: docs/pi-saas/
pi-solution-blueprint-design.md section 3.4 and 4; records in `blueprint_models`, text patterns in
`blueprint_text`).

No database, no model, no owner-facing wording. Every function returns data: a list of `Issue`s
(empty means the record passes) or an ordered tuple, and none of them raises: a wrong type in a
record is reported as a MALFORMED issue naming the field. Nothing here is wired into the
conversation or the document yet; a later step calls it before any option is shown.

Rules (codes are stable; each has a test that fails when the rule is removed):

  MALFORMED       a field has the wrong type, or a text is longer than `blueprint_text.MAX_TEXT`
  OPT-ADDR        every option links to at least one stated problem id, and only known ones
  OPT-MONEY       no money in any text pi wrote (what, benefit, limits, trade-offs, risks,
                  dependencies, check reasons, rejection reason), in any script or as words
  OPT-COST        the cost source is staff and the amount is never filled by pi
  OPT-PROMISE     no promised result in any text pi wrote (the constitution's promise rule, "will"
                  without "not", and the wider patterns of `blueprint_text`)
  OPT-CATALOGUE   a build or custom automation names its catalogue key
  OPT-ENUM        kind, effort, reversibility, status, check result, dependency kind, risk level
                  are from their lists
  OPT-REJECT      a rejected option names why, and only a rejected option has a reason
  OPT-RECOMMEND   a recommended option has no violated constraint, no blocking dependency and
                  evidence (a learn_first option needs none)
  OPT-CHECKS      every stated constraint has a check, even when the result is "unknown"
  OPT-CAUSE-FACT  a cause pi only inferred is never worded as a fact (token based, in any option
                  text, a hedge counts only in the same clause)
  OPT-EVIDENCE    evidence words are whole words of the owner's own message; given the owner's
                  messages by id, the message must be one of them
  SET-COUNT       two options are compared, unless the evidence supports only one (flagged)
  SET-SINGLE      the single-option flag is honest: only with one option, and with its reason
  SET-EMPTY       an empty set says why
  SET-DUPLICATE-ID  option ids are unique
  SET-RECOMMENDED one recommendation at most, and it is the first of the ranking
  SET-NO-RECOMMENDATION  a recommendable option exists, so one is recommended or a reason is given
  SET-THIN        thin evidence needs a learn_first option
  CAUSE-STATUS    a cause status is from the list
  CAUSE-UNSUPPORTED  an owner_said or confirmed cause has the owner's own words as proof
"""

from __future__ import annotations

import dataclasses
import re
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.modules.pi import blueprint_models as bm
from app.modules.pi import blueprint_text as bt
from app.modules.pi import problem_fields as pf
from app.modules.pi.constitution import PROMISE

# The patterns are shared with `blueprint_text`, which keeps the copies of brain_docs'
# MONEY_IN_TEXT and WILL (a unit test asserts they are identical to the originals).
MONEY_IN_TEXT = bt.MONEY_IN_TEXT
WILL = bt.WILL

RULE_CODES = (
    "MALFORMED",
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
    "SET-DUPLICATE-ID",
    "SET-RECOMMENDED",
    "SET-NO-RECOMMENDATION",
    "SET-THIN",
    "CAUSE-STATUS",
    "CAUSE-UNSUPPORTED",
)

OwnerMessages = Mapping[str, str]


@dataclass(frozen=True)
class Issue:
    code: str
    option_id: str = ""
    detail: str = ""


@dataclass(frozen=True)
class _Ctx:
    problem_ids: frozenset[str]
    owner_text: str | None
    owner_messages: OwnerMessages | None
    view: bm.ConstraintsView | None
    cause: bm.RootCause | None


def _name(option: Any) -> str:
    """The option's id as text, whatever it holds."""
    value = getattr(option, "id", "")
    return value if isinstance(value, str) else str(value)


def _is_option(value: Any) -> bool:
    return isinstance(value, bm.Option)


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
    """The texts that describe what the option is or does, risks included."""
    texts = [option.what, option.benefit, *option.limits, *option.trade_offs]
    texts += [r.text for r in option.risks]
    return [t for t in texts if t]


# --- owner evidence ------------------------------------------------------------------------------


def _ref_verified(ref: Any, owner_messages: OwnerMessages | None) -> bool:
    """The ref is the owner's, names a message and carries words and, when the owner's messages are
    known by id, that message is one of them and the words are whole words of it. Without the
    owner's messages only the `verified` flag set by `verify_option` can stand in for the check."""
    if not isinstance(ref, bm.Evidence) or not ref.claimed or ref.role != "owner":
        return False
    if owner_messages is None:
        return ref.verified is True and ref.seal == bm.SEAL
    try:
        said = owner_messages.get(ref.msg)
        return isinstance(said, str) and pf.said_by_owner(list(bm.seq(ref.words)), said)
    except Exception:  # an owner_messages that is not a usable mapping proves nothing
        return False


def _owner_map(owner_messages: Any) -> OwnerMessages | None:
    """None stays None; a mapping is used as it is; anything else is an owner record that proves
    nothing (an empty mapping), never an error."""
    if owner_messages is None or isinstance(owner_messages, Mapping):
        return owner_messages
    return {}


def _verified(option: Any, owner_messages: OwnerMessages | None) -> Any:
    """A copy of the option with the id as text and, given the owner's messages, every evidence
    ref's `verified` flag recomputed from them (a flag set by hand is not trusted)."""
    if not isinstance(option, bm.Option):
        return option
    owner_messages = _owner_map(owner_messages)
    changes: dict[str, Any] = {}
    if not isinstance(option.id, str):
        changes["id"] = _name(option)
    if owner_messages is not None:
        changes["evidence"] = tuple(
            dataclasses.replace(
                e,
                verified=_ref_verified(e, owner_messages),
                seal=bm.SEAL if _ref_verified(e, owner_messages) else "",
            )
            for e in bm.seq(option.evidence)
            if isinstance(e, bm.Evidence)
        )
    return dataclasses.replace(option, **changes) if changes else option


def verify_option(option: bm.Option, owner_messages: OwnerMessages) -> bm.Option:
    """The option with each evidence ref marked verified only when it is the owner's, names one of
    the owner's messages and its words are whole words of that message. This is the only place the
    flag is set; `Option.evidence_strength` counts verified refs only."""
    verified: bm.Option = _verified(option, owner_messages)
    return verified


def strength(option: bm.Option, owner_messages: OwnerMessages | None = None) -> int:
    """How many distinct owner messages verifiably back the option (see `verify_option`). Without
    the owner's messages only refs already marked verified count."""
    checked = _verified(option, owner_messages)
    return int(checked.evidence_strength) if _is_option(checked) else 0


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


def recommendable(option: bm.Option, owner_messages: OwnerMessages | None = None) -> bool:
    """Derived from code facts, never from the model's confidence."""
    if not _is_option(option):
        return False
    option = _verified(option, owner_messages)
    return option.status != "rejected" and not _blockers(option)


def evidence_thin(
    options: Iterable[bm.Option], owner_messages: OwnerMessages | None = None
) -> bool:
    """True when no option other than learn_first has any owner evidence behind it (a rejected or
    violating option does not count, nor does evidence the owner's messages do not back): the
    honest first step is to learn, not to build."""
    checked = [_verified(o, owner_messages) for o in _only_options(options)]
    return not any(
        o.evidence_strength >= 1
        for o in checked
        if o.kind != bm.LEARN_FIRST and o.status != "rejected" and not o.violated
    )


def _only_options(options: Any) -> list[bm.Option]:
    """The Option items of any iterable (not a string or a mapping); anything else gives nothing."""
    if not isinstance(options, Iterable) or isinstance(options, str | bytes | Mapping):
        return []
    try:
        return [o for o in options if _is_option(o)]
    except Exception:  # an iterable that fails half way
        return []


def _effort_rank(option: bm.Option) -> int:
    return bm.EFFORTS.index(option.effort) if option.effort in bm.EFFORTS else len(bm.EFFORTS)


def _reversibility_rank(option: bm.Option) -> int:
    values = bm.REVERSIBILITY
    return values.index(option.reversibility) if option.reversibility in values else len(values)


def _unknown_flag(option: bm.Option) -> int:
    return 1 if option.unknown_checks else 0


def _tier(option: bm.Option) -> int:
    """1 reliable options; 2 learn_first; 3 visible but not recommendable (blocked, no evidence, no
    catalogue key); 4 violates a stated constraint; 5 rejected. While the evidence is thin no
    option can be in tier 1, so learn_first comes first then; when it is strong learn_first follows
    the reliable options."""
    if option.status == "rejected":
        return 5
    if option.violated:
        return 4
    if _blockers(option):
        return 3
    if option.kind == bm.LEARN_FIRST:
        return 2
    return 1


def _presort_key(option: bm.Option) -> tuple[str, str, str, str]:
    """A total order over options, so ties never depend on the order they came in: id, wording,
    then the whole record (risks, dependencies, trade-offs and the rest)."""
    try:
        rest = repr(option)
    except Exception:
        rest = ""
    return (_name(option), str(option.what), str(option.benefit), rest)


def rank_options(
    options: Iterable[bm.Option] | None, owner_messages: OwnerMessages | None = None
) -> tuple[bm.Option, ...]:
    """The options in the order they are offered: smallest reliable first. Deterministic, and it
    never raises: anything that is not an Option is left out, a missing list is empty.

    Order, first rule that differs wins:
      1. tier: reliable options; then learn_first (so it leads when the evidence is thin, because
         then no option is reliable, and follows the reliable options when the evidence is strong);
         then options that are visible but cannot be recommended (blocked, no evidence, no
         catalogue key); then options that violate a stated constraint; then rejected ones. A
         violation is never rescued by a good score.
      2. within a tier: no unknown constraint check before an unknown one (an unchecked option is
         not "reliable"; the reviewer sees it flagged);
      3. effort class, smallest first (none, small, medium, large);
      4. reversibility, easiest to undo first (reversible, partly, hard);
      5. evidence strength, strongest first (distinct owner messages behind it, capped; with the
         owner's messages given, only evidence they back counts);
      6. ties keep the order of the input sorted by id and then wording (a stable sort), so they
         never depend on the order the options came in.
    """
    items = _only_options(options)
    items.sort(key=_presort_key)
    checked = [(_verified(o, owner_messages), o) for o in items]
    originals = {id(v): o for v, o in checked}
    ranked = sorted(
        (v for v, _ in checked),
        key=lambda o: (
            _tier(o),
            _unknown_flag(o),
            _effort_rank(o),
            _reversibility_rank(o),
            -o.evidence_strength,
        ),
    )
    return tuple(originals[id(v)] for v in ranked)


# --- option rules --------------------------------------------------------------------------------


def _bad_fields(option: bm.Option) -> list[str]:
    """The fields with the wrong type, and the texts that are too long."""
    bad: list[str] = []
    for name in (
        "id",
        "kind",
        "what",
        "benefit",
        "effort",
        "reversibility",
        "status",
        "expected_outcome",
        "rejected_because",
    ):
        if not isinstance(getattr(option, name, None), str):
            bad.append(name)
    if not isinstance(option.catalogue_key, str | None):
        bad.append("catalogue_key")
    for name in ("addresses", "works_on", "limits", "trade_offs"):
        value = getattr(option, name, None)
        if not isinstance(value, tuple | list) or not all(isinstance(i, str) for i in value):
            bad.append(name)
    nested: tuple[tuple[str, type, tuple[str, ...]], ...] = (
        ("dependencies", bm.Dependency, ("kind", "text")),
        ("risks", bm.Risk, ("text", "level")),
        ("constraint_checks", bm.ConstraintCheck, ("constraint", "result", "why")),
    )
    for name, cls, attrs in nested:
        value = getattr(option, name, None)
        ok = isinstance(value, tuple | list) and all(
            isinstance(i, cls) and all(isinstance(getattr(i, a), str) for a in attrs) for i in value
        )
        if not ok:
            bad.append(name)
    refs = getattr(option, "evidence", None)
    if not isinstance(refs, tuple | list) or not all(
        isinstance(e, bm.Evidence)
        and isinstance(e.msg, str)
        and isinstance(e.role, str)
        and isinstance(e.verified, bool)
        and isinstance(e.seal, str)
        and isinstance(e.words, tuple | list)
        and all(isinstance(w, str) for w in e.words)
        for e in refs
    ):
        bad.append("evidence")
    fit = getattr(option, "fit", None)
    fit_ok = isinstance(fit, bm.Fit) and all(
        isinstance(getattr(fit, n), tuple | list)
        and all(isinstance(i, str) for i in getattr(fit, n))
        for n in ("problem_link", "facts_reused")
    )
    if not fit_ok:
        bad.append("fit")
    if not isinstance(getattr(option, "cost", None), bm.Cost):
        bad.append("cost")
    if not bad:
        bad += [f"{t[:20]}...: too long" for t in _own_texts(option) if len(t) > bt.MAX_TEXT]
    return bad


def _rule_addr(option: bm.Option, ctx: _Ctx) -> list[Issue]:
    if not option.addresses:
        return [Issue("OPT-ADDR", option.id, "links to no problem")]
    unknown = [p for p in option.addresses if p not in ctx.problem_ids]
    return [Issue("OPT-ADDR", option.id, f"unknown problem {p}") for p in unknown]


def _rule_money(option: bm.Option, ctx: _Ctx) -> list[Issue]:
    return [Issue("OPT-MONEY", option.id, t[:60]) for t in _own_texts(option) if bt.money_in(t)]


def _rule_cost(option: bm.Option, ctx: _Ctx) -> list[Issue]:
    if option.cost.amount is not None or option.cost.source != bm.COST_SOURCE:
        return [Issue("OPT-COST", option.id, "the cost is staff's, never filled by pi")]
    return []


def _rule_promise(option: bm.Option, ctx: _Ctx) -> list[Issue]:
    """Every text pi wrote is scanned, risks, dependencies, check reasons and the rejection reason
    included."""
    return [
        Issue("OPT-PROMISE", option.id, text[:60])
        for text in _own_texts(option)
        if bt.promise_in(text, PROMISE, WILL)
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
    checked = _verified(option, ctx.owner_messages)
    return [Issue("OPT-RECOMMEND", option.id, why) for why in _blockers(checked)]


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
    return [
        Issue("OPT-CAUSE-FACT", option.id, "a guessed cause is worded as a fact")
        for text in _claims(option)
        if bt.states_as_fact(cause.text, text)
    ]


# Owner message ids have no fixed form (a counter, a uuid, "m1"), so there is no clean pattern to
# allow; the ids that name another speaker are refused instead. This list is a floor, not the
# proof: the strict check is `owner_messages` by id.
_NON_OWNER_WORDS = frozenset(
    "assistant chatbot pi ai llm bot system agent model staff reviewer workzap gpt claude".split()
)


def _non_owner_id(msg: str) -> bool:
    """Without the owner's messages by id, a message id with a letter group that names another
    speaker ("assistant-5", "assistant5", "ai-1", "llm_2", "workzap-pi-1") is not the owner's."""
    return any(t in _NON_OWNER_WORDS for t in re.findall(r"[a-z]+", msg.lower()))


def _rule_evidence(option: bm.Option, ctx: _Ctx) -> list[Issue]:
    """With the owner's messages by id: every ref names one of them and its words are in it. With
    only the owner's text: the words are in it. A ref that names no message or has no words fails
    either way."""
    bad: list[Issue] = []
    for ref in option.evidence:
        if ctx.owner_messages is not None:
            ok = _ref_verified(ref, ctx.owner_messages)
        elif ctx.owner_text is None:
            ok = _ref_verified(ref, None)  # nothing to check against: only a verified ref passes
        else:
            ok = (
                ref.claimed
                and ref.role == "owner"
                and not _non_owner_id(ref.msg)
                and pf.said_by_owner(list(ref.words), ctx.owner_text)
            )
        if not ok:
            bad.append(Issue("OPT-EVIDENCE", option.id, ref.msg))
    return bad


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
    """Look the rule up by name at call time, so a test can switch one rule off. A rule that fails
    is reported as MALFORMED, never raised."""
    rule: Callable[..., list[Issue]] = globals()[name]
    try:
        return rule(*args)
    except Exception:  # a record no rule can read is a malformed record
        return [Issue("MALFORMED", "", f"{name} could not read the record")]


def _context(
    problem_ids: Any, owner_text: Any, owner_messages: Any, view: Any, cause: Any
) -> tuple[_Ctx, list[Issue]]:
    """The checks' inputs, with a MALFORMED issue for each one of the wrong type."""
    issues: list[Issue] = []
    ids: frozenset[str] = frozenset()
    if isinstance(problem_ids, Iterable) and not isinstance(problem_ids, str | bytes | Mapping):
        items = list(problem_ids)
        if all(isinstance(i, str) for i in items):
            ids = frozenset(items)
        else:
            issues.append(Issue("MALFORMED", "", "problem_ids"))
    else:
        issues.append(Issue("MALFORMED", "", "problem_ids"))
    if not isinstance(owner_text, str | None):
        issues.append(Issue("MALFORMED", "", "owner_text"))
        owner_text = None
    if owner_messages is not None and not (
        isinstance(owner_messages, Mapping)
        and all(isinstance(k, str) and isinstance(v, str) for k, v in owner_messages.items())
    ):
        issues.append(Issue("MALFORMED", "", "owner_messages"))
        owner_messages = None
    if not isinstance(view, bm.ConstraintsView | None):
        issues.append(Issue("MALFORMED", "", "view"))
        view = None
    if not isinstance(cause, bm.RootCause | None) or (
        cause is not None and not isinstance(cause.text, str)
    ):
        issues.append(Issue("MALFORMED", "", "cause"))
        cause = None
    return _Ctx(ids, owner_text, owner_messages, view, cause), issues


def option_issues(
    option: bm.Option,
    problem_ids: Iterable[str] | None,
    *,
    owner_text: str | None = None,
    owner_messages: OwnerMessages | None = None,
    view: bm.ConstraintsView | None = None,
    cause: bm.RootCause | None = None,
) -> list[Issue]:
    """Every rule broken by one option, never raising. `owner_messages` (owner message id to its
    text) turns on the strict evidence check, `owner_text` the corpus-only one, `view` the
    constraint-check coverage, `cause` the guessed-cause check."""
    ctx, found = _context(problem_ids, owner_text, owner_messages, view, cause)
    if not _is_option(option):
        return [*found, Issue("MALFORMED", "", "option")]
    try:
        bad = _bad_fields(option)
    except Exception:
        bad = ["option"]
    if bad:
        return [*found, *(Issue("MALFORMED", _name(option), field) for field in bad)]
    return found + [issue for name in _OPTION_RULES for issue in _call(name, option, ctx)]


# --- set rules -----------------------------------------------------------------------------------


def _compared(options: tuple[bm.Option, ...]) -> int:
    """Options that were really weighed: a rejected one counts when it names its reason."""
    return sum(1 for o in options if o.status != "rejected" or o.rejected_because.strip())


def _set_empty(oset: bm.OptionSet, ctx: _Ctx) -> list[Issue]:
    if not oset.options and not oset.none_reason.strip():
        return [Issue("SET-EMPTY", "", "no option and no reason")]
    return []


def _set_count(oset: bm.OptionSet, ctx: _Ctx) -> list[Issue]:
    if oset.options and _compared(oset.options) < 2 and not oset.single_option:
        return [Issue("SET-COUNT", "", "fewer than two options compared")]
    return []


def _set_single(oset: bm.OptionSet, ctx: _Ctx) -> list[Issue]:
    if not oset.single_option:
        return []
    if _compared(oset.options) >= 2:
        return [Issue("SET-SINGLE", "", "flagged as single but two options were compared")]
    if not oset.single_reason.strip():
        return [Issue("SET-SINGLE", "", "the single-option flag has no reason")]
    return []


def _set_duplicate(oset: bm.OptionSet, ctx: _Ctx) -> list[Issue]:
    counts = Counter(o.id for o in oset.options)
    return [
        Issue("SET-DUPLICATE-ID", name, "used more than once")
        for name, n in counts.items()
        if n > 1
    ]


def _set_recommended(oset: bm.OptionSet, ctx: _Ctx) -> list[Issue]:
    marked = [o.id for o in oset.options if o.status == "recommended"]
    if len(marked) > 1:
        return [Issue("SET-RECOMMENDED", "", "more than one recommended option")]
    chosen = oset.recommended_id or (marked[0] if marked else None)
    if chosen is None:
        return []
    if marked and oset.recommended_id and marked[0] != oset.recommended_id:
        return [Issue("SET-RECOMMENDED", chosen, "the status and the recommended id differ")]
    ranked = rank_options(oset.options, ctx.owner_messages)
    first = next((o for o in ranked if recommendable(o, ctx.owner_messages)), None)
    if first is None or first.id != chosen:
        return [Issue("SET-RECOMMENDED", chosen, "not the first of the ranking")]
    return []


def _set_no_recommendation(oset: bm.OptionSet, ctx: _Ctx) -> list[Issue]:
    """A set that could recommend something but recommends nothing needs its reason."""
    if oset.recommended_id or any(o.status == "recommended" for o in oset.options):
        return []
    if oset.no_recommendation_reason.strip():
        return []
    if any(recommendable(o, ctx.owner_messages) for o in oset.options):
        return [Issue("SET-NO-RECOMMENDATION", "", "an option could be recommended and none is")]
    return []


def _set_thin(oset: bm.OptionSet, ctx: _Ctx) -> list[Issue]:
    live = [o for o in oset.options if o.status != "rejected"]
    thin = evidence_thin(oset.options, ctx.owner_messages)
    if oset.options and thin and not any(o.kind == bm.LEARN_FIRST for o in live):
        return [Issue("SET-THIN", "", "thin evidence and no learn_first option")]
    return []


_SET_RULES: tuple[str, ...] = (
    "_set_empty",
    "_set_count",
    "_set_single",
    "_set_duplicate",
    "_set_recommended",
    "_set_no_recommendation",
    "_set_thin",
)


def set_issues(
    oset: bm.OptionSet,
    problem_ids: Iterable[str] | None,
    *,
    owner_text: str | None = None,
    owner_messages: OwnerMessages | None = None,
    view: bm.ConstraintsView | None = None,
    cause: bm.RootCause | None = None,
) -> list[Issue]:
    """The set rules, then the option rules of every option. Never raises."""
    ctx, found = _context(problem_ids, owner_text, owner_messages, view, cause)
    if not isinstance(oset, bm.OptionSet):
        return [*found, Issue("MALFORMED", "", "option set")]
    shape = [
        field
        for field, ok in (
            ("options", isinstance(oset.options, tuple | list)),
            ("recommended_id", isinstance(oset.recommended_id, str | None)),
            ("single_reason", isinstance(oset.single_reason, str)),
            ("none_reason", isinstance(oset.none_reason, str)),
            ("no_recommendation_reason", isinstance(oset.no_recommendation_reason, str)),
        )
        if not ok
    ]
    if shape:
        return [*found, *(Issue("MALFORMED", "", f) for f in shape)]
    options = tuple(oset.options)
    found += [
        Issue("MALFORMED", "", "options: not an Option") for o in options if not _is_option(o)
    ]
    per_option: list[Issue] = []
    clean: list[bm.Option] = []
    for option in options:
        if not _is_option(option):
            continue
        issues = option_issues(
            option,
            ctx.problem_ids,
            owner_text=ctx.owner_text,
            owner_messages=ctx.owner_messages,
            view=ctx.view,
            cause=ctx.cause,
        )
        per_option += issues
        if not any(i.code == "MALFORMED" for i in issues):
            clean.append(option)
    # the set rules read only the options whose fields are well formed
    inner = dataclasses.replace(oset, options=tuple(clean))
    found += [issue for name in _SET_RULES for issue in _call(name, inner, ctx)]
    return found + per_option


# --- the root cause ------------------------------------------------------------------------------


def _cause_status(
    cause: bm.RootCause, owner_text: str | None, owner: OwnerMessages | None
) -> list[Issue]:
    if cause.status not in bm.CAUSE_STATUSES:
        return [Issue("CAUSE-STATUS", "", cause.status)]
    return []


def _cause_unsupported(
    cause: bm.RootCause, owner_text: str | None, owner: OwnerMessages | None
) -> list[Issue]:
    if cause.status not in bm.OWNER_STATUSES:
        return []
    proof = list(bm.seq(cause.evidence_for))
    if owner is not None:
        proven = bool(proof) and all(_ref_verified(e, owner) for e in proof)
    else:
        proven = bool(proof) and all(
            isinstance(e, bm.Evidence) and pf.said_by_owner(list(bm.seq(e.words)), owner_text)
            for e in proof
        )
    if proven:
        return []
    return [Issue("CAUSE-UNSUPPORTED", "", "the owner's own words are missing")]


_CAUSE_RULES: tuple[str, ...] = ("_cause_status", "_cause_unsupported")


def cause_issues(
    cause: bm.RootCause,
    owner_text: str | None,
    owner_messages: OwnerMessages | None = None,
) -> list[Issue]:
    """A cause the owner said or confirmed needs the owner's own words (whole words, in the owner's
    message, nothing else counts); a pi_inferred cause needs no proof and is never stated. Given the
    owner's messages by id, the proof must name one of them. Never raises."""
    if not isinstance(cause, bm.RootCause):
        return [Issue("MALFORMED", "", "cause")]
    bad = [
        f
        for f, ok in (
            ("text", isinstance(cause.text, str)),
            ("status", isinstance(cause.status, str)),
            ("evidence_for", isinstance(cause.evidence_for, tuple | list)),
            ("evidence_against", isinstance(cause.evidence_against, tuple | list)),
            ("owner_text", isinstance(owner_text, str | None)),
        )
        if not ok
    ]
    if bad:
        return [Issue("MALFORMED", "", f) for f in bad]
    found: list[Issue] = []
    for name in _CAUSE_RULES:
        found += _call(name, cause, owner_text, owner_messages)
    return found


def may_state_as_fact(
    cause: bm.RootCause, owner_text: str | None, owner_messages: OwnerMessages | None = None
) -> bool:
    """True only for an owner status with proof."""
    return (
        isinstance(cause, bm.RootCause)
        and cause.stateable
        and not cause_issues(cause, owner_text, owner_messages)
    )


def owner_event(owner_msg: Any, owner_msgs: Collection[str] | None = None) -> bool:
    """A marker that the owner said it: the id of an owner message (and, when the owner's message
    ids are known, one of them). A bare True is not a marker."""
    if not isinstance(owner_msg, str) or not owner_msg.strip():
        return False
    return owner_msgs is None or owner_msg in owner_msgs


def advance_status(
    current: str,
    requested: str,
    *,
    owner_msg: str | None,
    owner_msgs: Collection[str] | None = None,
) -> str:
    """The status after a request to raise it. Only an owner event raises it (`owner_msg`, the id of
    an owner message; with `owner_msgs` it must be one of them), one step at a time (pi_inferred,
    owner_said, confirmed), and it is never lowered. An unknown value changes nothing."""
    order = bm.CAUSE_STATUSES
    if current not in order:
        return pf.PI_INFERRED
    by_owner = owner_event(owner_msg, owner_msgs)
    if not by_owner or requested not in order:
        return current
    at, wanted = order.index(current), order.index(requested)
    return order[at + 1] if wanted > at else current
