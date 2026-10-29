"""Baseline report: scores every case (scripted replay), groups by split, industry, language
and case kind, and states "not yet measured" for any group with too few labelled cases.
Held-out results are printed as totals only and must never be used for tuning.

Run from apps/api:  python -m app.modules.pi.evalkit.report [--out docs/pi-saas/pi-eval-baseline.md]
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.modules.pi.evalkit import replay, scorers, splits

CASES = Path(__file__).with_name("cases") / "extraction.json"


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def line(name: str, agg: dict[str, Any]) -> str:
    if not agg["measured"]:
        return f"| {name} | {agg['cases']} | not yet measured | | | | |"
    return (
        f"| {name} | {agg['cases']} | {pct(agg['recall'])} | {pct(agg['precision'])} | "
        f"{pct(agg['figure_fidelity'])} | {pct(agg['correction_fidelity'])} | "
        f"{agg['unsupported_cause_cases']} |"
    )


def build(cases: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    scored = []
    for case in cases:
        score = scorers.score_case(case, replay.replay(case))
        score |= {
            "split": splits.split_of(case),
            "industry": case["industry"],
            "language": case.get("language", "en"),
            "kind": case.get("kind", "single"),
        }
        scored.append(score)
    out = [
        "# pi understanding: scripted baseline",
        "",
        "Scripted replay: hand-written reference notes (not model output) go through the real",
        "extraction path, no model call. A high score here proves the code keeps what a good model",
        "returns; it says nothing about the model. The real-model run needs owner approval.",
        f"Groups under {scorers.MIN_CASES} cases are reported as not yet measured.",
        "",
    ]
    head = (
        "| group | cases | problem recall | precision | figures kept | corrections kept "
        "| unsupported causes |\n|---|---|---|---|---|---|---|"
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
            agg = scorers.aggregate(groups[name])
            totals[f"{key}:{name}"] = agg
            out.append(line(name, agg))
        out.append("")
    out += ["## Cases that missed something", ""]
    for s in scored:
        if (
            s["recall"] < 1
            or s["extra"]
            or s["unsupported_causes"]
            or (s["figures_kept"] < s["figures"])
            or s["corrections_applied"] < s["corrections"]
        ):
            out.append(
                f"- {s['id']} ({s['split']}): found {s['found']}/{s['expected']}, "
                f"extra {s['extra']}, figures {s['figures_kept']}/{s['figures']}, "
                f"corrections {s['corrections_applied']}/{s['corrections']}, "
                f"unsupported {s['unsupported_causes']}"
            )
    return "\n".join(out) + "\n", totals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    text, totals = build(replay.load_cases(str(CASES)))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    print(json.dumps({k: v for k, v in totals.items() if k.startswith("split:")}, indent=1))


if __name__ == "__main__":
    main()
