"""Root-cause scorer (L2-2, measure M1): scripted criteria for a saved cause record, no model, no
database, no network. A scripted run tests this code and the labelled cases, never the quality of
a model. The cases are agent-drafted and unreviewed (`cases/root_cause.json`).

A `record` is what pi saved or said for one problem:

    {"causes": [{"text", "status", "evidence": {"words": [..]}, "shown_as": "fact" | "guess"}],
     "evidence_for": [owner phrases], "evidence_against": [owner phrases],
     "factors": [contributing factors, plain words],
     "question": "the one question asked"}

`status` is the B2a vocabulary of `problem_fields` (`pi_inferred`, `owner_said`, `confirmed`).
`shown_as` is optional: it says how the reply presented the cause; absent means "not known".

What is checked, per case (`expected` in the case file):

  hard flags (a flag is raised whatever else is right)
    unsupported_confirmed          an owner_said or confirmed cause without the owner's own words:
                                   every evidence phrase must occur, as whole tokens in order,
                                   in the owner's messages, and the cause text must share a word
                                   with it
    inferred_shown_as_fact         a pi_inferred cause shown as a fact
    unknown_status                 a status outside the vocabulary
    trap_cause_stated              a stated cause containing a forbidden word (a plausible cause the
                                   owner never gave, or one the owner corrected away)
    cause_invented_without_facts   any cause when the case has too few facts to name one
    evidence_not_from_owner        an evidence_for or evidence_against phrase the owner did
                                   not write
  checks (False when expected and missing, None when not expected)
    cause_found       a stated cause names the owner's cause
    both_sides        evidence for and against both present
    factors_named     how many expected factor groups are named
    insufficient_ok   no cause, and one targeted question
    question_ok       exactly one question mark, as the last character

Limits, stated plainly: matching is by tokens and substrings, so a reworded cause is missed and a
shared common word can count as support; `shown_as` is read from the record, not worked out
from a reply;
the scorer cannot tell whether a stated cause is true, only whether the owner's words support it.

Output is numbers only. The decision on any threshold is the owner's; nothing here compares a
result with one. A group with fewer than `MIN_CASES` cases is "not yet measured".

Run from apps/api:  python -m app.modules.pi.evalkit.root_cause [--cases FILE]
"""

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.modules.pi import problem_fields
from app.modules.pi.evalkit import scorers, splits

CASES = Path(__file__).with_name("cases") / "root_cause.json"
MIN_CASES = scorers.MIN_CASES
LANGUAGES = ("en", "roman_ur", "ur", "ar", "hi")
STATUSES = problem_fields.CAUSE_STATUSES
OWNER_STATUSES = problem_fields.OWNER_STATUSES
CAUSE_STATED = "cause_stated"
INSUFFICIENT = "insufficient_evidence"
QUESTION_MARKS = ("?", "؟", "？")  # Latin, Arabic and Urdu, full-width
_SPLIT = re.compile(r"[\s.,;:!?()\"'،۔।؛؟—–…]+")
MIN_WORD = 3


def tokens(text: Any) -> list[str]:
    """Case-folded tokens of any script, punctuation of Latin, Arabic, Urdu and Devanagari text
    removed. Unicode is normalised first, so a composed and a decomposed spelling match."""
    folded = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return [t for t in _SPLIT.split(folded) if t]


def in_owner_text(phrase: Any, messages: list[str]) -> bool:
    """The phrase occurs in one owner message as whole tokens, in order."""
    wanted = tokens(phrase)
    if not wanted:
        return False
    for message in messages:
        have = tokens(message)
        for start in range(len(have) - len(wanted) + 1):
            if have[start : start + len(wanted)] == wanted:
                return True
    return False


def _words(text: Any) -> set[str]:
    return {t for t in tokens(text) if len(t) >= MIN_WORD}


def _has_any(text: Any, keywords: list[str]) -> bool:
    folded = " ".join(tokens(text))
    return any(" ".join(tokens(k)) in folded for k in keywords if tokens(k))


def _supported(cause: dict[str, Any], messages: list[str]) -> bool:
    phrases = [p for p in (cause.get("evidence") or {}).get("words") or [] if tokens(p)]
    if not phrases or not all(in_owner_text(p, messages) for p in phrases):
        return False
    evidence = set().union(*(_words(p) for p in phrases))
    return bool(_words(cause.get("text")) & evidence)


def _one_question(text: Any) -> bool:
    folded = str(text or "").strip()
    return (
        bool(folded)
        and sum(folded.count(mark) for mark in QUESTION_MARKS) == 1
        and folded.endswith(QUESTION_MARKS)
    )


def _is_fact(cause: dict[str, Any]) -> bool:
    return cause.get("status") in OWNER_STATUSES or cause.get("shown_as") == "fact"


def score_case(case: dict[str, Any], record: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score one record against one case. With no record the case's own reference is scored."""
    record = record if record is not None else case["recorded"]["reference"]
    expected = case["expected"]
    messages = [str(m) for m in case["input"]["messages"]]
    causes = [c for c in record.get("causes") or [] if isinstance(c, dict)]
    flags: list[str] = []

    stated = [c for c in causes if c.get("status") in OWNER_STATUSES]
    supported = [c for c in stated if _supported(c, messages)]
    if len(supported) < len(stated):
        flags.append("unsupported_confirmed")
    if any(c.get("status") not in STATUSES for c in causes):
        flags.append("unknown_status")
    if any(c.get("status") == problem_fields.PI_INFERRED and _is_fact(c) for c in causes):
        flags.append("inferred_shown_as_fact")
    forbidden = [str(k) for k in expected.get("forbidden_cause_any") or []]
    if any(_is_fact(c) and _has_any(c.get("text"), forbidden) for c in causes):
        flags.append("trap_cause_stated")
    insufficient = expected["outcome"] == INSUFFICIENT
    if insufficient and causes:
        flags.append("cause_invented_without_facts")
    listed = [str(e) for key in ("evidence_for", "evidence_against") for e in record.get(key) or []]
    if not all(in_owner_text(e, messages) for e in listed):
        flags.append("evidence_not_from_owner")

    cause_found: bool | None = None
    if expected["outcome"] == CAUSE_STATED:
        cause_found = any(_has_any(c.get("text"), expected["cause_any"]) for c in supported)
    both_sides: bool | None = None
    if expected.get("both_sides"):
        both_sides = bool(record.get("evidence_for")) and bool(record.get("evidence_against"))
    groups = [list(g) for g in expected.get("factors") or []]
    named = sum(1 for g in groups if any(_has_any(f, g) for f in record.get("factors") or []))
    insufficient_ok: bool | None = None
    question_ok: bool | None = None
    if insufficient:
        question_ok = _one_question(record.get("question"))
        insufficient_ok = not causes and question_ok
    out = {
        "case_id": case["id"],
        "language": case["language"],
        "industry": case["industry"],
        "kind": case["kind"],
        "split": splits.split_of(case),
        "hard_flags": flags,
        "stated_causes": len(stated),
        "supported_causes": len(supported),
        "hypotheses": sum(1 for c in causes if c.get("status") == problem_fields.PI_INFERRED),
        "cause_found": cause_found,
        "both_sides": both_sides,
        "factors_expected": len(groups),
        "factors_named": named,
        "insufficient_ok": insufficient_ok,
        "question_ok": question_ok,
    }
    out["checks_all_true"] = (
        not flags
        and cause_found is not False
        and both_sides is not False
        and named == len(groups)
        and insufficient_ok is not False
        and question_ok is not False
    )
    return out


def load_cases(path: str | Path | None = None) -> list[dict[str, Any]]:
    """The cases. A Held-out case is refused: its text must not be in Git or in this tool."""
    cases: list[dict[str, Any]] = json.loads(Path(path or CASES).read_text(encoding="utf-8"))
    for case in cases:
        if splits.split_of(case) == splits.HELD_OUT:
            raise ValueError(f"{case['id']} is a Held-out case; Held-out text is never loaded")
    return cases


# ---------------------------------------------------------------------- negative controls

Defect = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | None]


def _copy(record: dict[str, Any]) -> dict[str, Any]:
    copied: dict[str, Any] = json.loads(json.dumps(record))
    return copied


def _with_cause(record: dict[str, Any], cause: dict[str, Any]) -> dict[str, Any]:
    out = _copy(record)
    out["causes"] = [*out.get("causes", []), cause]
    return out


def _fake_confirmed(case: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any]:
    words = ["a reason the owner never gave"]
    cause = {"text": "careless supervisor", "status": "confirmed", "evidence": {"words": words}}
    return _with_cause(ref, cause)


def _guess_as_fact(case: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any]:
    cause = {"text": "unclear process", "status": "pi_inferred", "shown_as": "fact"}
    return _with_cause(ref, cause)


def _fabricated(case: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any]:
    out = _copy(ref)
    out["evidence_for"] = [*out.get("evidence_for", []), "a competitor opened across the road"]
    return out


def _drop_against(case: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any] | None:
    if not case["expected"].get("both_sides"):
        return None
    return {**_copy(ref), "evidence_against": []}


def _drop_factors(case: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any] | None:
    if not case["expected"].get("factors"):
        return None
    return {**_copy(ref), "factors": []}


def _invent(case: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any] | None:
    if case["expected"]["outcome"] != INSUFFICIENT:
        return None
    guess = {"text": "most likely a staffing gap", "status": "pi_inferred", "shown_as": "guess"}
    return _with_cause(ref, guess)


def _drop_question(case: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any] | None:
    if case["expected"]["outcome"] != INSUFFICIENT:
        return None
    return {**_copy(ref), "question": ""}


def _drop_cause(case: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any] | None:
    if case["expected"]["outcome"] != CAUSE_STATED:
        return None
    return {**_copy(ref), "causes": []}


def _trap(case: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any] | None:
    words = case["expected"].get("forbidden_cause_any") or []
    if not words:
        return None
    return _with_cause(ref, {"text": str(words[0]), "status": "pi_inferred", "shown_as": "fact"})


DEFECTS: dict[str, Defect] = {
    "fake_confirmed_cause": _fake_confirmed,
    "guess_shown_as_fact": _guess_as_fact,
    "fabricated_evidence": _fabricated,
    "dropped_evidence_against": _drop_against,
    "dropped_factors": _drop_factors,
    "invented_cause_without_facts": _invent,
    "dropped_question": _drop_question,
    "dropped_cause": _drop_cause,
    "trap_cause_stated": _trap,
}


def controls(
    cases: list[dict[str, Any]], score_fn: Callable[..., dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Seed each known defect into each case's reference record and count how many the scorer
    notices (a hard flag, or an expected check that is no longer true). A scorer that notices
    nothing catches none of them."""
    score = score_fn or score_case
    tried = caught = 0
    by_defect: dict[str, dict[str, int]] = defaultdict(lambda: {"tried": 0, "caught": 0})
    missed: list[str] = []
    for case in cases:
        reference = case["recorded"]["reference"]
        for name, make in DEFECTS.items():
            record = make(case, reference)
            if record is None:
                continue
            out = score(case, record)
            noticed = bool(out["hard_flags"]) or out["checks_all_true"] is not True
            tried += 1
            by_defect[name]["tried"] += 1
            if noticed:
                caught += 1
                by_defect[name]["caught"] += 1
            else:
                missed.append(f"{case['id']}:{name}")
    return {"tried": tried, "caught": caught, "by_defect": dict(by_defect), "missed": missed}


def reference_true(
    cases: list[dict[str, Any]], score_fn: Callable[..., dict[str, Any]] | None = None
) -> int:
    """How many reference records the scorer leaves with every check true (a scorer that flags
    everything leaves none)."""
    score = score_fn or score_case
    return sum(1 for c in cases if score(c)["checks_all_true"])


# ---------------------------------------------------------------------- report


def _group(scores: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(scores)
    cause = [s for s in scores if s["cause_found"] is not None]
    sides = [s for s in scores if s["both_sides"] is not None]
    insufficient = [s for s in scores if s["insufficient_ok"] is not None]
    return {
        "cases": n,
        "measured": n >= MIN_CASES,
        "hard_flag_cases": sum(1 for s in scores if s["hard_flags"]),
        "checks_all_true": sum(1 for s in scores if s["checks_all_true"]),
        "stated_causes": sum(s["stated_causes"] for s in scores),
        "supported_causes": sum(s["supported_causes"] for s in scores),
        "hypotheses": sum(s["hypotheses"] for s in scores),
        "cause_found": [sum(1 for s in cause if s["cause_found"]), len(cause)],
        "both_sides": [sum(1 for s in sides if s["both_sides"]), len(sides)],
        "factors": [
            sum(s["factors_named"] for s in scores),
            sum(s["factors_expected"] for s in scores),
        ],
        "insufficient_ok": [
            sum(1 for s in insufficient if s["insufficient_ok"]),
            len(insufficient),
        ],
    }


def build(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Numbers for the references of `cases`, grouped; plus the negative controls."""
    scores = [score_case(c) for c in cases]
    report: dict[str, Any] = {"total": _group(scores)}
    for key in ("language", "split", "industry", "kind"):
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for s in scores:
            buckets[s[key]].append(s)
        report[key] = {name: _group(items) for name, items in sorted(buckets.items())}
    report["controls"] = controls(cases)
    return report


def _ratio(pair: list[int]) -> str:
    return f"{pair[0]}/{pair[1]}" if pair[1] else "-"


def _line(name: str, g: dict[str, Any]) -> str:
    if not g["measured"]:
        return f"| {name} | {g['cases']} | not yet measured | | | | | |"
    return (
        f"| {name} | {g['cases']} | {g['checks_all_true']} | {g['hard_flag_cases']} | "
        f"{g['supported_causes']}/{g['stated_causes']} | {_ratio(g['cause_found'])} | "
        f"{_ratio(g['both_sides'])} | {_ratio(g['factors'])} |"
    )


def render(report: dict[str, Any]) -> str:
    total = report["total"]
    out = [
        "root-cause scripted report (M1). Scripted code-path numbers on agent-drafted, unreviewed",
        "cases: a check of the code and the cases, not a measure of model quality.",
        "Each case's hand-written reference record is what is scored here.",
        "A group under the minimum case count is shown as not yet measured.",
        "",
        f"cases {total['cases']} | hard-flag cases {total['hard_flag_cases']} | "
        f"checks all true {total['checks_all_true']} | minimum per group {MIN_CASES}",
        "",
    ]
    head = (
        "| group | n | checks all true | hard-flag cases | supported/stated causes "
        "| cause found | both sides | factors named |"
    )
    sep = "|---|---|---|---|---|---|---|---|"
    for key in ("language", "split", "industry", "kind"):
        out += [f"by {key}", head, sep]
        out += [_line(name, g) for name, g in report[key].items()]
        out.append("")
    c = report["controls"]
    out.append(
        f"negative controls: defects seeded {c['tried']}, noticed by the scorer {c['caught']}"
    )
    out.append("")
    out.append("The decision on any threshold is the owner's; this tool only prints numbers.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Root-cause scripted report (numbers only)")
    parser.add_argument("--cases", help="a cases file (default: cases/root_cause.json)")
    args = parser.parse_args(argv)
    print(render(build(load_cases(args.cases))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
