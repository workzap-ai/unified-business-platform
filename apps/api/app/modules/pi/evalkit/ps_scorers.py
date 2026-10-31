# ruff: noqa: E501
"""Code scorers for the problem-solving cases (PS-0). No model. Each metric is a (num, den) pair so a
report can show the real n; nothing here sets a pass level.

Reused: `scorers` (extraction recall and precision, figure fidelity, correction applied, unsupported
cause, constraint kept), `relevance` (idea verdicts), the live `idea_filter`, `problem_fields.merge_cause`,
`language.detect_language`, `expert_advisor.question_ok` and `same_question`.
New here: repeated-question scorer (slot cues), blueprint completeness, constraint rejection by the live
idea filter, fact preservation, language match of pi's reference replies.

Limits that matter when reading a number: pi's replies in these cases are hand-written reference replies,
so the question and language metrics check the scorers and the case design, not the model. The slot
cues are a small fixed list; a question with no recognised slot is counted as unclassified, never as
fine. Blueprint completeness of the reference blueprint is a scorer check; what the live path can hold
is `live_blueprint_support`, a read of the document schema.
"""

import re
from typing import Any

from app.modules.pi import expert_advisor, language, problem_fields
from app.modules.pi import idea_filter as live_filter
from app.modules.pi.evalkit import ps_replay, relevance, scorers

MIN_CASES = scorers.MIN_CASES  # fewer cases in a cell: not yet measured
MIN_ITEMS = 10  # fewer scored items (the metric's den) in a cell: not yet measured

# Slot cues, case-folded substrings. A pi question is classified by the first slot whose cue it holds.
SLOT_CUES: dict[str, tuple[str, ...]] = {
    "since": ("since when", "how long", "when did", "when was", "kab se", "kab shuru", "kitne arse",
              "منذ متى", "من متى", "کب سے", "کب شروع", "کتنے عرصے"),
    "how_often": ("how often", "how many times", "kitni baar", "kitni dafa", "كم مرة", "کتنی بار",
                  "کتنی دفعہ"),
    "tried": ("tried", "already did", "what have you done", "ab tak kya", "kya try", "جرب", "کیا آزما",
              "کیا کوشش", "ہو چکی"),
    "cause": ("why", "what do you think", "the reason", "the cause", "kyun", "kis wajah", "kya wajah",
              "لماذا", "ما السبب", "تعتقد", "کیوں", "کیا وجہ", "کس وجہ"),
    "outcome": ("what would", "good look like", "what result", "what outcome", "what change",
                "what do you want", "what first", "see first", "first thing", "kya chahte",
                "kya behtar", "kaisa nateeja", "kya nateeja", "kaisa hoga", "chahenge",
                "chahte hain", "ماذا تريد", "ما النتيجة", "كيف سيبدو", "كيف يبدو", "ما أول",
                "ما الذي تريد", "ماذا تتوقع", "کیا نتیجہ", "کیا چاہتے", "کیسا نتیجہ", "کیا بہتر",
                "کیسا ہو", "کیا جاننا", "کیا دیکھنا", "کیا تبدیل"),
    "money": ("how much", "kitna nuqsan", "kitne paise", "kitni raqam", "kitni aamdani",
              "kitna kharch", "kitne mein", "kitna kiraya", "كم تخسر", "كم يكلف", "كم الخسارة",
              "كم يبلغ", "كم يدر", "كم تكلف", "کتنا نقصان", "کتنے پیسے", "کتنی رقم", "کتنی آمدنی",
              "کتنا خرچ", "کتنے میں"),
    "count": ("how many", "kitne", "كم عدد", "كم ", "کتنے", "کتنی"),
    "who": ("who ", "which staff", "which person", "kaun", "kis ", "من يتولى", "من ", "کون", "کس "),
    "when": ("which day", "what time", "weekday", "weekend", "aam dinon", "kis din", "kab ",
             "أي يوم", "متى", "کس دن", "ویک اینڈ", "عام دنوں", "کب "),
    "where": ("where", "which branch", "which step", "which part", "one part", "by phone",
              "kahan", "kis hissay", "ek hissay", "kaise book", "أين", "في أي", "كيف يحجز",
              "كيف يدفع", "کہاں", "کس حصے", "کس مرحلے", "ایک حصے", "کیسے"),
    "constraint": ("budget", "deadline", "can you hire", "limit", "mushkil", "ميزانية", "قيود",
                   "بجٹ", "حد"),
}  # fmt: skip
SLOT_ORDER = ("since", "how_often", "tried", "cause", "outcome", "money", "count", "where",
              "when", "who", "constraint")  # fmt: skip
LANG_OF = {"en": "en", "roman_ur": "roman_ur", "ur": "ur", "ar": "ar"}


def classify_slot(question: str) -> str | None:
    """The slot a question asks about by cue, or None (unclassified)."""
    low = " ".join(question.casefold().split()) + " "
    return next((s for s in SLOT_ORDER if any(c in low for c in SLOT_CUES[s])), None)


def last_question(text: str) -> str:
    parts = [p.strip() for p in re.split(r"(?<=[.!?؟۔])\s+", text or "") if p.strip()]
    return next((p for p in reversed(parts) if p.endswith(("?", "؟"))), "")


def rate(num: int, den: int) -> dict[str, int]:
    return {"num": num, "den": den}


def known_slots(case: dict[str, Any], before_turn: int) -> set[str]:
    """Slots the owner had stated by the end of owner turn `before_turn` (0-based, inclusive)."""
    facts = case["expected"].get("answered_facts") or []
    return {f["slot"] for f in facts if int(f.get("said_in_turn", 99)) <= before_turn}


def question_scores(case: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Repeated, unclassified and badly formed questions among pi's (reference) replies."""
    replies = [t["text"] for t in case["turns"] if t["role"] == "pi"]
    earlier: list[str] = []
    repeats = unclassified = form_ok = label_known = 0
    for index, reply in enumerate(replies):
        question = last_question(reply)
        slot = classify_slot(question)
        known = known_slots(case, index)
        legit = {
            r["slot"] for r in case["expected"].get("legit_reasks") or [] if r["turn"] == index
        }
        if slot is None:
            unclassified += 1
        elif slot in known and slot not in legit:
            repeats += 1
        elif expert_advisor.same_as_any(question, earlier):
            repeats += 1
        labelled = next(
            (
                q["slot"]
                for q in case["expected"].get("questions") or []
                if q["after_turn"] == index
            ),
            None,
        )
        if labelled in known:
            label_known += 1
        form_ok += 1 if expert_advisor.question_ok(question) else 0
        earlier.append(question)
    n = len(replies)
    return {
        "repeated_question": rate(repeats, n),
        "unclassified_question": rate(unclassified, n),
        "question_form_ok": rate(form_ok, n),
        "labelled_slot_already_known": rate(label_known, n),
    }


def language_scores(case: dict[str, Any]) -> dict[str, dict[str, int]]:
    expected = LANG_OF.get(case.get("language", ""), "")
    replies = [t["text"] for t in case["turns"] if t["role"] == "pi"]
    detected = [language.detect_language(r) for r in replies]
    return {
        "language_match": rate(sum(1 for d in detected if d == expected), len(replies)),
        "language_undetected": rate(sum(1 for d in detected if d is None), len(replies)),
    }


def _flat(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in _flat(v)]
    if isinstance(value, list | tuple):
        return [t for v in value for t in _flat(v)]
    return []


def _pool(records: list[dict[str, Any]]) -> str:
    """Everything the saved records hold as text (every text field, including limits, things tried,
    the cause and the places), so a fact counts as kept wherever the record keeps it."""
    return " ".join(t for r in records for k, v in r.items() if k != "turn" for t in _flat(v))


def _record_dicts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Records as scorers.constraint_text reads them: constraints is a list of strings."""
    return [
        {
            **r,
            "constraints": [
                c if isinstance(c, str) else str(c) for c in r.get("constraints") or []
            ],
        }
        for r in records
    ]


def extraction_scores(
    case: dict[str, Any], records: list[dict[str, Any]], suffix: str
) -> dict[str, dict[str, int]]:
    """Recall, precision, figures, corrections, stated facts, constraints, tried, cause for one set of
    records (`live` or `reference`)."""
    expected = case["expected"]
    view = {
        "id": case["id"],
        "messages": [t["text"] for t in ps_replay.owner_turns(case)],
        "expected": {
            "problems": expected["problems"],
            "corrections": [
                {"wrong": c["wrong"], "right": c["right"], "problem": c["problem"]}
                for c in expected.get("corrections") or []
            ],
            "hypothesis_only": expected.get("hypothesis_only") or [],
        },
    }
    base = scorers.score_case(view, records)
    recs = _record_dicts(records)
    pool = _pool(recs)
    stated = expected.get("stated") or []
    constraints = [c["text"] for c in expected.get("constraints") or []]
    tried = [t["what"] for t in expected.get("tried") or []]
    cause = expected.get("cause") or {}
    cause_words = cause.get("evidence_words") or []
    cause_text = " ".join(str(r.get("cause", "")) for r in recs)
    cause_ok = bool(cause_words) and all(
        scorers.constraint_kept(w, cause_text) for w in cause_words
    )
    out = {
        "recall": rate(base["found"], base["expected"]),
        "precision": rate(base["found"], base["found"] + base["extra"]),
        "figure_fidelity": rate(base["figures_kept"], base["figures"]),
        "correction_applied": rate(base["corrections_applied"], base["corrections"]),
        "unsupported_cause": rate(len(base["unsupported_causes"]), len(recs)),
        "stated_facts_kept": rate(
            sum(1 for s in stated if scorers.constraint_kept(s, pool)), len(stated)
        ),
        "constraints_kept": rate(
            sum(1 for c in constraints if scorers.constraint_kept(c, pool)), len(constraints)
        ),
        "tried_kept": rate(sum(1 for t in tried if scorers.constraint_kept(t, pool)), len(tried)),
        "owner_cause_captured": rate(1 if cause_ok else 0, 1 if cause else 0),
    }
    return {f"{k}{suffix}" if suffix else k: v for k, v in out.items()}


def hypothesis_scores(case: dict[str, Any]) -> dict[str, dict[str, int]]:
    """A cause pi only guessed must stay a hypothesis in `problem_fields.merge_cause`, also when the
    caller wrongly says the owner said it but the owner never wrote those words."""
    corpus = " ".join(t["text"] for t in ps_replay.owner_turns(case))
    tests = 0
    safe = 0
    for hypothesis in case["expected"].get("hypothesis_only") or []:
        for owner_said in (False, True):
            tests += 1
            stored, _ = problem_fields.merge_cause(
                None, hypothesis, owner_said, hypothesis.split()[:4], "m1", corpus
            )
            if stored is None or stored.get("status") == problem_fields.PI_INFERRED:
                safe += 1
    return {"hypothesis_stays_hypothesis": rate(safe, tests)}


def brief_of(case: dict[str, Any]) -> dict[str, Any]:
    """The relevance brief from the case: problems with the owner's words, figures, stated facts and
    the confirmed limits."""
    expected = case["expected"]
    notes = (case.get("recorded") or {}).get("notes_by_turn") or {}
    first = {p["id"]: p for p in expected["problems"]}
    titles: dict[str, dict[str, Any]] = {}
    for index, spec in enumerate(expected["problems"]):
        note = (notes.get(str(index)) or [{}])[0]
        titles[spec["id"]] = note
    facts = [w for f in expected.get("answered_facts") or [] for w in f.get("value_words") or []]
    problems = []
    for pid, spec in first.items():
        note = titles.get(pid) or {}
        limits = [
            {
                "kind": c.get("kind", ""),
                "text": c["text"],
                "blocks": c.get("blocks") or [],
                "status": c.get("status", "confirmed"),
            }
            for c in expected.get("constraints") or []
            if (c.get("problem") or "p1") == pid
        ]
        problems.append(
            {
                "id": pid,
                "title": note.get("title_local") or note.get("title") or "",
                "user_words": note.get("user_words") or [],
                "figures": spec.get("figures") or [],
                "facts": facts,
                "constraints": limits,
            }
        )
    return {"problems": problems, "roles": [], "systems": []}


def idea_scores(case: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Candidate ideas: the relevance scorer's agreement with the labels, and what the LIVE idea filter
    does with them. The live filter gets the same noted problems the live path would hold; it has no
    field for a stated limit, so a limit-breaking idea is rejected only by chance."""
    expected = case["expected"]
    brief = brief_of(case)
    owner_text = " ".join(t["text"] for t in ps_replay.owner_turns(case))
    lang = case.get("language")
    candidates = expected["candidates"]
    agree = false_rel = hard = 0
    violating = [c for c in candidates if c["verdict"] == "violates_constraint"]
    relevant = [c for c in candidates if c["verdict"] == "relevant"]
    noted = [
        {"ref": p["id"], "title": p["title"], "user_words": p["user_words"]}
        for p in brief["problems"]
    ]
    ctx = live_filter.context_from(noted, owner_text)
    rejected = sum(1 for c in violating if live_filter.failures(c["text"], owner_text, ctx))
    kept = sum(1 for c in relevant if not live_filter.failures(c["text"], owner_text, ctx))
    only_g8 = sum(
        1
        for c in violating
        if live_filter.failures(c["text"], owner_text, ctx)
        and set(live_filter.failures(c["text"], owner_text, ctx)) == {"G8"}
    )
    for cand in candidates:
        got = relevance.score_candidate(brief, cand["text"], cand.get("problem"), owner_text, lang)[
            "verdict"
        ]
        agree += got == cand["verdict"]
        false_rel += got == "relevant" and cand["verdict"] != "relevant"
        hard += cand["verdict"] == "violates_constraint" and got != "violates_constraint"
    return {
        "relevance_agreement": rate(agree, len(candidates)),
        "false_relevant": rate(false_rel, len(candidates)),
        "violations_missed_by_scorer": rate(hard, len(violating)),
        "violations_rejected_by_live_filter": rate(rejected, len(violating)),
        "violations_rejected_by_other_than_g8": rate(rejected - only_g8, len(violating)),
        "relevant_kept_by_live_filter": rate(kept, len(relevant)),
    }


def filter_rules(case: dict[str, Any]) -> list[tuple[str, str]]:
    """(label verdict, live filter rule id or "pass") for every candidate idea of a case."""
    brief = brief_of(case)
    owner_text = " ".join(t["text"] for t in ps_replay.owner_turns(case))
    noted = [
        {"ref": p["id"], "title": p["title"], "user_words": p["user_words"]}
        for p in brief["problems"]
    ]
    ctx = live_filter.context_from(noted, owner_text)
    out: list[tuple[str, str]] = []
    for cand in case["expected"]["candidates"]:
        found = live_filter.failures(cand["text"], owner_text, ctx)
        out += [(cand["verdict"], rule) for rule in found] or [(cand["verdict"], "pass")]
    return out


# --- blueprint ---------------------------------------------------------------------------------

BLUEPRINT_KINDS = ("steps", "dependencies", "resources", "success_criteria")
MIN_ELEMENTS = {"steps": 3, "dependencies": 2, "resources": 1, "success_criteria": 1}


def _has(any_words: list[str], text: str, lang: str | None) -> bool:
    need = [relevance.stems(w, lang) for w in any_words]
    have = relevance.stems(text, lang)
    return bool(any_words) and all(n <= have for n in need if n)


def blueprint_scores(
    case: dict[str, Any], plan: dict[str, Any] | None = None
) -> dict[str, dict[str, int]]:
    """Blueprint actionability of `plan` (default: the case's reference blueprint): each element kind
    present in the minimum count, steps and criteria tied to owner words, dependencies resolving to
    real steps in order, no step that breaks a stated limit, no price or promise."""
    from app.modules.pi import constitution
    from app.modules.pi.brain_docs import MONEY_IN_TEXT

    plan = plan if plan is not None else case["expected"]["blueprint"]
    lang = case.get("language")
    steps = plan.get("steps") or []
    ids = [s.get("id") for s in steps]
    deps = plan.get("dependencies") or []
    present = {k: len(plan.get(k) or []) >= MIN_ELEMENTS[k] for k in BLUEPRINT_KINDS}
    ordered = sum(
        1
        for d in deps
        if d.get("from") in ids and d.get("to") in ids and ids.index(d["from"]) < ids.index(d["to"])
    )
    tied = sum(1 for s in steps if _has(s.get("any") or [], str(s.get("text", "")), lang))
    tied += sum(
        1
        for s in plan.get("success_criteria") or []
        if _has(s.get("any") or [], str(s.get("text", "")), lang)
    )
    total_tied = len(steps) + len(plan.get("success_criteria") or [])
    brief = brief_of(case)
    texts = [
        str(s.get("text", ""))
        for k in ("steps", "resources", "success_criteria")
        for s in plan.get(k) or []
    ]
    broken = sum(
        1
        for t in texts
        if relevance.score_candidate(brief, t, None, "", lang)["verdict"] == "violates_constraint"
    )
    promised = sum(1 for t in texts if MONEY_IN_TEXT.search(t) or constitution.PROMISE.search(t))
    return {
        "blueprint_elements_present": rate(sum(present.values()), len(BLUEPRINT_KINDS)),
        "blueprint_dependencies_valid": rate(ordered, len(deps)),
        "blueprint_tied_to_owner_words": rate(tied, total_tied),
        "blueprint_steps_breaking_a_limit": rate(broken, len(texts)),
        "blueprint_price_or_promise": rate(promised, len(texts)),
    }


LIVE_FIELD_FOR = {  # blueprint element -> the live document field that could hold it (None: none)
    "steps": "phases",  # names of phases only
    "dependencies": None,
    "resources": "needs",  # a short list of what the owner must provide
    "success_criteria": None,
}


def live_blueprint_support() -> dict[str, str | None]:
    """Which blueprint elements the CURRENT Solution Box draft schema has a field for (schema read)."""
    from app.modules.pi.brain_docs import BoxDraft

    return {k: (v if v in BoxDraft.model_fields else None) for k, v in LIVE_FIELD_FOR.items()}


# --- one case --------------------------------------------------------------------------------


def score_case(case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    """Every metric for one case as {name: {num, den}} plus the correction the live finder made."""
    metrics: dict[str, dict[str, int]] = {}
    metrics |= extraction_scores(case, run["live"], "")
    metrics |= extraction_scores(case, run["reference"], "_reference")
    metrics |= hypothesis_scores(case)
    metrics |= idea_scores(case)
    metrics |= question_scores(case)
    metrics |= language_scores(case)
    metrics |= blueprint_scores(case)
    expected = case["expected"].get("corrections") or []
    found = {(c["wrong"], c["right"]) for c in run["corrections"]}
    metrics["correction_detected"] = rate(
        sum(1 for c in expected if (c["wrong"], c["right"]) in found), len(expected)
    )
    return {"id": case["id"], "metrics": metrics}


def aggregate(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Sum num and den per metric over case rows; `measured` needs MIN_CASES cases and MIN_ITEMS items."""
    names = sorted({m for r in rows for m in r["metrics"]})
    out: dict[str, dict[str, Any]] = {}
    for name in names:
        num = sum(r["metrics"][name]["num"] for r in rows if name in r["metrics"])
        den = sum(r["metrics"][name]["den"] for r in rows if name in r["metrics"])
        cases = sum(1 for r in rows if name in r["metrics"] and r["metrics"][name]["den"])
        out[name] = {
            "num": num,
            "den": den,
            "cases": cases,
            "measured": cases >= MIN_CASES and den >= MIN_ITEMS,
        }
    return out
