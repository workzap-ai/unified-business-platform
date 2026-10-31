# ruff: noqa: E501
"""PS-10: the 14 owner checks (SR-01..SR-14) plus SR-15 and SR-16, each a pure function.

Each check takes a `DraftResult` and returns a `CheckResult`. None of them raises, calls a model or a
database, or reads more than the capped input. `None` on a supplied-input field means the caller did
not supply it: for a check that needs it, that is UNKNOWN, never PASS.

A draft "claims a solution" when it has a recommended option, a blueprint or kind solution/blueprint;
a plain question turn claims nothing, so the solution checks are NOT_APPLICABLE for it.

Spec: v1.6 section 18 (pre-send checks; regenerate once; a safe fallback after two failures),
18.3 canOffer, 18.5 alreadyAnswered; v1.5 Part 18; the owner's 14-point self-review list.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.modules.pi import self_review_text as T
from app.modules.pi.self_review_types import (
    CAUSE_STATUSES,
    CONTEXT_SOURCES,
    FAIL,
    GATE_STATUSES,
    GATE_UNKNOWN,
    GENERIC,
    GROUNDED_FACT,
    HYPOTHESIS,
    LANGS,
    LINKED,
    MAX_ITEM_TEXT,
    MAX_ITEMS,
    NOT_APPLICABLE,
    PASS,
    PI_INFERRED,
    REL_UNKNOWN,
    REPEATS_TRIED,
    SATISFIED,
    UNKNOWN,
    UNLINKED,
    VIOLATED,
    VIOLATES,
    CheckResult,
    DraftResult,
    OptionIn,
)

NAMES = {
    "SR-01": "understood the actual problem",
    "SR-02": "retrieved existing context",
    "SR-03": "identified connected problems",
    "SR-04": "facts kept apart from hypotheses",
    "SR-05": "root causes carry evidence or a hypothesis label",
    "SR-06": "every known constraint accounted for",
    "SR-07": "irrelevant or generic ideas rejected",
    "SR-08": "previously tried solutions checked",
    "SR-09": "unknown treated honestly",
    "SR-10": "recommended option is feasible",
    "SR-11": "recommended option addresses the root problem",
    "SR-12": "dependencies and risks included",
    "SR-13": "reply in the owner's language and script",
    "SR-14": "owner can understand and act",
    "SR-15": "one question, and it is last",
    "SR-16": "a proposal is not worded as done",
}
BAD_KINDS = (UNLINKED, GENERIC, REPEATS_TRIED, VIOLATES)


def _r(
    cid: str,
    status: str,
    evidence: tuple[str, ...] | list[str] = (),
    repair: str = "",
    arg: str = "",
    tag: str = "",
) -> CheckResult:
    return CheckResult(
        cid,
        NAMES[cid],
        status,
        tuple(str(e)[:MAX_ITEM_TEXT] for e in evidence[:6]),
        repair,
        arg,
        tag,
    )


def _seq(x: object) -> tuple[Any, ...]:
    return tuple(x)[:MAX_ITEMS] if isinstance(x, (tuple, list)) else ()


def _claims_solution(d: DraftResult) -> bool:
    return (
        d.recommended is not None or d.blueprint is not None or d.kind in ("solution", "blueprint")
    )


def _all_options(d: DraftResult) -> list[OptionIn]:
    seen: set[str] = set()
    out: list[OptionIn] = []
    for o in (*([d.recommended] if d.recommended else []), *_seq(d.options)):
        if isinstance(o, OptionIn) and o.id not in seen:
            seen.add(o.id)
            out.append(o)
    return out


def _is_recommended(d: DraftResult, o: OptionIn) -> bool:
    return d.recommended is not None and d.recommended.id == o.id


def _shown(d: DraftResult, o: OptionIn) -> bool:
    return o.viable or _is_recommended(d, o)


def _rel(o: OptionIn) -> str:
    return o.relevance if o.relevance in (LINKED, *BAD_KINDS) else REL_UNKNOWN


def _known_numbers(d: DraftResult) -> set[str]:
    nums = T.numbers(d.owner_text)
    for f in _seq(d.facts):
        nums |= T.numbers(getattr(f, "text", ""))
    for c in _seq(d.constraints):
        nums |= T.numbers(getattr(c, "text", ""))
    for t in _seq(d.tried_solutions):
        nums |= T.numbers(t)
    for c in _seq(d.root_causes):
        nums |= T.numbers(getattr(c, "text", ""))
    return nums


# ---------------------------------------------------------------- SR-01 .. SR-03


def sr01(d: DraftResult) -> CheckResult:
    if not _claims_solution(d):
        return _r("SR-01", NOT_APPLICABLE, ["no solution is claimed"])
    if d.noted_problems is None:
        return _r("SR-01", UNKNOWN, ["noted problems not supplied"], "ask_detail")
    probs = _seq(d.noted_problems)
    good = [
        p
        for p in probs
        if getattr(p, "owner_worded", False)
        and getattr(p, "title", "").strip()
        and getattr(p, "fact_count", 0) >= 1
    ]
    if good:
        return _r("SR-01", PASS, [f"problem {good[0].id}: owner-worded title with stated facts"])
    if not probs:
        return _r("SR-01", FAIL, ["no problem is noted"], "ask_detail")
    return _r(
        "SR-01",
        FAIL,
        ["problems are only a category, or have no owner wording or no facts"],
        "ask_detail",
    )


def sr02(d: DraftResult) -> CheckResult:
    q = d.questions
    answered = bool(q and q.already_answered)
    c = d.context
    if c is None:
        if answered:
            return _r("SR-02", FAIL, ["asked something the records answer"], "drop_question")
        return _r("SR-02", UNKNOWN, ["context retrieval not reported"], "ask_detail")
    sources = [s for s in _seq(c.sources) if s in CONTEXT_SOURCES]
    if answered:
        return _r("SR-02", FAIL, ["asked something the records answer"], "drop_question")
    if c.records_exist and not sources:
        return _r("SR-02", FAIL, ["records exist but no source was retrieved"], "retrieve_context")
    if c.retrieved is None:
        return _r("SR-02", UNKNOWN, ["retrieval not reported"])
    if c.retrieved is False and c.records_exist is not False:
        return _r("SR-02", FAIL, ["nothing retrieved and records may exist"], "retrieve_context")
    return _r("SR-02", PASS, [f"sources: {', '.join(sources) or 'none (no records)'}"])


def sr03(d: DraftResult) -> CheckResult:
    if d.noted_problems is None:
        return _r(
            "SR-03",
            NOT_APPLICABLE if not _claims_solution(d) else UNKNOWN,
            ["problems not supplied"],
        )
    probs = _seq(d.noted_problems)
    if len(probs) <= 1:
        return _r("SR-03", NOT_APPLICABLE, ["one problem or none"])
    ids = {getattr(p, "id", "") for p in probs}
    edges = [
        e
        for e in _seq(d.connected_problems)
        if isinstance(e, tuple) and len(e) == 2 and set(e) <= ids
    ]
    if edges:
        return _r("SR-03", PASS, [f"{len(edges)} connection(s)"])
    if d.problems_unrelated:
        return _r("SR-03", PASS, ["marked explicitly as unrelated"])
    return _r(
        "SR-03",
        FAIL,
        [f"{len(probs)} problems, no connection and no 'unrelated' marker"],
        "connect_problems",
    )


# ---------------------------------------------------------------- SR-04 .. SR-06


def sr04(d: DraftResult) -> CheckResult:
    if not d.reply_text:
        return _r("SR-04", NOT_APPLICABLE, ["no reply text"])
    if d.facts is None and d.root_causes is None:
        if _claims_solution(d):
            return _r("SR-04", UNKNOWN, ["facts and causes not supplied"], "label_causes")
        return _r("SR-04", NOT_APPLICABLE, ["no facts or causes involved"])
    sents = T.sentences(d.reply_text)
    bad: list[str] = []
    risky: list[tuple[str, str]] = []
    for f in _seq(d.facts):
        if getattr(f, "status", "") not in GROUNDED_FACT:
            risky.append(("fact", getattr(f, "text", "")))
    for c in _seq(d.root_causes):
        st = getattr(c, "status", "")
        if st not in CAUSE_STATUSES:
            bad.append(f"cause {getattr(c, 'id', '?')} has no status")
        elif st in (PI_INFERRED, HYPOTHESIS):
            risky.append(("cause", getattr(c, "text", "")))
    for kind, text in risky:
        key = T.content_words(text)
        if not key:
            continue
        need = max(1, int(len(key) * 0.6 + 0.999))
        for s in sents:
            if len(key & T.content_words(s)) >= need and not T.has_hedge(s):
                bad.append(f"{kind} not stated by the owner is worded as fact: {text[:60]}")
                break
    if bad:
        arg = "causes" if any(b.startswith("cause") for b in bad) else "facts"
        return _r("SR-04", FAIL, bad, "label_causes", arg)
    return _r("SR-04", PASS, ["every inferred item is hedged and every cause has a status"])


def sr05(d: DraftResult) -> CheckResult:
    rec = d.recommended
    if rec is None:
        return _r("SR-05", NOT_APPLICABLE, ["no recommended option"])
    if d.root_causes is None:
        return _r("SR-05", UNKNOWN, ["root causes not supplied"], "label_causes")
    cause = (
        next((c for c in _seq(d.root_causes) if getattr(c, "id", None) == rec.cause_id), None)
        if rec.cause_id
        else None
    )
    if cause is None:
        if rec.learn_first:
            return _r("SR-05", PASS, ["learn-first: no cause claimed"])
        return _r("SR-05", FAIL, ["the recommended option names no known cause"], "label_causes")
    st = getattr(cause, "status", "")
    evidence = [e for e in _seq(getattr(cause, "evidence", ())) if str(e).strip()]
    if evidence or st in (HYPOTHESIS, *GROUNDED_FACT) or rec.learn_first:
        return _r("SR-05", PASS, [f"cause {cause.id}: evidence or hypothesis label"])
    return _r(
        "SR-05",
        FAIL,
        [f"cause {cause.id} has no evidence, no owner statement and no hypothesis label"],
        "label_causes",
        "causes",
    )


def sr06(d: DraftResult) -> CheckResult:
    if not (_claims_solution(d) or d.options):
        return _r("SR-06", NOT_APPLICABLE, ["no option or solution"])
    if d.stored_constraint_ids is None:
        return _r("SR-06", UNKNOWN, ["stored constraints not supplied"], "list_constraints")
    stored = [s for s in _seq(d.stored_constraint_ids) if isinstance(s, str)]
    table = {getattr(c, "id", ""): c for c in _seq(d.constraints)}
    missing = [s for s in stored if s not in table]
    nostatus = [i for i, c in table.items() if getattr(c, "gate", "") not in GATE_STATUSES]
    if missing:
        return _r(
            "SR-06",
            FAIL,
            [f"constraint dropped silently: {m}" for m in missing],
            "list_constraints",
        )
    if nostatus:
        return _r(
            "SR-06",
            FAIL,
            [f"constraint without a status: {i}" for i in nostatus],
            "list_constraints",
        )
    unk = [i for i, c in table.items() if c.gate == GATE_UNKNOWN]
    note = f"{len(table)} constraint(s) in the table" + (
        f"; unknown listed: {', '.join(unk)}" if unk else ""
    )
    return _r("SR-06", PASS, [note])


# ---------------------------------------------------------------- SR-07 .. SR-09


def sr07(d: DraftResult) -> CheckResult:
    opts = _all_options(d)
    bp = d.blueprint
    unlinked = _seq(bp.unlinked_items) if bp else ()
    if not opts and not unlinked:
        return _r("SR-07", NOT_APPLICABLE, ["no option listed"])
    bad = [
        o
        for o in opts
        if _shown(d, o)
        and _rel(o) in BAD_KINDS
        and not (_rel(o) == REPEATS_TRIED and o.improves_on_tried)
    ]
    if bad:
        return _r(
            "SR-07",
            FAIL,
            [f"{o.id} is {_rel(o)} but shown as viable" for o in bad],
            "drop_option",
            bad[0].id,
        )
    if unlinked:
        return _r(
            "SR-07",
            FAIL,
            [f"blueprint item not tied to the problem: {u}" for u in unlinked],
            "drop_item",
            str(unlinked[0])[:40],
        )
    unk = [
        o
        for o in opts
        if _shown(d, o) and _rel(o) == REL_UNKNOWN and not (o.labelled_unchecked or o.learn_first)
    ]
    if unk:
        return _r(
            "SR-07",
            UNKNOWN,
            [f"{o.id}: relevance unknown and not labelled" for o in unk],
            "label_unknown",
            unk[0].id,
        )
    return _r("SR-07", PASS, [f"{len(opts)} option(s), none unlinked or generic"])


def sr08(d: DraftResult) -> CheckResult:
    opts = _all_options(d)
    if not opts:
        return _r("SR-08", NOT_APPLICABLE, ["no option listed"])
    tried = [t for t in _seq(d.tried_solutions) if isinstance(t, str)]
    tried_sets = [w for w in (T.content_words(t) for t in tried) if w]
    if d.tried_solutions is None and not any(_rel(o) == REPEATS_TRIED for o in opts):
        return _r("SR-08", UNKNOWN, ["tried solutions not supplied"], "ask_tried")
    bad: list[OptionIn] = []
    for o in opts:
        if not _shown(d, o) or o.improves_on_tried:
            continue
        ow = T.content_words(o.text)
        same = bool(ow) and any(
            len(ow & tw) >= max(2, int(0.7 * min(len(ow), len(tw)))) for tw in tried_sets
        )
        if _rel(o) == REPEATS_TRIED or same:
            bad.append(o)
    if bad:
        return _r(
            "SR-08",
            FAIL,
            [f"{o.id} repeats a failed attempt without a labelled improvement" for o in bad],
            "drop_option",
            bad[0].id,
        )
    return _r("SR-08", PASS, [f"{len(tried)} tried item(s) checked"])


def _unknown_present(d: DraftResult) -> bool:
    return any(getattr(c, "gate", "") == GATE_UNKNOWN for c in _seq(d.constraints)) or any(
        o.gate == GATE_UNKNOWN or _rel(o) == REL_UNKNOWN for o in _all_options(d)
    )


def sr09(d: DraftResult) -> CheckResult:
    opts = _all_options(d)
    if not (d.constraints or opts or d.blueprint):
        return _r("SR-09", NOT_APPLICABLE, ["nothing unknown can be shown"])
    bad: list[str] = []
    arg = ""
    for c in _seq(d.constraints):
        if getattr(c, "gate", "") == GATE_UNKNOWN and getattr(c, "shown", "") in (
            "satisfied",
            "clear",
            "approved",
            "ok",
        ):
            bad.append(f"constraint {c.id} is unknown but shown as {c.shown}")
            arg = c.id
    for o in opts:
        shown_unknown = o.gate == GATE_UNKNOWN or _rel(o) == REL_UNKNOWN
        if _shown(d, o) and shown_unknown and not (o.labelled_unchecked or o.learn_first):
            bad.append(f"option {o.id} is unknown but not labelled")
            arg = arg or o.id
    unknown = _unknown_present(d)
    if unknown and d.blueprint is not None and not d.blueprint.unknowns:
        bad.append("unknowns exist but the blueprint lists none")
    if unknown and d.reply_text and T.guarded_hits(T.APPROVAL, d.reply_text, (T.NEGATION,)):
        bad.append("the reply says approved or all clear while something is unknown")
    if bad:
        return _r("SR-09", FAIL, bad, "label_unknown", arg)
    return _r("SR-09", PASS, ["unknowns are labelled" if unknown else "nothing unknown"])


# ---------------------------------------------------------------- SR-10 .. SR-12


def sr10(d: DraftResult) -> CheckResult:
    rec = d.recommended
    if rec is None:
        return _r("SR-10", NOT_APPLICABLE, ["no recommended option"])
    cons = _seq(d.constraints)
    all_unknown = bool(cons) and all(getattr(c, "gate", "") == GATE_UNKNOWN for c in cons)
    if rec.gate == VIOLATED or any(getattr(c, "gate", "") == VIOLATED for c in cons):
        return _r(
            "SR-10", FAIL, ["the recommended option violates a constraint"], "drop_option", rec.id
        )
    if rec.gate not in (SATISFIED, GATE_UNKNOWN):
        return _r(
            "SR-10",
            UNKNOWN,
            ["no feasibility status for the recommended option"],
            "list_constraints",
        )
    if rec.gate == GATE_UNKNOWN and not (rec.labelled_unchecked or rec.learn_first):
        return _r(
            "SR-10",
            FAIL,
            ["feasibility unknown and not labelled 'not yet checked'"],
            "label_unknown",
            rec.id,
        )
    if all_unknown and not rec.learn_first:
        return _r(
            "SR-10",
            FAIL,
            ["every constraint is unknown: present it as learn-first"],
            "learn_first",
            rec.id,
        )
    return _r("SR-10", PASS, [f"gate {rec.gate}"])


def sr11(d: DraftResult) -> CheckResult:
    rec = d.recommended
    if rec is None:
        return _r("SR-11", NOT_APPLICABLE, ["no recommended option"])
    main = d.main_problem_id or (
        getattr(_seq(d.noted_problems)[0], "id", "") if _seq(d.noted_problems) else ""
    )
    if not main:
        return _r("SR-11", UNKNOWN, ["main problem not known"], "ask_detail")
    if main in _seq(rec.addresses):
        return _r("SR-11", PASS, [f"addresses {main}"])
    return _r(
        "SR-11", FAIL, [f"the recommended option does not address {main}"], "drop_option", rec.id
    )


def sr12(d: DraftResult) -> CheckResult:
    bp = d.blueprint
    if bp is None:
        if d.kind == "blueprint":
            return _r("SR-12", UNKNOWN, ["blueprint not supplied"], "add_deps_risks")
        return _r("SR-12", NOT_APPLICABLE, ["no blueprint"])
    secs = {T.fold(s).strip() for s in _seq(bp.sections)}
    dep_ok = bool(_seq(bp.dependencies)) or bp.none_known_dependencies
    risk_ok = bool(_seq(bp.risks)) or bp.none_known_risks
    miss: list[str] = []
    if not dep_ok or (secs and "dependencies" not in secs):
        miss.append("dependencies")
    if not risk_ok or (secs and "risks" not in secs):
        miss.append("risks")
    if miss:
        return _r(
            "SR-12", FAIL, [f"missing or empty: {', '.join(miss)}"], "add_deps_risks", miss[0]
        )
    return _r("SR-12", PASS, ["dependencies and risks present"])


# ---------------------------------------------------------------- SR-13 .. SR-16


def _expected_language(d: DraftResult) -> str | None:
    if d.owner_language in LANGS:
        return d.owner_language
    if d.owner_text:
        return T.detect_language(d.owner_text)
    return None


def sr13(d: DraftResult) -> CheckResult:
    if not d.reply_text.strip():
        return _r("SR-13", NOT_APPLICABLE, ["no reply text"])
    exp = _expected_language(d)
    if exp is None:
        if d.owner_script in ("latin", "arabic"):
            got = T.detect_language(d.reply_text)
            if got is not None and T.script_of_language(got) != d.owner_script:
                return _r(
                    "SR-13",
                    FAIL,
                    [f"reply is {got}, owner script is {d.owner_script}"],
                    "rewrite_reply",
                    d.owner_script,
                )
        return _r("SR-13", UNKNOWN, ["owner language not known"])
    got = T.detect_language(d.reply_text)
    if got is None:
        if d.reply_language in LANGS and d.reply_language != exp:
            return _r(
                "SR-13",
                FAIL,
                [f"caller says reply is {d.reply_language}, owner is {exp}"],
                "rewrite_reply",
                exp,
            )
        return _r("SR-13", UNKNOWN, ["reply language cannot be told"])
    if got == exp:
        return _r("SR-13", PASS, [f"reply is {got}"])
    return _r("SR-13", FAIL, [f"reply is {got}, owner is {exp}"], "rewrite_reply", exp)


def sr14(d: DraftResult) -> CheckResult:
    text = d.reply_text
    if not text.strip():
        return _r("SR-14", NOT_APPLICABLE, ["no reply text"])
    guards = (T.NEGATION,)
    known = _known_numbers(d)
    claims = T.guarded_hits(T.CLAIM_WORD, text, guards)
    t = T.fold(text)
    for m in T.PERCENT.finditer(t):
        if m.group(1) not in known:
            claims.append(m.group(0))
    for m in T.MONEY.finditer(t):
        num = (m.group(1) or m.group(2) or "").replace(",", "")
        if num and num not in known:
            claims.append(m.group(0))
    if claims:
        return _r(
            "SR-14",
            FAIL,
            [f"invented claim: {c}" for c in claims[:4]],
            "remove_claims",
            claims[0],
            tag="claim",
        )
    jarg = sorted(set(T.words(text)) & T.JARGON)
    if len(jarg) >= 2:
        return _r("SR-14", FAIL, [f"jargon: {', '.join(jarg)}"], "plain_words")
    if d.next_steps is not None and d.next_steps > 1:
        return _r("SR-14", FAIL, [f"{d.next_steps} next steps; give one"], "one_step")
    if _claims_solution(d) and d.next_steps in (None, 0) and T.question_count(text) == 0:
        return _r("SR-14", FAIL, ["no clear next step"], "one_step")
    return _r("SR-14", PASS, ["one clear step, plain words, no invented claim"])


def sr15(d: DraftResult) -> CheckResult:
    text = d.reply_text
    if not text.strip():
        return _r("SR-15", NOT_APPLICABLE, ["no reply text"])
    n = T.question_count(text)
    if d.questions and d.questions.count is not None:
        n = max(n, d.questions.count)
    if n > 1:
        return _r("SR-15", FAIL, [f"{n} questions in one message"], "ask_one_question")
    if n == 1 and not T.last_is_question(text):
        return _r("SR-15", FAIL, ["the question is not the last sentence"], "ask_one_question")
    return _r("SR-15", PASS, [f"{n} question(s)"])


def sr16(d: DraftResult) -> CheckResult:
    if not d.reply_text.strip():
        return _r("SR-16", NOT_APPLICABLE, ["no reply text"])
    if d.implementation_status in ("implemented", "delivered", "done"):
        return _r("SR-16", NOT_APPLICABLE, ["the solution is implemented"])
    hits = T.guarded_hits(T.IMPLEMENTED, d.reply_text, (T.NEGATION, T.CONDITIONAL))
    if hits:
        return _r(
            "SR-16",
            FAIL,
            [f"proposed solution worded as done: {h}" for h in hits[:3]],
            "reword_proposed",
        )
    return _r("SR-16", PASS, ["proposal worded as a proposal"])


CHECKS: tuple[tuple[str, Callable[[DraftResult], CheckResult]], ...] = (
    ("SR-01", sr01), ("SR-02", sr02), ("SR-03", sr03), ("SR-04", sr04), ("SR-05", sr05),
    ("SR-06", sr06), ("SR-07", sr07), ("SR-08", sr08), ("SR-09", sr09), ("SR-10", sr10),
    ("SR-11", sr11), ("SR-12", sr12), ("SR-13", sr13), ("SR-14", sr14), ("SR-15", sr15),
    ("SR-16", sr16),
)  # fmt: skip
