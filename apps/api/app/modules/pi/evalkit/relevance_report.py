"""Relevance report for the plan cases: scripted code-path check, grouped by split, language,
industry and case kind. A group under the evalkit minimum is "not yet measured". Held-out
results are printed as totals only and must never be used for tuning.

Held-out discipline, fail closed: `build` and `borderline_section` read Held-out cases, so both
require an access log path, who and why, and write one line to the append-only access log BEFORE
they return anything. Without them (or when the log cannot be written) they raise and print
nothing.

Known unlogged path, outside this module and left unchanged: the older extraction report
(`report.py`) prints Held-out totals and Held-out case ids without writing an access log line.

Run from apps/api:
    python -m app.modules.pi.evalkit.relevance_report --access-log FILE --who NAME --why REASON
        [--out FILE]
"""

import argparse
import json
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.modules.pi.evalkit import access_log, relevance, relevance_calibration, scorers, splits

CASES = Path(__file__).with_name("cases") / "plan.json"


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def line(name: str, agg: dict[str, Any]) -> str:
    if not agg["measured"]:
        return f"| {name} | {agg['cases']} | not yet measured | | | |"
    return (
        f"| {name} | {agg['cases']} | {pct(agg['accuracy'])} | {agg['false_relevant']} | "
        f"{agg['missed_relevant']} | {agg['hard_misses']} |"
    )


def _require_access(access_log_path: str | Path | None, who: str, why: str) -> Path:
    if access_log_path is None or not str(access_log_path).strip():
        raise ValueError("reading Held-out cases needs an access log path")
    if not who.strip() or not why.strip():
        raise ValueError("reading Held-out cases needs who and why")
    return Path(access_log_path)


def build(
    cases: list[dict[str, Any]],
    access_log_path: str | Path | None,
    who: str,
    why: str,
) -> tuple[str, dict[str, Any]]:
    log = _require_access(access_log_path, who, why)
    cases = [c for c in cases if c.get("kind") != "borderline_relevance"]
    held_count = sum(1 for c in cases if splits.split_of(c) == splits.HELD_OUT)
    ticket = None
    if held_count:  # the read is logged BEFORE anything is scored or returned
        ticket = access_log.grant(
            log,
            who=who,
            why=why,
            run_id=uuid.uuid4().hex[:12],
            split=splits.HELD_OUT,
            count=held_count,
        )
    scored = [
        relevance.score_case(case, held_out_ok=ticket) | {"split": splits.split_of(case)}
        for case in cases
    ]
    out = [
        "# pi solution relevance: scripted code-path check",
        "",
        relevance.DISCLAIMER,
        "",
        "This tests the relevance scorer and the plan case files against labels written with the",
        "cases. No model is called, so it says nothing about how well pi solves problems. The",
        "check against a grader and against people is done separately (relevance_calibration).",
        f"Groups under {scorers.MIN_CASES} cases are reported as not yet measured.",
        "",
    ]
    head = (
        "| group | cases | verdicts matching the agent-drafted labels (not a score) "
        "| relevant by mistake | relevant missed | limit breaks missed |\n"
        "|---|---|---|---|---|---|"
    )
    totals: dict[str, Any] = {}
    for title, key in (
        ("Split", "split"),
        ("Language", "language"),
        ("Case kind", "kind"),
        ("Industry", "industry"),
    ):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for s in scored:
            # only the Split table shows Held-out; the other tables are Development and
            # Regression, so the Held-out share cannot be derived by subtraction
            if key == "split" or s["split"] != splits.HELD_OUT:
                groups[s[key]].append(s)
        note = "" if key == "split" else " (Development and Regression only)"
        out += [f"## {title}{note}", "", head]
        for name in sorted(groups):
            agg = relevance.aggregate(groups[name])
            totals[f"{key}:{name}"] = agg
            out.append(line(name, agg))
        out.append("")
    out += ["## Cases where a verdict differed (Held-out is not listed)", ""]
    for s in scored:
        if s["split"] == splits.HELD_OUT:
            continue
        wrong = [r for r in s["results"] if r["expected"] != r["got"]]
        if wrong:
            detail = ", ".join(f"{r['id']} expected {r['expected']} got {r['got']}" for r in wrong)
            out.append(f"- {s['id']} ({s['split']}): {detail}")
    return "\n".join(out) + "\n", totals


def borderline_section(access_log_path: str | Path | None, who: str, why: str) -> str:
    """The borderline set: the scorer against agent-drafted labels (not human labels). Held-out
    borderline candidates are only counted, and `borderline_comparison` itself requires the access
    log and writes the line."""
    log = _require_access(access_log_path, who, why)
    found = relevance_calibration.borderline_comparison(relevance_calibration.Access(log, who, why))
    rows = found["development"]
    diff = [r for r in rows if not r["agree"]]
    out = [
        "## Borderline set: scorer against agent-drafted labels (not human labels)",
        "",
        f"Development: {len(rows)} candidates, the scorer differs on {len(diff)}. Held-out: "
        f"{found['held_out_candidates']} candidates counted only (not scored, no labels "
        "committed). A difference is a finding; neither side is changed to remove it.",
        "",
    ]
    out += [
        f"- {r['sample_id']} {r['case_id']}/{r['candidate_id']} ({r['language']}): label "
        f"{r['agent_drafted']}, scorer {r['scorer']}"
        for r in diff
    ]
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    parser.add_argument("--access-log", required=True, help="append-only Held-out access log")
    parser.add_argument("--who", required=True)
    parser.add_argument("--why", required=True)
    args = parser.parse_args()
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    text, totals = build(cases, args.access_log, args.who, args.why)
    text += "\n" + borderline_section(args.access_log, args.who, args.why)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    print(json.dumps({k: v for k, v in totals.items() if k.startswith("split:")}, indent=1))


if __name__ == "__main__":
    main()
