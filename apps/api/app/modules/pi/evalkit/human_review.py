"""Two-reviewer human labelling process for the relevance samples (FT-A3).

Steps (the owner names the reviewers; nothing here can arrange them):
  1. `--reviewer-sheets DIR` writes one blank sheet per reviewer (json and csv): empty reviewer
     name, empty verdict column, no label, no scorer output. Each reviewer fills theirs alone.
  2. Each reviewer sheet is loaded (`load_reviewer_sheet`): reviewer named, verdicts from the
     allowed list, only known sample ids, every row answered.
  3. `disagreement_record` lists the samples where the two reviewers differ, as a file with empty
     `adjudicated` and `rationale` fields for a THIRD person, the adjudicator, to fill in.
  4. `adjudicated_labels` merges agreed labels with the adjudicated ones. The adjudicator must be
     a named third person, and every disagreement must be resolved.
  5. `process_report` prints reviewer-vs-reviewer agreement and kappa, then adjudicated-vs-scorer
     and adjudicated-vs-grader as separate lines.

The report refuses to give an 85% human-label result unless two different named reviewers (names
compared case-folded with whitespace collapsed) labelled the same known samples, at least 20 of
them. The library functions run the same checks as the loader on the dicts they are given, so
calling them directly does not skip a check. Agent-drafted labels are never an input here, and a
sheet whose labels are a copy of the agent-drafted labels is rejected.

Usage from apps/api:
  python -m app.modules.pi.evalkit.human_review --reviewer-sheets OUT_DIR
  python -m app.modules.pi.evalkit.human_review --reviewer-a A.json --reviewer-b B.json \\
      [--disagreements-out FILE] [--adjudication FILE] [--grader GRADER.json]
"""

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Any

from app.modules.pi.evalkit import relevance
from app.modules.pi.evalkit import relevance_calibration as cal

MIN_HUMAN_SAMPLES = cal.MIN_HUMAN_SAMPLES
PROPOSED_LEVEL = 85.0  # a proposal until the owner approves it as a gate


def _load(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check_sheet(sheet: dict[str, Any]) -> dict[str, Any]:
    """The checks load_reviewer_sheet makes, for any dict shaped like its result: a named
    reviewer, label_source human, known ids, allowed verdicts, not a copy of the agent labels."""
    if not isinstance(sheet, dict):
        raise ValueError("a reviewer sheet must be a mapping")
    if not cal.norm_name(sheet.get("reviewer")):
        raise ValueError("a reviewer sheet must name its reviewer")
    cal.check_human_labels(sheet)
    return sheet


def write_reviewer_sheets(out_dir: str | Path, reviewers: int = 2) -> list[Path]:
    """One blank sheet per reviewer, each in its own order so they cannot copy a position."""
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    _core, _border, rows = cal.all_rows()
    written = []
    for n in range(1, reviewers + 1):
        mine = [dict(r) for r in rows]
        random.Random(cal.SEED + n).shuffle(mine)
        sheet = {
            "label_source": "human",
            "reviewer": "",
            "allowed_verdicts": list(relevance.VERDICTS),
            "definitions": cal.DEFINITIONS,
            "rows": mine,
        }
        json_path = folder / f"human_review_reviewer_{n}.json"
        json_path.write_text(
            json.dumps(sheet, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
        )
        csv_path = folder / f"human_review_reviewer_{n}.csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["reviewer", *mine[0]])
            writer.writeheader()
            writer.writerows({"reviewer": "", **r} for r in mine)
        written += [json_path, csv_path]
    return written


def load_reviewer_sheet(path: str | Path, require_complete: bool = True) -> dict[str, Any]:
    """A filled reviewer sheet (json). Returns {"reviewer", "labels": {sample_id: verdict}}."""
    data = dict(_load(path))
    if data.get("label_source") != "human":
        raise ValueError("a reviewer sheet must say label_source: human")
    if "human_confirmed" in data:
        raise ValueError("a reviewer sheet must not set human_confirmed itself")
    reviewer = str(data.get("reviewer") or "").strip()
    if not cal.norm_name(reviewer):
        raise ValueError("a reviewer sheet must name its reviewer")
    labels: dict[str, str] = {}
    for row in data.get("rows") or []:
        verdict = str(row.get("verdict") or "").strip()
        if not verdict:
            if require_complete:
                raise ValueError(f"row {row.get('sample_id')} has no verdict")
            continue
        if verdict not in relevance.VERDICTS:
            raise ValueError(f"row {row.get('sample_id')}: {verdict!r} is not an allowed verdict")
        if row["sample_id"] in labels:
            raise ValueError(f"row {row['sample_id']} appears twice")
        labels[row["sample_id"]] = verdict
    sheet = {"label_source": "human", "reviewer": reviewer, "labels": labels}
    return check_sheet(sheet)


def disagreement_record(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    """The samples the two reviewers labelled differently, ready for an adjudicator to fill in."""
    check_sheet(first)
    check_sheet(second)
    if cal.norm_name(first["reviewer"]) == cal.norm_name(second["reviewer"]):
        raise ValueError("a disagreement needs two different reviewers")
    ids = sorted(set(first["labels"]) & set(second["labels"]))
    return {
        "label_source": "human_disagreements",
        "reviewers": [first["reviewer"], second["reviewer"]],
        "adjudicator": "",
        "items": [
            {
                "sample_id": i,
                first["reviewer"]: first["labels"][i],
                second["reviewer"]: second["labels"][i],
                "adjudicated": "",
                "rationale": "",
            }
            for i in ids
            if first["labels"][i] != second["labels"][i]
        ],
    }


def adjudicated_labels(
    first: dict[str, Any], second: dict[str, Any], record: dict[str, Any]
) -> dict[str, str]:
    """Agreed labels plus the adjudicated ones. The adjudicator is a named third person (different
    from both reviewers once names are normalised) and every disagreement is resolved, otherwise
    this refuses."""
    check_sheet(first)
    check_sheet(second)
    adjudicator = cal.norm_name(record.get("adjudicator"))
    if not adjudicator:
        raise ValueError("the disagreement record must name its adjudicator")
    if adjudicator in {cal.norm_name(first["reviewer"]), cal.norm_name(second["reviewer"])}:
        raise ValueError("the adjudicator must be a third person, not one of the two reviewers")
    decided = {i["sample_id"]: i for i in record.get("items") or []}
    out: dict[str, str] = {}
    for sample in sorted(set(first["labels"]) & set(second["labels"])):
        a, b = first["labels"][sample], second["labels"][sample]
        if a == b:
            out[sample] = a
            continue
        verdict = str((decided.get(sample) or {}).get("adjudicated") or "").strip()
        if verdict not in relevance.VERDICTS:
            raise ValueError(f"disagreement {sample} is not adjudicated with an allowed verdict")
        out[sample] = verdict
    return out


def _languages_and_scorer() -> tuple[dict[str, str], dict[str, str]]:
    cases = cal.load_cases()
    by_id = {c["id"]: c for c in cases}
    samples = cal.load_samples() + cal.load_borderline_samples()
    languages = {s["sample_id"]: by_id[s["case_id"]]["language"] for s in samples}
    return languages, cal.scorer_labels(cases, samples)


def acceptance_problem(first: dict[str, Any], second: dict[str, Any]) -> str:
    """Why the pair cannot back an 85% human-label result, or an empty string when it can."""
    check_sheet(first)
    check_sheet(second)
    if cal.norm_name(first["reviewer"]) == cal.norm_name(second["reviewer"]):
        return "both sheets come from the same reviewer"
    if set(first["labels"]) != set(second["labels"]):
        return "the two reviewers did not label the same samples"
    known = cal.known_sample_ids()
    both = len(set(first["labels"]) & set(second["labels"]) & known)
    if both < MIN_HUMAN_SAMPLES:
        return f"fewer than {MIN_HUMAN_SAMPLES} known samples were labelled by both reviewers"
    return ""


def eligible_for_acceptance(first: dict[str, Any], second: dict[str, Any]) -> tuple[bool, int]:
    problem = acceptance_problem(first, second)
    both = len(set(first["labels"]) & set(second["labels"]) & cal.known_sample_ids())
    return problem == "", both


def process_report(
    first: dict[str, Any],
    second: dict[str, Any],
    adjudicated: dict[str, str] | None = None,
    grader: dict[str, str] | None = None,
) -> str:
    problem = acceptance_problem(first, second)  # validates both sheets
    languages, scorer = _languages_and_scorer()
    both = len(set(first["labels"]) & set(second["labels"]) & cal.known_sample_ids())
    lines = [
        f"Human review: reviewers {first['reviewer']} and {second['reviewer']}, "
        f"{both} samples labelled by both",
        "",
    ]
    lines += cal._fmt(
        "reviewer vs reviewer", cal.agreement(first["labels"], second["labels"], languages)
    )
    lines.append("")
    if adjudicated is not None:
        pairs = [("adjudicated vs scorer", scorer)]
        if grader is not None:
            pairs.append(("adjudicated vs grader", grader))
        for name, other in pairs:
            result = cal.agreement(adjudicated, other, languages)
            if not result["n"]:
                lines += [f"{name}: no overlap between the two label sets, nothing to compare", ""]
            else:
                lines += cal._fmt(name, result) + [""]
    if problem:
        lines.append(
            f"No 85% human-label result: {problem}. This needs at least {MIN_HUMAN_SAMPLES} "
            f"independently human-labelled samples from two different named reviewers (have "
            f"{both}). Nothing here may be quoted as an acceptance result."
        )
    elif adjudicated is None or grader is None:
        lines.append(
            "Eligible for the 85% test (two reviewers, enough samples), but it is evaluated only "
            "with adjudicated labels and a grader file."
        )
    else:
        result = cal.agreement(adjudicated, grader, languages)
        if not result["n"] or result["percent"] is None:
            lines.append("No 85% comparison: the grader file shares no sample ids (no overlap).")
        else:
            verdict = "meets" if result["percent"] >= PROPOSED_LEVEL else "does not meet"
            lines.append(
                f"Proposed 85% test (the owner has not approved it as a gate): adjudicated vs "
                f"grader {result['percent']:.0f}% on {result['n']} samples {verdict} the proposed "
                "level."
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewer-sheets", default="", help="write blank per-reviewer sheets")
    parser.add_argument("--reviewer-a", default="")
    parser.add_argument("--reviewer-b", default="")
    parser.add_argument("--disagreements-out", default="")
    parser.add_argument("--adjudication", default="", help="filled disagreement record")
    parser.add_argument("--grader", default="", help="grader results JSON: id -> verdict")
    args = parser.parse_args()
    if args.reviewer_sheets:
        for path in write_reviewer_sheets(args.reviewer_sheets):
            print("wrote", path)
    if args.reviewer_a and args.reviewer_b:
        first, second = load_reviewer_sheet(args.reviewer_a), load_reviewer_sheet(args.reviewer_b)
        if args.disagreements_out:
            record = disagreement_record(first, second)
            Path(args.disagreements_out).write_text(
                json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
            )
            print("wrote", args.disagreements_out, f"({len(record['items'])} disagreements)")
        adjudicated = (
            adjudicated_labels(first, second, _load(args.adjudication))
            if args.adjudication
            else None
        )
        grader = cal._grader_map(_load(args.grader)) if args.grader else None
        print(process_report(first, second, adjudicated, grader))


if __name__ == "__main__":
    main()
