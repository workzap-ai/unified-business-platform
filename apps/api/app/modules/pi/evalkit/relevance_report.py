"""Relevance report for the plan cases: scripted code-path check, grouped by split, language,
industry and case kind. A group under the evalkit minimum is "not yet measured". Held-out
results are printed as totals only and must never be used for tuning; a run that reads them
can write one line to the append-only access log.

Run from apps/api:  python -m app.modules.pi.evalkit.relevance_report [--out FILE]
        [--access-log FILE --who NAME --why REASON]
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


def build(
    cases: list[dict[str, Any]],
    access_log_path: str | Path | None = None,
    who: str = "",
    why: str = "",
) -> tuple[str, dict[str, Any]]:
    if access_log_path is not None and not (who.strip() and why.strip()):
        raise ValueError("an access log path needs who and why")
    cases = [c for c in cases if c.get("kind") != "borderline_relevance"]
    scored = []
    for case in cases:
        score = relevance.score_case(case) | {"split": splits.split_of(case)}
        scored.append(score)
    held = [s for s in scored if s["split"] == splits.HELD_OUT]
    if access_log_path is not None and held:
        access_log.append(
            access_log_path,
            who=who,
            why=why,
            run_id=uuid.uuid4().hex[:12],
            split=splits.HELD_OUT,
            count=len(held),
        )
    out = [
        "# pi solution relevance: scripted code-path check",
        "",
        "This tests the relevance scorer and the plan case files against labels written with the",
        "cases. No model is called, so it says nothing about how well pi solves problems. The",
        "check against a grader and against people is done separately (relevance_calibration).",
        f"Groups under {scorers.MIN_CASES} cases are reported as not yet measured.",
        "",
    ]
    head = (
        "| group | cases | verdicts matching the labels | relevant by mistake "
        "| relevant missed | limit breaks missed |\n|---|---|---|---|---|---|"
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
            groups[s[key]].append(s)
        out += [f"## {title}", "", head]
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


def borderline_section() -> str:
    """The borderline set: the scorer against agent-drafted labels (not human labels). Held-out
    borderline candidates are counted only."""
    found = relevance_calibration.borderline_comparison()
    rows = found["development"]
    diff = [r for r in rows if not r["agree"]]
    out = [
        "## Borderline set: scorer against agent-drafted labels (not human labels)",
        "",
        f"Development: {len(rows)} candidates, the scorer differs on {len(diff)}. Held-out: "
        f"{found['held_out_candidates']} candidates, differs on {found['held_out_disagreements']} "
        "(counted only). A difference is a finding; neither side is changed to remove it.",
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
    parser.add_argument("--access-log", default="")
    parser.add_argument("--who", default="")
    parser.add_argument("--why", default="")
    args = parser.parse_args()
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    text, totals = build(cases, args.access_log or None, args.who, args.why)
    text += "\n" + borderline_section()
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    print(json.dumps({k: v for k, v in totals.items() if k.startswith("split:")}, indent=1))


if __name__ == "__main__":
    main()
