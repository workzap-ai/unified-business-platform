"""PS-4: the parts of a blueprint that explain and link it: causes with their status, the
reasons for the recommendation, the alternatives and why not, the data records and connections,
facts with corrections, and what is still open.

Pure helpers for `blueprint_build`; nothing here raises. Two documented adapters read the L2-3
records by attribute name only (no import, no construction of evidence):

  cause_from(root_cause)     RootCause: text, status, evidence_for[words, verified]
  alternatives_from(set)     OptionSet: options[id, what, status, addresses, rejected_because,
                             constraint_checks, dependencies], recommended_id

A cause is stated as the owner's only when its status is owner_said or confirmed AND the owner's
words are attached; otherwise it is labelled "pi's guess, not confirmed".
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from itertools import islice
from typing import Any

from app.modules.pi import blueprint_strings as bs
from app.modules.pi.blueprint_checks import fold, tidy
from app.modules.pi.blueprint_types import (
    MAX_PROBLEMS,
    AlternativeRow,
    AltIn,
    CauseIn,
    CauseRow,
    ConstraintIn,
    ConstraintRow,
    CostLine,
    DataRow,
    ExternalDep,
    FactRow,
    Measure,
    OpenItem,
    OptionIn,
    ProblemIn,
    ReasonRow,
    RiskLine,
    TimeLine,
    TriedIn,
)

CAUSE_STATUSES = ("pi_inferred", "owner_said", "confirmed")
OWNER_CAUSE = ("owner_said", "confirmed")
MAX_ALTS = 6
MAX_ROWS = 40
Clean = Callable[..., str]


def get_attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    try:
        return getattr(obj, name, default)
    except Exception:  # a property that raises reads as absent
        return default


def seq_of(value: Any, cap: int) -> tuple[Any, ...]:
    """The first `cap` items of a list or tuple; anything else is empty."""
    if isinstance(value, list | tuple):
        return tuple(islice(value, cap))
    return ()


def short(value: Any, cap: int = 300) -> str:
    return tidy(value, cap) if isinstance(value, str) else ""


def shorts(value: Any, n: int, cap: int = 300) -> tuple[str, ...]:
    return tuple(t for t in (short(v, cap) for v in seq_of(value, n)) if t)


def _loose(obj: Any) -> bool:
    return obj is None or isinstance(obj, str | int | float | bool | list | tuple)


# ---- adapters ------------------------------------------------------------


def cause_from(cause: Any) -> CauseIn | None:
    """A `RootCause` (or the stored B2a dict {"text", "status", "evidence": {"words"}}).
    An owner status with no owner words attached reads as pi_inferred: it is not trusted."""
    if _loose(cause):
        return None
    text = short(get_attr(cause, "text"))
    if not text:
        return None
    status = short(get_attr(cause, "status"), 20)
    if status not in CAUSE_STATUSES:
        status = "pi_inferred"
    words: list[str] = []
    verified = False
    for ev in seq_of(get_attr(cause, "evidence_for"), 6):
        words += shorts(get_attr(ev, "words"), 4, 200)
        verified = verified or get_attr(ev, "verified") is True
    proof = get_attr(cause, "evidence")
    if isinstance(proof, Mapping):
        words += shorts(proof.get("words"), 4, 200)
    if status in OWNER_CAUSE and not words:
        status = "pi_inferred"
    return CauseIn(short(get_attr(cause, "problem"), 40), text, status, tuple(words[:6]), verified)


def causes_from(raw: Any) -> tuple[CauseIn, ...]:
    """Causes by problem id: a mapping id -> cause (or list of causes), a list of causes that carry
    a `problem`, or one cause with no problem id."""
    out: list[CauseIn] = []
    if isinstance(raw, Mapping) and "text" not in raw:
        for pid, value in islice(raw.items(), MAX_PROBLEMS):
            items = seq_of(value, 3) if isinstance(value, list | tuple) else (value,)
            for it in items:
                c = cause_from(it)
                if c is not None:
                    out.append(replace(c, problem=short(str(pid), 40)))
    elif isinstance(raw, list | tuple):
        for it in islice(raw, MAX_PROBLEMS * 3):
            c = cause_from(it)
            if c is not None:
                out.append(c)
    else:
        c = cause_from(raw)
        if c is not None:
            out.append(c)
    return tuple(out[: MAX_PROBLEMS * 3])


def alternatives_from(option_set: Any, recommended_id: str = "") -> tuple[AltIn, ...]:
    """The options of an `OptionSet` other than the recommended one, as AltIn."""
    rid = recommended_id or short(get_attr(option_set, "recommended_id"), 40)
    out: list[AltIn] = []
    for o in seq_of(get_attr(option_set, "options"), 20):
        oid = short(get_attr(o, "id"), 40)
        if _loose(o) or (rid and oid == rid):
            continue
        checks = seq_of(get_attr(o, "constraint_checks"), 20)
        violated = tuple(
            f"{short(get_attr(c, 'constraint'), 40)}: {short(get_attr(c, 'why'), 200)}".strip(": ")
            for c in checks
            if get_attr(c, "result") == "violates"
        )
        unknown = tuple(
            short(get_attr(c, "constraint"), 40)
            for c in checks
            if get_attr(c, "result") == "unknown"
        )
        blocked = tuple(
            short(get_attr(d, "text"), 200)
            for d in seq_of(get_attr(o, "dependencies"), 12)
            if get_attr(d, "blocking") is True
        )
        status = short(get_attr(o, "status"), 20)
        out.append(
            AltIn(
                oid,
                short(get_attr(o, "what")),
                status if status in ("alternative", "rejected", "recommended") else "alternative",
                short(get_attr(o, "rejected_because"), 300),
                violated,
                unknown,
                blocked,
                shorts(get_attr(o, "addresses"), MAX_PROBLEMS, 40),
            )
        )
    return tuple(out[:MAX_ALTS])


def parse_corrections(raw: Any, corpus: str) -> tuple[tuple[str, str, str], ...]:
    """(wrong, right, problem) for each correction whose BOTH sides really occur in the owner's own
    words; one that does not is dropped (it would be invented)."""
    hay = fold(corpus)
    out = []
    for c in seq_of(raw, 8):
        wrong, right = short(get_attr(c, "wrong"), 60), short(get_attr(c, "right"), 60)
        if wrong and right and fold(wrong) in hay and fold(right) in hay:
            out.append((wrong, right, short(get_attr(c, "problem"), 40)))
    return tuple(out)


# ---- rows ------------------------------------------------------------


def cause_rows(
    lang: str, causes: tuple[CauseIn, ...], tied: tuple[ProblemIn, ...], clean: Clean
) -> tuple[tuple[CauseRow, ...], list[OpenItem]]:
    rows: list[CauseRow] = []
    items: list[OpenItem] = []
    ids = {p.id for p in tied}
    for p in tied:
        mine = [c for c in causes if c.problem == p.id] or (
            [c for c in causes if not c.problem] if len(tied) == 1 else []
        )
        if not mine:
            rows.append(CauseRow(p.id, bs.tr(lang, "open_cause_missing"), "unknown"))
            items.append(OpenItem("missing", bs.tr(lang, "open_cause_missing"), (p.id,)))
            continue
        for c in mine[:2]:
            text = clean(c.text)
            if not text:
                continue
            ev = tuple(e for e in (clean(w, 200) for w in c.evidence) if e)
            status = c.status if (c.status not in OWNER_CAUSE or ev) else "pi_inferred"
            rows.append(CauseRow(p.id, text, status, ev))
            if status != "confirmed":
                items.append(OpenItem("decision", bs.tr(lang, "open_cause", text=text), (p.id,)))
    del ids
    return tuple(rows), items


def reason_rows(
    lang: str,
    option: OptionIn,
    constraint_rows: tuple[ConstraintRow, ...],
    titles: str,
    tied_ids: tuple[str, ...],
    clean: Clean,
) -> tuple[ReasonRow, ...]:
    t = bs.tr
    rows = [ReasonRow(t(lang, "reason_answers", titles=titles), tied_ids)]
    for c in constraint_rows:
        if c.result == "ok":
            rows.append(
                ReasonRow(t(lang, "reason_check_ok", label=c.label.replace("#", "_")), tied_ids)
            )
    if not any(d.blocking for d in option.dependencies):
        rows.append(ReasonRow(t(lang, "reason_no_block"), tied_ids))
    if option.effort or option.reversibility:
        rows.append(
            ReasonRow(
                t(
                    lang,
                    "reason_effort",
                    effort=short(option.effort, 20) or "-",
                    rev=short(option.reversibility, 20) or "-",
                ),
                tied_ids,
            )
        )
    benefit = clean(option.benefit)
    if benefit:
        rows.append(ReasonRow(t(lang, "reason_benefit", benefit=benefit), tied_ids))
    return tuple(rows[:MAX_ROWS])


def alternative_rows(
    lang: str, alts: tuple[AltIn, ...], tied_ids: tuple[str, ...], clean: Clean
) -> tuple[AlternativeRow, ...]:
    t = bs.tr
    rows: list[AlternativeRow] = []
    for a in alts[:MAX_ALTS]:
        what = clean(a.what)
        if not what:
            continue
        parts: list[str] = []
        why = clean(a.why_not)
        if why:
            parts.append(t(lang, "alt_rejected", why=why))
        for v in a.violated:
            label, _, reason = v.partition(": ")
            parts.append(
                t(lang, "alt_violates", label=label.replace("#", "_"), why=clean(reason)).strip()
            )
        parts += [t(lang, "alt_unknown", label=u.replace("#", "_")) for u in a.unknown[:4]]
        parts += [t(lang, "alt_blocked", text=clean(b)) for b in a.blocked_by[:2] if clean(b)]
        text = "\n".join(parts) or t(lang, "alt_lower")
        linked = tuple(x for x in a.addresses if x in tied_ids) or tied_ids
        rows.append(AlternativeRow(a.id, what, a.status, text, linked))
    if not rows:
        rows.append(AlternativeRow("", t(lang, "alt_none"), "none", "", tied_ids))
    return tuple(rows)


def data_rows(
    lang: str, option: OptionIn, tied_ids: tuple[str, ...], clean: Clean
) -> tuple[DataRow, ...]:
    rows = [
        DataRow("entity", n, "named", tied_ids)
        for n in (clean(x, 120) for x in option.entities[:8])
        if n
    ]
    rows += [
        DataRow("integration", n, "named", tied_ids)
        for n in (clean(x, 120) for x in option.integrations[:8])
        if n
    ]
    if not rows:
        rows.append(DataRow("none", bs.tr(lang, "data_none"), UNKNOWN_STATUS, tied_ids))
    return tuple(rows)


UNKNOWN_STATUS = "unknown"


def fact_rows(
    lang: str,
    tied: tuple[ProblemIn, ...],
    constraints: tuple[ConstraintIn, ...],
    tried: tuple[TriedIn, ...],
    corrections: tuple[tuple[str, str, str], ...],
    outcomes: Mapping[str, str],
    figures: Mapping[str, str],
    clean: Clean,
    tied_ids: tuple[str, ...],
) -> tuple[FactRow, ...]:
    rows: list[FactRow] = []
    for p in tied:
        for w in p.words[:2]:
            c = clean(w)
            if c:
                rows.append(FactRow(p.id, "said", c))
        for kind, val in (
            ("figure", figures.get(p.id, "")),
            ("frequency", ""),
            ("since", p.since),
            ("outcome", outcomes.get(p.id, "")),
        ):
            c = clean(val, 160)
            if c:
                rows.append(FactRow(p.id, kind, c))
    for k in constraints:
        text = bs.tr(lang, "cons_hidden") if k.kind == "budget" else clean(k.text, 200)
        if text:
            rows.append(FactRow("", "constraint", text))
    for tr_ in tried:
        text = clean(tr_.what + ((" - " + tr_.outcome) if tr_.outcome else ""), 200)
        if text:
            rows.append(FactRow("", "tried", text))
    for wrong, right, pid in corrections:
        rows.append(
            FactRow(
                pid if pid in tied_ids else "", "correction", clean(right, 80), clean(wrong, 80)
            )
        )
    return tuple(rows[:MAX_ROWS])


def open_items(
    lang: str,
    tied_ids: tuple[str, ...],
    cause_items: list[OpenItem],
    constraint_rows: tuple[ConstraintRow, ...],
    external: tuple[ExternalDep, ...],
    risks: tuple[RiskLine, ...],
    costs: tuple[CostLine, ...],
    timeline: tuple[TimeLine, ...],
    alternatives: tuple[AlternativeRow, ...],
    measures: tuple[Measure, ...],
) -> tuple[OpenItem, ...]:
    t = bs.tr
    items: list[OpenItem] = list(cause_items)
    items += [
        OpenItem("missing", r.text, r.problems or tied_ids)
        for r in risks
        if r.source == "missing_fact"
    ]
    items += [
        OpenItem("decision", t(lang, "open_constraint", text=c.text), tied_ids)
        for c in constraint_rows
        if c.result == "unknown"
    ]
    items += [
        OpenItem("missing", t(lang, "ext_needed", text=e.text), e.problems or tied_ids)
        for e in external
        if e.status == UNKNOWN_STATUS and e.text
    ]
    if all(c.amount is None for c in costs):
        items.append(OpenItem("missing", t(lang, "open_costs"), tied_ids))
    if not any(x.duration for x in timeline):
        items.append(OpenItem("missing", t(lang, "open_time"), tied_ids))
    unchecked = [a for a in alternatives if a.id and a.why_not]
    if any(a.status != "rejected" for a in unchecked):
        ids = ", ".join(a.id for a in unchecked if a.status != "rejected")
        items.append(OpenItem("decision", t(lang, "open_alt", text=ids), tied_ids))
    items.append(OpenItem("decision", t(lang, "open_decision"), tied_ids))
    return tuple(items[:MAX_ROWS])
