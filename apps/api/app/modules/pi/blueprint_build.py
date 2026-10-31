"""PS-4: build a solution blueprint from the recommended option and the owner's facts.

Pure, no database, no model call, no clock. `build_blueprint` never raises and never invents:

  * every sentence comes from the option, the owner's words, or a fixed localized template
    (`blueprint_strings`); an option text is cleaned first (promise and credential
    sentences removed,
    money and numbers the owner or staff did not give masked, with an unknown line saying so);
  * cost and timeline are staff's: an amount exists only as a staff input with its source, otherwise
    "to be quoted by staff" / "to be estimated by staff";
  * a constraint is "ok" only when the option's own check says so; a constraint nobody checked is
    "unknown"; a violated hard constraint refuses to build;
  * with no stated problem, no usable option, or an option that answers none of the stated
    problems, the result is `insufficient_information` with exactly what is missing and one
    targeted question (the caller sends it; it is the last sentence of that message);
  * every phase with an action sits behind an owner approval step and a reviewer approval comes
    first; there is always a baseline step where no starting figure is known, a review step and an
    exit step. The blueprint executes nothing.

Coupling to the L2-3 option models is one function, `option_from`, which reads attributes by name
(documented there). Nothing in this module imports `blueprint_models`.

Wiring (after FT-02 merges), see the PS-4 report: `brain_docs.draft_offer` calls `build_blueprint`
once the owner has said yes and stores `render_blueprint` output in the reviewer-visible content;
`brain_docs.blockers` calls `blueprint_issues`. Nothing calls it yet.
"""

from __future__ import annotations

import dataclasses
import math
import re
from collections.abc import Callable, Mapping
from itertools import islice
from typing import Any

from app.modules.pi import blueprint_strings as bs
from app.modules.pi.blueprint_checks import (
    SECTIONS,
    Issue,
    canon_number,
    check_blueprint,
    clean_text,
    fold,
    fold_digits,
    numbers_in,
    section_report,
    tidy,
)
from app.modules.pi.blueprint_extra import (
    alternative_rows,
    alternatives_from,
    cause_rows,
    causes_from,
    data_rows,
    fact_rows,
    open_items,
    parse_corrections,
    reason_rows,
)
from app.modules.pi.blueprint_extra import get_attr as _get
from app.modules.pi.blueprint_extra import seq_of as _seq
from app.modules.pi.blueprint_extra import short as _text
from app.modules.pi.blueprint_extra import shorts as _texts
from app.modules.pi.blueprint_render import render_blueprint
from app.modules.pi.blueprint_types import (
    INSUFFICIENT,
    MAX_CONSTRAINTS,
    MAX_DEPS,
    MAX_FACT_STRINGS,
    MAX_FACT_TEXT,
    MAX_PHASES,
    MAX_PROBLEMS,
    MAX_RISKS,
    MAX_STAFF,
    MAX_STEPS,
    MAX_TRIED,
    READY,
    REFUSED,
    ROLES,
    UNKNOWN,
    Blueprint,
    CheckIn,
    ConstraintIn,
    ConstraintRow,
    CostLine,
    Criterion,
    DepIn,
    Edge,
    ExternalDep,
    FactRow,
    Measure,
    Milestone,
    Missing,
    Module,
    OptionIn,
    ProblemIn,
    ProblemRow,
    Responsibility,
    RiskIn,
    RiskLine,
    StaffCost,
    StaffDuration,
    StaffInputs,
    Step,
    StepIn,
    Summary,
    TimeLine,
    TriedIn,
)

__all__ = [
    "Issue",
    "SECTIONS",
    "build_blueprint",
    "blueprint_issues",
    "option_from",
    "recommended_from",
    "render_blueprint",
    "section_report",
]

_DEP_KINDS = ("owner_input", "access", "data", "person", "other_option", "other")
_SCALAR_KINDS = ("budget", "staff", "deadline")
_REDUCE = re.compile(
    r"\b(?:less than|fewer than|below|under|at most|no more than|reduce[d]? to|down to|"
    r"cut to|kam se kam|se kam|kam ho|kam hona|ghat)\b"
    r"|اقل|أقل|اکثر سے کم|سے کم|کم ہو|گھٹ|انخفاض|تقليل",
    re.IGNORECASE,
)
_OWNER_KINDS = ("owner_action", "learn_first")
_STOP = ".!?؟۔ "


# ---- reading loose input -----------------------------------------------------------------------


def option_from(option: Any) -> OptionIn | None:
    """THE adapter from an L2-3 `blueprint_models.Option` (or any mapping or object with the same
    attribute names) to this module's `OptionIn`. Attributes read by name and tolerated absent:

      id, kind, what, addresses, benefit, effort, catalogue_key, status, expected_outcome, limits,
      dependencies[kind, text, blocking], risks[text, level],
      constraint_checks[constraint, result, why]

    Optional and absent in L2-3 today (staff or a later step supply them): `steps[text, role,
    done_check, after, phase, id]` and `modules`. Cost, evidence, fit and the rest are not read:
    cost is never pi's. Returns None when `option` is None or not a record."""
    if option is None or isinstance(option, str | int | float | bool | list | tuple):
        return None
    steps: list[StepIn] = []
    for s in _seq(_get(option, "steps"), MAX_STEPS):
        if isinstance(s, str):
            steps.append(StepIn(text=s))
            continue
        after = _texts(_get(s, "after"), MAX_STEPS, 40)
        phase = _get(s, "phase", 0)
        steps.append(
            StepIn(
                text=_text(_get(s, "text")),
                role=_text(_get(s, "role"), 20).casefold(),
                done_check=_text(_get(s, "done_check")),
                after=after,
                phase=phase if isinstance(phase, int) and not isinstance(phase, bool) else 0,
                id=_text(_get(s, "id"), 40),
                problems=_texts(_get(s, "problems"), MAX_PROBLEMS, 40),
            )
        )
    deps = tuple(
        DepIn(
            kind=k if (k := _text(_get(d, "kind"), 20)) in _DEP_KINDS else "other",
            text=_text(_get(d, "text")),
            blocking=_get(d, "blocking") is True,
        )
        for d in _seq(_get(option, "dependencies"), MAX_DEPS)
    )
    risks = tuple(
        RiskIn(_text(_get(r, "text")), _text(_get(r, "level"), 10) or "low")
        for r in _seq(_get(option, "risks"), MAX_RISKS)
    )
    raw_checks = _get(option, "constraint_checks")
    if raw_checks is None:
        raw_checks = _get(option, "checks")
    checks = tuple(
        CheckIn(
            _text(_get(c, "constraint"), 40),
            r
            if (r := _text(_get(c, "result"), 12)) in ("ok", "violates", "unknown")
            else "unknown",
            _text(_get(c, "why")),
        )
        for c in _seq(raw_checks, MAX_CONSTRAINTS + MAX_TRIED)
    )
    return OptionIn(
        id=_text(_get(option, "id"), 40),
        kind=_text(_get(option, "kind"), 30),
        what=_text(_get(option, "what"), 600),
        addresses=_texts(_get(option, "addresses"), MAX_PROBLEMS, 40),
        benefit=_text(_get(option, "benefit")),
        effort=_text(_get(option, "effort"), 20),
        catalogue_key=_text(_get(option, "catalogue_key"), 60),
        modules=_texts(_get(option, "modules"), 6),
        steps=tuple(steps),
        dependencies=deps,
        risks=risks,
        limits=_texts(_get(option, "limits"), 6),
        checks=checks,
        expected_outcome=_text(_get(option, "expected_outcome")),
        status=_text(_get(option, "status"), 20),
        reversibility=_text(_get(option, "reversibility"), 20),
        rejected_because=_text(_get(option, "rejected_because")),
        entities=_texts(_get(option, "entities"), 8, 120),
        integrations=_texts(_get(option, "integrations"), 8, 120),
        permissions=tuple(
            (_text(_get(x, "role"), 20).casefold(), _text(_get(x, "what")))
            for x in _seq(_get(option, "permissions"), 8)
        ),
    )


def recommended_from(option_set: Any) -> tuple[OptionIn | None, str]:
    """The recommended option of an L2-3 `OptionSet` (attributes `options`, `recommended_id`,
    `none_reason`, `no_recommendation_reason`) as an `OptionIn`, or (None, the set's own reason)."""
    options = _seq(_get(option_set, "options"), 20)
    rid = _text(_get(option_set, "recommended_id"), 40)
    for o in options:
        if rid and _text(_get(o, "id"), 40) == rid:
            return option_from(o), ""
    reason = _text(_get(option_set, "none_reason")) or _text(
        _get(option_set, "no_recommendation_reason")
    )
    return None, reason


def _problems(raw: Any) -> tuple[ProblemIn, ...]:
    items: list[Any] = []
    if isinstance(raw, Mapping):
        for k, v in islice(raw.items(), MAX_PROBLEMS):
            items.append({"id": k, **v} if isinstance(v, Mapping) else v)
    else:
        items = list(_seq(raw, MAX_PROBLEMS))
    out: list[ProblemIn] = []
    seen: set[str] = set()
    for i, p in enumerate(items, 1):
        if p is None or isinstance(p, str | int | float | bool | list | tuple):
            continue
        pid = _text(_get(p, "id"), 40) or f"p{i}"
        if pid in seen:
            continue
        seen.add(pid)
        title = (
            _text(_get(p, "title_local")) or _text(_get(p, "title")) or _text(_get(p, "summary"))
        )
        figures = " ".join(_texts(_get(p, "figures"), 3, 80))
        out.append(
            ProblemIn(
                id=pid,
                title=title,
                words=_texts(_get(p, "user_words") or _get(p, "words"), 4, 300),
                figure=_text(_get(p, "of_total")) or _text(_get(p, "figure")) or figures,
                frequency=_text(_get(p, "frequency_text")) or _text(_get(p, "frequency")),
                since=_text(_get(p, "since_text")) or _text(_get(p, "since")),
                expected_outcome=_text(_get(p, "expected_outcome")),
            )
        )
    return tuple(out)


def _constraints(raw: Any) -> tuple[ConstraintIn, ...]:
    out: list[ConstraintIn] = []
    counts: dict[str, int] = {}

    def add(kind: str, value: Any) -> None:
        text = _text(_get(value, "text") if not isinstance(value, str) else value)
        if not text or len(out) >= MAX_CONSTRAINTS:
            return
        kind = kind if kind in (*_SCALAR_KINDS, "cannot_change") else "other"
        counts[kind] = counts.get(kind, 0) + 1
        n = counts[kind]
        label = kind if (kind in _SCALAR_KINDS and n == 1) else f"{kind}#{n}"
        blocks = _texts(_get(value, "blocks"), 8, 60) if not isinstance(value, str) else ()
        hard = _get(value, "hard") is not False if not isinstance(value, str) else True
        out.append(ConstraintIn(label, kind, text, blocks, hard))

    if isinstance(raw, Mapping):
        for kind in (*_SCALAR_KINDS,):
            if raw.get(kind):
                add(kind, raw[kind])
        for v in _seq(raw.get("cannot_change"), MAX_CONSTRAINTS):
            add("cannot_change", v)
    else:
        for v in _seq(raw, MAX_CONSTRAINTS):
            add(_text(_get(v, "kind"), 20) if not isinstance(v, str) else "other", v)
    return tuple(out)


def _tried(raw: Any) -> tuple[TriedIn, ...]:
    out = []
    for t in _seq(raw, MAX_TRIED):
        what = _text(_get(t, "what")) if not isinstance(t, str) else _text(t)
        if what:
            out.append(TriedIn(what, _text(_get(t, "outcome")) if not isinstance(t, str) else ""))
    return tuple(out)


def _facts(raw: Any) -> tuple[str, ...]:
    """Every string in the owner's facts (a string, a list, or a mapping, three levels deep)."""
    out: list[str] = []

    def walk(v: Any, depth: int) -> None:
        if len(out) >= MAX_FACT_STRINGS:
            return
        if isinstance(v, str):
            t = tidy(v, MAX_FACT_TEXT)
            if t:
                out.append(t)
        elif depth < 3 and isinstance(v, Mapping):
            for x in islice(v.values(), MAX_FACT_STRINGS):
                walk(x, depth + 1)
        elif depth < 3 and isinstance(v, list | tuple):
            for x in islice(v, MAX_FACT_STRINGS):
                walk(x, depth + 1)

    walk(raw, 0)
    return tuple(out)


def _amount(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(fold_digits(value.strip()).replace(",", ""))
        except ValueError:
            return None
    if isinstance(value, int | float) and math.isfinite(value) and 0 <= value < 1e12:
        return float(value)
    return None


def _staff(raw: Any) -> StaffInputs:
    if isinstance(raw, StaffInputs):
        return raw
    if raw is None:
        return StaffInputs()
    costs: list[StaffCost] = []
    durations: list[StaffDuration] = []
    roles: list[tuple[str, str]] = []
    dropped: list[str] = []
    for c in _seq(_get(raw, "costs"), MAX_STAFF):
        amount = _amount(_get(c, "amount"))
        source = _text(_get(c, "source"), 120)
        if amount is None or not source:
            dropped.append("cost")
            continue
        cur = _text(_get(c, "currency"), 8)
        costs.append(
            StaffCost(
                _text(_get(c, "item"), 120) or "plan", amount, cur if cur.isalpha() else "", source
            )
        )
    for d in _seq(_get(raw, "durations"), MAX_STAFF):
        text, source = _text(_get(d, "text"), 120), _text(_get(d, "source"), 120)
        if not text or not source:
            dropped.append("duration")
            continue
        durations.append(StaffDuration(text, source, _text(_get(d, "step"), 40)))
    for r in _seq(_get(raw, "roles"), MAX_STAFF):
        role = _text(_get(r, "role"), 20).casefold()
        step = _text(_get(r, "step"), 40)
        if role in ROLES and step:
            roles.append((step, role))
    return StaffInputs(tuple(costs), tuple(durations), tuple(roles), tuple(dropped))


def _known(corpus: list[str], staff: StaffInputs) -> frozenset[str]:
    known: set[str] = set()
    for t in corpus:
        known.update(numbers_in(t))
    for c in staff.costs:
        known.add(canon_number(str(c.amount)))
        known.update(numbers_in(c.item))
        known.update(numbers_in(c.source))
    for d in staff.durations:
        known.update(numbers_in(d.text))
        known.update(numbers_in(d.source))
    return frozenset(known)


def _corpus(
    facts: tuple[str, ...],
    problems: tuple[ProblemIn, ...],
    constraints: tuple[ConstraintIn, ...],
    tried: tuple[TriedIn, ...],
    outcome: str,
    extra: list[str] | None = None,
) -> list[str]:
    out = list(facts) + list(extra or ())
    for p in problems:
        out += [p.title, *p.words, p.figure, p.frequency, p.since, p.expected_outcome]
    for c in constraints:
        out.append(c.text)
    for t in tried:
        out += [t.what, t.outcome]
    out.append(outcome)
    return [t for t in out if t]


def _extra_corpus(causes: Any, corrections: Any) -> list[str]:
    out: list[str] = []
    for c in causes:
        out += [c.text, *c.evidence]
    for wrong, right, _ in corrections:
        out += [wrong, right]
    return out


# ---- the builder -------------------------------------------------------------------------------


def build_blueprint(
    recommended_option: Any,
    problems: Any,
    requirements: Any,
    owner_facts: Any,
    language: Any = "en",
    staff_inputs: Any = None,
    *,
    root_causes: Any = None,
    options: Any = None,
) -> Blueprint:
    """The blueprint for the recommended option. Never raises: an input that cannot be read gives
    `insufficient_information`.

    recommended_option  an `OptionIn`, an L2-3 Option or OptionSet (see `option_from`), a mapping
    problems            list of problem records (id, title or title_local, user_words, of_total,
                        frequency_text, since_text, expected_outcome) or a mapping id -> record
    requirements        {"constraints": [{kind, text, blocks?, hard?}] or {budget, staff, deadline,
                        cannot_change}, "tried": [{what, outcome}],
                        "expected_outcome": str | {pid: str}}
    owner_facts         the owner's own messages: a string, a list, or a mapping of them
    staff_inputs        {"costs": [{item, amount, currency, source}], "durations": [{text, source,
                        step}], "roles": [{step, role}]}; step ids are the ids this blueprint
                        makes (S1...); requirements may also carry "corrections":
                        [{wrong, right, problem}], kept only when both sides are in the owner facts
    root_causes         causes by problem id (L2-3 RootCause via `cause_from`), or None
    options             the OptionSet the recommendation came from: its other options become the
                        alternatives and why not (also read from recommended_option if it is a set)
    """
    lang = bs.norm_language(language)
    try:
        return _build(
            recommended_option,
            problems,
            requirements,
            owner_facts,
            lang,
            staff_inputs,
            root_causes,
            options,
        )
    except Exception:  # the contract is "never raises"; an unreadable input is missing information
        return Blueprint(
            INSUFFICIENT, lang, missing=(Missing("unreadable", bs.tr(lang, "unreadable")),)
        )


def _insufficient(lang: str, codes: list[tuple[str, str]], known: frozenset[str]) -> Blueprint:
    missing = tuple(Missing(code, bs.tr(lang, key)) for code, key in codes)
    question = ""
    for code, _ in codes:
        if code == "problem":
            question = bs.tr(lang, "q_problem")
        elif code == "option_not_tied":
            question = bs.tr(lang, "q_which")
        if question:
            break
    return Blueprint(
        INSUFFICIENT,
        lang,
        missing=missing,
        next_question=question,
        known_numbers=tuple(sorted(known)),
    )


def _build(
    option_raw: Any,
    problems_raw: Any,
    req_raw: Any,
    facts_raw: Any,
    lang: str,
    staff_raw: Any,
    causes_raw: Any = None,
    options_raw: Any = None,
) -> Blueprint:
    t = bs.tr
    option: OptionIn | None
    if isinstance(option_raw, OptionIn):
        option = option_raw
    elif (
        option_raw is not None
        and _get(option_raw, "options") is not None
        and _get(option_raw, "what") is None
    ):
        option, _ = recommended_from(option_raw)
        options_raw = options_raw if options_raw is not None else option_raw
    else:
        option = option_from(option_raw)

    probs = _problems(problems_raw)
    constraints = _constraints(_get(req_raw, "constraints"))
    tried = _tried(_get(req_raw, "tried"))
    outcome_raw = _get(req_raw, "expected_outcome")
    global_outcome = _text(outcome_raw) if isinstance(outcome_raw, str) else ""
    per_problem_outcome = (
        {str(k): _text(v) for k, v in islice(outcome_raw.items(), MAX_PROBLEMS)}
        if isinstance(outcome_raw, Mapping)
        else {}
    )
    facts = _facts(facts_raw)
    staff = _staff(staff_raw)
    causes = causes_from(causes_raw)
    corrections = parse_corrections(_get(req_raw, "corrections"), " ".join(facts))
    known = _known(
        _corpus(
            facts,
            probs,
            constraints,
            tried,
            global_outcome + " " + " ".join(per_problem_outcome.values()),
            _extra_corpus(causes, corrections),
        ),
        staff,
    )

    # --- is there enough to build from? ---
    gaps: list[tuple[str, str]] = []
    usable = [p for p in probs if p.title or p.words]
    if not usable:
        gaps.append(("problem", "miss_problem"))
    tied: tuple[ProblemIn, ...] = ()
    what = ""
    what_notes: tuple[str, ...] = ()
    if option is None or not option.what.strip():
        gaps.append(("option", "miss_option"))
    elif option.status == "rejected":
        gaps.append(("option", "miss_rejected"))
    else:
        what, what_notes = clean_text(option.what, known)
        if not what:
            gaps.append(("option", "miss_option"))
        wanted = set(option.addresses)
        tied = tuple(p for p in usable if p.id in wanted)
        if usable and not tied:
            gaps.append(("option_not_tied", "miss_not_tied"))
    if gaps or option is None:
        return _insufficient(lang, gaps, known)

    notes: list[str] = list(what_notes)

    def clean(text: str, cap: int = 300) -> str:
        out, n = clean_text(text, known, cap)
        notes.extend(n)
        return out

    tied_ids = tuple(p.id for p in tied)

    # --- option content, cleaned ---
    raw_steps: list[tuple[StepIn, str]] = []
    unlinked = False
    for s in option.steps[:MAX_STEPS]:
        text = clean(s.text)
        if not text:
            continue
        if s.problems and not set(s.problems) & set(tied_ids):
            unlinked = True  # a step that answers none of the stated problems is not built
            continue
        raw_steps.append((s, text))
    no_steps = not raw_steps
    if no_steps:
        raw_steps = [(StepIn(text=what), what)]
    module_names = [m for m in (clean(m, 120) for m in option.modules[:6]) if m] or [what]
    limits = tuple(x for x in (clean(x) for x in option.limits[:6]) if x)

    # --- constraints; a violated hard constraint refuses ---
    step_texts = [txt for _, txt in raw_steps] + module_names + [what]
    rows = _constraint_rows(lang, constraints, tried, option, step_texts, clean)
    violated = [r for r in rows if r.result == "violates" and r.hard]
    if violated:
        return Blueprint(
            REFUSED,
            lang,
            constraints=rows,
            problem_ids=tuple(p.id for p in usable),
            refusal=tuple(
                t(lang, "refused", label=r.text) + (" " + r.reason if r.reason else "")
                for r in violated
            ),
            known_numbers=tuple(sorted(known)),
        )

    unknowns: list[str] = []
    risks: list[RiskLine] = []
    steps: list[Step] = []
    edges: list[Edge] = []

    # --- steps: reviewer, baseline, gated work phases, review, exit ---
    steps.append(
        Step(
            "A1",
            "approval",
            t(lang, "reviewer_step"),
            "reviewer",
            t(lang, "reviewer_done"),
            1,
            source="scaffold",
        )
    )
    tail = ["A1"]
    base_ids: dict[str, str] = {}
    figures = {
        p.id: clean(" ".join(x for x in (p.figure, p.frequency) if x), 160) if p.figure else ""
        for p in tied
    }
    for p in tied:
        if figures[p.id]:
            continue
        sid = f"B{len(base_ids) + 1}"
        base_ids[p.id] = sid
        title = clean(p.title or " ".join(p.words), 120) or p.id
        steps.append(
            Step(
                sid,
                "measure",
                t(lang, "baseline_step", title=title),
                "pi",
                t(lang, "baseline_done", title=title),
                1,
                (p.id,),
                "scaffold",
            )
        )
        tail.append(sid)

    # work steps, ordered by phase (stable)
    staff_roles = dict(staff.roles)
    defaulted = False
    indexed = []
    for i, (s, text) in enumerate(raw_steps, 1):
        phase = 1 + (min(max(s.phase, 1), MAX_PHASES - 1) if s.phase else 1)
        indexed.append((phase, i, s, text))
    indexed.sort(key=lambda x: (x[0], x[1]))
    new_id = {}
    for n, (_, i, s, _) in enumerate(indexed, 1):
        new_id[s.id or f"S{i}"] = f"S{n}"
        new_id.setdefault(f"S{i}", f"S{n}")
    order_unclear = False
    phases_used: list[int] = []
    work: list[Step] = []
    declared: dict[str, list[str]] = {}
    for n, (phase, _i, s, text) in enumerate(indexed, 1):
        sid = f"S{n}"
        role = s.role if s.role in ROLES else ""
        if sid in staff_roles:
            role = staff_roles[sid]
        if not role:
            role = "owner" if option.kind in _OWNER_KINDS else "staff"
            defaulted = True
        done = clean(s.done_check) or t(lang, "action_done", text=tidy(text, 100))
        linked = tuple(x for x in s.problems if x in tied_ids) or tied_ids
        work.append(Step(sid, "action", text, role, done, phase, linked, "option"))
        if phase not in phases_used:
            phases_used.append(phase)
        refs = []
        for a in s.after:
            target = new_id.get(a)
            if target and int(target[1:]) < n:
                refs.append(target)
            else:
                order_unclear = True
        if refs:
            declared[sid] = refs
    prev_sinks = tail
    first_action = work[0].id
    sinks_of_last: list[str] = []
    for phase in phases_used:
        gate = f"G{phase}"
        steps.append(
            Step(
                gate,
                "approval",
                t(lang, "gate_text"),
                "owner",
                t(lang, "gate_done"),
                phase,
                source="scaffold",
            )
        )
        edges += [Edge(x, gate) for x in prev_sinks]
        phase_steps = [w for w in work if w.phase == phase]
        phase_edges: list[Edge] = []
        for k, w in enumerate(phase_steps):
            if w.id in declared:
                phase_edges += [Edge(a, w.id) for a in declared[w.id]]
            elif k > 0:
                phase_edges.append(Edge(phase_steps[k - 1].id, w.id))
        has_in = {e.after for e in phase_edges}
        edges += [Edge(gate, w.id) for w in phase_steps if w.id not in has_in]
        edges += phase_edges
        steps += phase_steps
        has_out = {e.before for e in phase_edges}
        prev_sinks = [w.id for w in phase_steps if w.id not in has_out] or [phase_steps[-1].id]
        sinks_of_last = prev_sinks
    steps.append(
        Step(
            "R1",
            "review",
            t(lang, "review_step"),
            "owner",
            t(lang, "review_done"),
            phases_used[-1],
            tied_ids,
            "scaffold",
        )
    )
    edges += [Edge(x, "R1") for x in sinks_of_last]
    steps.append(
        Step(
            "X1",
            "rollback",
            t(lang, "rollback_text"),
            "owner",
            t(lang, "rollback_done"),
            phases_used[-1],
            source="scaffold",
        )
    )
    edges.append(Edge(first_action, "X1"))
    edges = list(dict.fromkeys(edges))
    if order_unclear:
        unknowns.append(t(lang, "unk_order"))
    if no_steps:
        unknowns.append(t(lang, "unk_option_steps"))
    if defaulted:
        unknowns.append(t(lang, "unk_roles"))

    # --- modules ---
    modules = tuple(
        Module(f"C{i}", name, tied_ids, limits if i == 1 else (), "option")
        for i, name in enumerate(module_names, 1)
    )

    # --- external dependencies ---
    external: list[ExternalDep] = []
    for d in option.dependencies[:MAX_DEPS]:
        text = clean(d.text)
        if text:
            external.append(ExternalDep(f"E{len(external) + 1}", d.kind, text, UNKNOWN, d.blocking))
    for e in external:
        unknowns.append(t(lang, "ext_needed", text=e.text))
        if e.blocking:
            risks.append(RiskLine(t(lang, "risk_blocking", text=e.text), "high", "missing_fact"))
    if not external:
        external.append(ExternalDep("E1", "other", t(lang, "ext_none")))

    # --- responsibilities ---
    resp = tuple(
        Responsibility(role, tuple(s.id for s in steps if s.role == role))
        for role in ROLES
        if any(s.role == role for s in steps)
    )

    # --- cost and timeline: staff only ---
    costs: list[CostLine] = []
    for c in staff.costs:
        costs.append(
            CostLine(
                clean(c.item, 120) or "plan",
                c.amount,
                c.currency,
                clean(c.source, 120) or "staff",
                "staff_supplied",
            )
        )
    if not costs:
        costs.append(CostLine("plan", None, "", "staff", UNKNOWN))
    step_ids = {s.id for s in steps}
    timeline: list[TimeLine] = []
    given: dict[str, StaffDuration] = {}
    plan_given: list[StaffDuration] = []
    for sd in staff.durations:
        if sd.step in step_ids:
            given.setdefault(sd.step, sd)
        else:
            if sd.step:
                unknowns.append(t(lang, "unk_staff_step"))
            plan_given.append(sd)
    for w in work:
        sd2 = given.get(w.id)
        if sd2 is None:
            timeline.append(TimeLine(w.id, "", "", UNKNOWN))
        else:
            timeline.append(
                TimeLine(w.id, clean(sd2.text, 120), clean(sd2.source, 120), "staff_supplied")
            )
    plan_lines = [
        TimeLine("plan", clean(x.text, 120), clean(x.source, 120), "staff_supplied")
        for x in plan_given
    ]
    plan_lines += [
        TimeLine("plan", clean(c2.text, 200), "owner", "owner_stated")
        for c2 in constraints
        if c2.kind == "deadline"
    ]
    timeline += plan_lines or [TimeLine("plan", "", "", UNKNOWN)]
    if staff.dropped:
        unknowns.append(t(lang, "unk_staff_dropped"))

    # --- risks and unknowns ---
    for r in option.risks[:MAX_RISKS]:
        text = clean(r.text)
        if text:
            risks.append(
                RiskLine(text, r.level if r.level in ("low", "medium", "high") else "low", "option")
            )
    outcomes: dict[str, str] = {}
    for p in tied:
        o = clean(
            p.expected_outcome
            or per_problem_outcome.get(p.id, "")
            or global_outcome
            or option.expected_outcome
        )
        outcomes[p.id] = o
        title = clean(p.title or " ".join(p.words), 120) or p.id
        if not figures[p.id]:
            risks.append(
                RiskLine(t(lang, "risk_no_baseline", title=title), "medium", "missing_fact")
            )
        if not o:
            risks.append(
                RiskLine(t(lang, "risk_no_outcome", title=title), "medium", "missing_fact")
            )
    kinds = {c.kind for c in constraints}
    for kind, key in (
        ("budget", "unk_budget"),
        ("staff", "unk_staff"),
        ("deadline", "unk_deadline"),
    ):
        if kind not in kinds:
            unknowns.append(t(lang, key))
    for code, key in (
        ("promise", "unk_promise"),
        ("credential", "unk_credential"),
        ("money", "unk_money"),
        ("number", "unk_number"),
    ):
        if code in notes:
            unknowns.append(t(lang, key))

    # --- success measures and acceptance ---
    measures: list[Measure] = []
    criteria: list[Criterion] = []
    for p in tied:
        title = clean(p.title or " ".join(p.words), 120) or p.id
        baseline = figures[p.id]
        o = outcomes[p.id]
        target = o if numbers_in(o) else ""
        measures.append(
            Measure(
                f"SM{len(measures) + 1}",
                p.id,
                t(lang, "measure_what", title=title),
                baseline,
                "owner" if baseline else f"step {base_ids.get(p.id, 'B1')}",
                target,
                "owner" if target else "",
            )
        )
        if o:
            criteria.append(
                Criterion(
                    f"AC{len(criteria) + 1}",
                    t(lang, "acc_outcome", outcome=o),
                    ("R1",),
                    "owner",
                    (p.id,),
                )
            )
            red = _reduce_number(o)
            if red:
                criteria.append(
                    Criterion(
                        f"AC{len(criteria) + 1}",
                        t(lang, "acc_at_or_below", title=title, n=red),
                        ("R1",),
                        "owner",
                        (p.id,),
                    )
                )
        else:
            criteria.append(
                Criterion(
                    f"AC{len(criteria) + 1}",
                    t(lang, "acc_no_outcome", title=title),
                    ("R1",),
                    "owner",
                    (p.id,),
                )
            )
    criteria.append(
        Criterion(
            f"AC{len(criteria) + 1}",
            t(lang, "acc_steps"),
            tuple(w.id for w in work),
            "owner",
            tied_ids,
        )
    )

    # --- milestones: tied to steps ---
    milestones = [
        Milestone(
            "M1",
            t(lang, "milestone_start"),
            tuple(s.id for s in steps if s.phase == 1),
            t(lang, "milestone_check"),
        )
    ]
    for phase in phases_used:
        milestones.append(
            Milestone(
                f"M{len(milestones) + 1}",
                t(lang, "milestone_work"),
                tuple(s.id for s in steps if s.phase == phase and s.kind in ("approval", "action")),
                t(lang, "milestone_check"),
            )
        )
    milestones.append(
        Milestone(
            f"M{len(milestones) + 1}",
            t(lang, "milestone_end"),
            ("R1", "X1"),
            t(lang, "milestone_check"),
        )
    )

    titles = "; ".join(clean(p.title or " ".join(p.words), 120) or p.id for p in tied)
    summary = Summary(
        tidy(t(lang, "summary", titles=titles.rstrip(_STOP), what=what.rstrip(_STOP)), 600),
        tied_ids,
        option.id,
    )
    # --- what explains and links the plan ---
    if unlinked:
        unknowns.append(t(lang, "unk_unlinked"))
    steps = [dataclasses.replace(x, problems=x.problems or tied_ids) for x in steps]
    risks = [dataclasses.replace(r, problems=r.problems or tied_ids) for r in risks]
    external = [dataclasses.replace(e, problems=e.problems or tied_ids) for e in external]
    alts = alternatives_from(options_raw, option.id) if options_raw is not None else ()
    problem_rows = tuple(
        ProblemRow(
            p.id,
            clean(p.title or " ".join(p.words), 120) or p.id,
            tuple(w for w in (clean(x) for x in p.words[:2]) if w),
        )
        for p in usable
    )
    cause_tuple, cause_items = cause_rows(lang, causes, tied, clean)
    reason_tuple = reason_rows(lang, option, rows, titles, tied_ids, clean)
    alt_tuple = alternative_rows(lang, alts, tied_ids, clean)
    fact_tuple = fact_rows(
        lang, tied, constraints, tried, corrections, outcomes, figures, clean, tied_ids
    )
    if not fact_tuple:  # whatever was cut, the problem the owner stated is still a fact
        first = next((r for r in problem_rows if r.id in tied_ids), problem_rows[0])
        fact_tuple = (FactRow(first.id, "said", first.title),)
    data_tuple = data_rows(lang, option, tied_ids, clean)
    perms = dict(option.permissions)
    resp = tuple(
        dataclasses.replace(
            r,
            permissions=(clean(perms[r.role]),)
            if perms.get(r.role) and clean(perms[r.role])
            else (),
        )
        for r in resp
    )
    open_tuple = open_items(
        lang,
        tied_ids,
        cause_items,
        rows,
        tuple(external),
        tuple(risks),
        tuple(costs),
        tuple(timeline),
        alt_tuple,
        tuple(measures),
    )
    return Blueprint(
        status=READY,
        language=lang,
        summary=summary,
        problems=problem_rows,
        facts=fact_tuple,
        causes=cause_tuple,
        reasons=reason_tuple,
        alternatives=alt_tuple,
        modules=modules,
        data=data_tuple,
        open_items=open_tuple,
        steps=tuple(steps),
        edges=tuple(edges),
        external=tuple(external),
        responsibilities=resp,
        costs=tuple(costs),
        timeline=tuple(timeline),
        risks=tuple(risks),
        unknowns=tuple(dict.fromkeys(unknowns)),
        milestones=tuple(milestones),
        acceptance=tuple(criteria),
        success=tuple(measures),
        constraints=rows,
        problem_ids=tuple(p.id for p in usable),
        known_numbers=tuple(sorted(known)),
    )


def _reduce_number(outcome: str) -> str:
    """The first number of an owner's outcome asking for fewer ("kam se kam 5"), else ''.
    The number is the owner's own; nothing here sets a target."""
    if not _REDUCE.search(fold(outcome)):
        return ""
    found = re.search(r"(?<![A-Za-z_\d])\d+(?:[.,]\d+)?", fold_digits(outcome))
    return canon_number(found.group()) if found else ""


def _constraint_rows(
    lang: str,
    constraints: tuple[ConstraintIn, ...],
    tried: tuple[TriedIn, ...],
    option: OptionIn,
    step_texts: list[str],
    clean: Callable[..., str],
) -> tuple[ConstraintRow, ...]:
    t = bs.tr
    checks = {c.constraint: c for c in option.checks if c.constraint}
    hay = fold(" ".join(step_texts))
    rows: list[ConstraintRow] = []
    for c in constraints:
        hit = next((b for b in c.blocks if _contains(hay, b)), None)
        chk = checks.get(c.label) or (checks.get(c.kind) if c.kind in _SCALAR_KINDS else None)
        text = t(lang, "cons_hidden") if c.kind == "budget" else clean(c.text, 200)
        if hit is not None:
            result, reason = "violates", t(lang, "cons_block", phrase=clean(hit, 60))
        elif chk is not None and chk.result == "violates":
            result, reason = "violates", clean(chk.why) or t(lang, "cons_block", phrase=text)
        elif chk is not None and chk.result == "ok":
            result, reason = "ok", clean(chk.why) or t(lang, "cons_ok")
        elif chk is not None:
            result, reason = "unknown", clean(chk.why) or t(lang, "cons_not_checked")
        else:
            result, reason = "unknown", t(lang, "cons_not_checked")
        rows.append(ConstraintRow(c.label, c.kind, text, result, reason, c.hard))
    for i, tr_ in enumerate(tried, 1):
        label = f"tried#{i}"
        chk = checks.get(label)
        text = clean(tr_.what + ((" - " + tr_.outcome) if tr_.outcome else ""), 200)
        if chk is not None and chk.result == "violates":
            result, reason = "violates", clean(chk.why) or t(lang, "cons_tried")
        elif chk is not None and chk.result == "ok":
            result, reason = "ok", clean(chk.why) or t(lang, "cons_ok")
        elif _repeats(tr_.what, hay):
            result, reason = "unknown", t(lang, "cons_tried")
        else:
            result, reason = (
                "unknown",
                clean(chk.why) if chk is not None and chk.why else t(lang, "cons_not_checked"),
            )
        rows.append(ConstraintRow(label, "tried", text, result, reason, True))
    if not rows:
        rows.append(
            ConstraintRow(
                "none", "other", t(lang, "cons_none"), "unknown", t(lang, "cons_none_why"), False
            )
        )
    return tuple(rows)


def _contains(hay: str, phrase: str) -> bool:
    """The phrase as whole words in the folded text ("app" is not in "application")."""
    p = fold(phrase)
    if not p:
        return False
    return re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", hay) is not None


def _repeats(what: str, hay: str) -> bool:
    """A rough overlap test: most of the long words of what was tried appear in the option text.
    It can only raise a flag for a person; it never decides."""
    words = {w for w in re.findall(r"\w{4,}", fold(what))}
    if not words:
        return False
    shared = sum(1 for w in words if w in hay)
    return shared >= max(2, (len(words) + 1) // 2)


# ---- the independent check ---------------------------------------------------------------------


def blueprint_issues(
    blueprint: Blueprint,
    owner_facts: Any = None,
    problems: Any = None,
    requirements: Any = None,
    staff_inputs: Any = None,
    root_causes: Any = None,
) -> tuple[Issue, ...]:
    """Completeness and honesty issues of a blueprint (empty means clean). Never raises.

    Pass the original owner facts, problems, requirements and staff inputs to check every number in
    the blueprint against the SOURCES; with none of them it checks against the numbers the builder
    recorded in `blueprint.known_numbers` (weaker: a hand-edited blueprint could carry
    its own list).
    The one-question rule is the caller's, not checked here."""
    try:
        if all(x is None for x in (owner_facts, problems, requirements, staff_inputs, root_causes)):
            known: frozenset[str] = frozenset(getattr(blueprint, "known_numbers", ()) or ())
        else:
            probs = _problems(problems)
            cons = _constraints(_get(requirements, "constraints"))
            trd = _tried(_get(requirements, "tried"))
            oc = _get(requirements, "expected_outcome")
            oc_text = " ".join(
                [oc]
                if isinstance(oc, str)
                else [str(v) for v in oc.values()]
                if isinstance(oc, Mapping)
                else []
            )
            facts = _facts(owner_facts)
            extra = _extra_corpus(
                causes_from(root_causes),
                parse_corrections(_get(requirements, "corrections"), " ".join(facts)),
            )
            known = _known(_corpus(facts, probs, cons, trd, oc_text, extra), _staff(staff_inputs))
        return check_blueprint(blueprint, known)
    except Exception:
        return (Issue("BP-MALFORMED", "blueprint", "could not check the blueprint"),)
