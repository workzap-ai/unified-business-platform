"""Code scorers for understanding (no model). A `record` is what pi saved for one problem:
{"title", "user_words": [..], "summary", "money_text", "cause", "cause_status"}.
`cause_status` is "owner_said", "hypothesis" or "confirmed"; a confirmed cause that the owner never
said is the unsupported-cause failure.
"""

import re
from typing import Any

STEM = 5
_WORD = re.compile(r"\w+", re.UNICODE)
_NUM = re.compile(r"\d+(?:[.,]\d+)?")
MIN_CASES = 3  # fewer labelled cases than this in a group: "not yet measured", never "passing"


def _stems(text: str) -> set[str]:
    return {w.casefold()[:STEM] for w in _WORD.findall(text or "") if len(w) >= 3}


def record_text(record: dict[str, Any]) -> str:
    parts = [record.get("title", ""), record.get("summary", ""), record.get("money_text", "")]
    parts += [str(w) for w in record.get("user_words") or []]
    return " ".join(str(p) for p in parts if p)


def matches(spec: dict[str, Any], record: dict[str, Any]) -> bool:
    """The expected problem is this record when it shares at least `need` keywords (default 1)."""
    have = _stems(record_text(record))
    hit = sum(1 for k in spec.get("any") or [] if _stems(k) and _stems(k) <= have)
    return hit >= int(spec.get("need", 1))


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUM.findall(text or "")}


def figure_kept(figure: str, text: str) -> bool:
    """A figure like "10 crore" is kept when its number and its unit word both survive."""
    nums, words = _numbers(figure), _stems(_NUM.sub("", figure))
    return nums <= _numbers(text) and words <= _stems(text)


def constraint_kept(constraint: str, text: str) -> bool:
    """A stated limit ("only 2 supervisors", "cannot stop production") is kept when its content
    words and numbers all survive. A limit with no content word the word pattern can see (Devanagari
    is split at its vowel signs) must appear as written, so it is never kept vacuously."""
    if _stems(constraint):
        return figure_kept(constraint, text)
    return " ".join(constraint.casefold().split()) in " ".join(text.casefold().split())


def constraint_text(records: list[dict[str, Any]]) -> str:
    """Everything the saved records say about limits: their constraints and their own words."""
    parts = [" ".join(str(c) for c in r.get("constraints") or []) for r in records]
    return " ".join([*parts, *(record_text(r) for r in records)])


def score_case(case: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    expected = case["expected"]
    specs = expected.get("problems") or []
    taken: set[int] = set()
    pairs: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for spec in specs:
        found = next(
            (i for i, r in enumerate(records) if i not in taken and matches(spec, r)), None
        )
        if found is not None:
            taken.add(found)
        pairs.append((spec, records[found] if found is not None else None))
    got = sum(1 for _, r in pairs if r is not None)
    figures = [(f, r) for s, r in pairs if r is not None for f in s.get("figures") or []]
    kept = sum(1 for f, r in figures if figure_kept(f, record_text(r)))
    corrections = expected.get("corrections") or []
    applied = 0
    for fix in corrections:
        record = next((r for s, r in pairs if s.get("id") == fix.get("problem") and r), None)
        text = record_text(record) if record else ""
        if record and fix["right"] in _numbers(text) and fix["wrong"] not in _numbers(text):
            applied += 1
    owner_words = " ".join(case["messages"]).casefold()
    bad_cause = [
        r.get("title", "")
        for r in records
        if r.get("cause_status") == "confirmed"
        and not _stems(r.get("cause", "")) <= _stems(owner_words)
    ]
    hypotheses = [
        r.get("title", "")
        for r in records
        if r.get("cause_status") == "confirmed"
        and any(
            h.casefold() in str(r.get("cause", "")).casefold()
            for h in expected.get("hypothesis_only") or []
        )
    ]
    labelled = expected.get("constraints") or []
    pool = constraint_text(records)
    return {
        "id": case["id"],
        "expected": len(specs),
        "found": got,
        "extra": len(records) - got,
        "recall": got / len(specs) if specs else 1.0,
        "precision": got / len(records) if records else (1.0 if not specs else 0.0),
        "figures": len(figures),
        "figures_kept": kept,
        "corrections": len(corrections),
        "corrections_applied": applied,
        "unsupported_causes": sorted(set(bad_cause) | set(hypotheses)),
        "constraints": len(labelled),
        "constraints_kept": sum(1 for c in labelled if constraint_kept(str(c), pool)),
    }


def aggregate(scores: list[dict[str, Any]]) -> dict[str, Any]:
    """Totals for a group of case scores; `measured` is False below MIN_CASES."""
    n = len(scores)
    exp = sum(s["expected"] for s in scores)
    got = sum(s["found"] for s in scores)
    recs = got + sum(s["extra"] for s in scores)
    fig = sum(s["figures"] for s in scores)
    cor = sum(s["corrections"] for s in scores)
    con = sum(s["constraints"] for s in scores)
    return {
        "cases": n,
        "measured": n >= MIN_CASES,
        "recall": got / exp if exp else None,
        "precision": got / recs if recs else None,
        "figure_fidelity": sum(s["figures_kept"] for s in scores) / fig if fig else None,
        "correction_fidelity": sum(s["corrections_applied"] for s in scores) / cor if cor else None,
        "unsupported_cause_cases": sum(1 for s in scores if s["unsupported_causes"]),
        "constraint_fidelity": sum(s["constraints_kept"] for s in scores) / con if con else None,
    }
