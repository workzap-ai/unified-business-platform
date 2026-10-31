# ruff: noqa: E501
"""Baseline report for the problem-solving cases: Development and Regression only.

Held-out cases are listed (id and split, nothing else) and never replayed or scored here: `build`
skips them and `replay_case` refuses them without an access Pass.

Run from apps/api:  python -m app.modules.pi.evalkit.ps_report [--out PATH]
"""

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.modules.pi.evalkit import ps_replay, ps_scorers, replay, scorers, splits

CASES = Path(__file__).with_name("cases") / "problem_solving.json"
EXTRACTION = Path(__file__).with_name("cases") / "extraction.json"
SHOWN = (
    "recall", "precision", "figure_fidelity", "correction_detected", "correction_applied",
    "stated_facts_kept", "constraints_kept", "tried_kept", "owner_cause_captured",
    "unsupported_cause", "hypothesis_stays_hypothesis", "relevance_agreement", "false_relevant",
    "violations_missed_by_scorer", "violations_rejected_by_live_filter", "violations_rejected_by_other_than_g8",
    "relevant_kept_by_live_filter", "language_match", "language_undetected", "repeated_question",
    "unclassified_question", "question_form_ok", "blueprint_elements_present",
    "blueprint_dependencies_valid", "blueprint_tied_to_owner_words",
    "blueprint_steps_breaking_a_limit", "blueprint_price_or_promise",
    "constraints_kept_reference", "tried_kept_reference", "owner_cause_captured_reference",
    "stated_facts_kept_reference",
)  # fmt: skip


def cell(agg: dict[str, Any] | None) -> str:
    if not agg or not agg["den"]:
        return "no items"
    text = f"{agg['num']}/{agg['den']}"
    if not agg["measured"]:
        return f"not yet measured ({text}, {agg['cases']} cases)"
    return f"{text} ({agg['num'] * 100 / agg['den']:.0f}%)"


def table(groups: dict[str, list[dict[str, Any]]], names: tuple[str, ...]) -> list[str]:
    """One row per metric, one column per group."""
    keys = sorted(groups)
    aggs = {k: ps_scorers.aggregate(groups[k]) for k in keys}
    out = ["| metric | " + " | ".join(f"{k} ({len(groups[k])} cases)" for k in keys) + " |"]
    out.append("|---|" + "---|" * len(keys))
    for name in names:
        out.append(f"| {name} | " + " | ".join(cell(aggs[k].get(name)) for k in keys) + " |")
    return out


def split_table(cases: list[dict[str, Any]]) -> list[str]:
    rows = ["| case id | split |", "|---|---|"]
    rows += [f"| {c['id']} | {splits.split_of(c)} |" for c in sorted(cases, key=lambda c: c["id"])]
    return rows


def score_all(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        split = splits.split_of(case)
        if split == splits.HELD_OUT:
            continue  # sealed: never replayed or scored
        row = ps_scorers.score_case(case, ps_replay.replay_case(case))
        row |= {
            "split": split,
            "industry": case["industry"],
            "language": case["language"],
            "scenario": case.get("scenario", ""),
        }
        rows.append(row)
    return rows


def regression_rows() -> list[dict[str, Any]]:
    """The existing extraction cases tagged `regression`, through the existing scripted replay."""
    out = []
    for case in replay.load_cases(str(EXTRACTION)):
        if splits.split_of(case) != splits.REGRESSION:
            continue
        s = scorers.score_case(case, replay.replay(case))
        out.append(
            {
                "id": case["id"],
                "industry": case["industry"],
                "language": case["language"],
                "metrics": {
                    "recall": ps_scorers.rate(s["found"], s["expected"]),
                    "precision": ps_scorers.rate(s["found"], s["found"] + s["extra"]),
                    "figure_fidelity": ps_scorers.rate(s["figures_kept"], s["figures"]),
                    "correction_applied": ps_scorers.rate(
                        s["corrections_applied"], s["corrections"]
                    ),
                },
            }
        )
    return out


KEY = (
    "recall", "figure_fidelity", "correction_detected", "stated_facts_kept", "constraints_kept",
    "relevance_agreement", "repeated_question", "language_match", "blueprint_elements_present",
)  # fmt: skip


def build(cases: list[dict[str, Any]]) -> str:
    rows = score_all(cases)
    reg = regression_rows()
    dev = [r for r in rows if r["split"] == splits.DEVELOPMENT]
    by_lang: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_ind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in dev:
        by_lang[r["language"]].append(r)
        by_ind[r["industry"]].append(r)
    out = [
        "## Development, by language", "",
        *table({"all": dev, **by_lang}, SHOWN), "",
        "## Development, by industry (key metrics)", "",
        *table(by_ind, KEY), "",
        "## Regression", "",
        "New problem-solving cases tagged regression: "
        f"{sum(1 for r in rows if r['split'] == splits.REGRESSION)}. Existing extraction cases "
        "tagged regression, through the existing scripted replay:", "",
        *table({"regression (extraction)": reg}, ("recall", "precision", "figure_fidelity",
                                                   "correction_applied")), "",
    ]  # fmt: skip
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    text = build(replay.load_cases(str(CASES)))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    print(ps_scorers.live_blueprint_support())


if __name__ == "__main__":
    main()
