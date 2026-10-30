"""Two-reviewer human labelling process for the relevance samples (FT-A3).

Steps (the owner names the reviewers; nothing here can arrange them):
  1. `--reviewer-sheets DIR` writes one blank sheet per reviewer (json and csv): empty reviewer
     name, empty verdict column, no label, no scorer output. Each reviewer fills theirs alone.
  2. Each reviewer sheet is loaded (`load_reviewer_sheet`): reviewer named, verdicts from the
     allowed list, only known sample ids.
  3. `disagreement_record` lists the samples where the two reviewers differ, as a file with empty
     `adjudicated` and `rationale` fields for a THIRD person, the adjudicator, to fill in.
  4. `adjudicated_labels` merges agreed labels with the adjudicated ones. The adjudicator must be
     a third person (a different normalised name), the record must name the same two reviewers,
     and every disagreement must be resolved.
  5. `process_report` prints a NEUTRAL report: the normalised reviewer names, the numbers (n,
     percent, kappa) for reviewer vs reviewer, and, when a record is given, adjudicated vs scorer
     and adjudicated vs grader. It builds the adjudicated labels itself from the record.

This tool never prints or returns an acceptance verdict ("meets the level"). It cannot verify who
the reviewers are or that they worked independently: code cannot prove two names are two people.
The 85% acceptance is a decision the owner records, not something computed here. It keeps only
structural checks that prevent accidents: known ids only, both sheets cover the same ids, at least
20 samples before any agreement is shown, distinct normalised names, two reviewers identical on
every shared id are rejected, and a sheet whose agreement with the agent-drafted labels is at or
above 90% is refused as "agent-copy suspected". The library functions run the same checks as the
loader on the dicts they are given.

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
IDENTITY_NOTE = cal.IDENTITY_NOTE


def _load(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check_sheet(sheet: dict[str, Any]) -> dict[str, Any]:
    """The checks load_reviewer_sheet makes, for any dict shaped like its result: a named
    reviewer, label_source human, known ids, allowed verdicts, not an agent copy."""
    if not isinstance(sheet, dict):
        raise ValueError("a reviewer sheet must be a mapping")
    if not cal.norm_name(sheet.get("reviewer")):
        raise ValueError("a reviewer sheet must name its reviewer")
    cal.check_human_labels(sheet)
    return sheet


def check_pair(first: dict[str, Any], second: dict[str, Any]) -> None:
    """Structural checks on two reviewer sheets (raises ValueError): both valid, distinct
    normalised names, the same ids, and not identical on every shared id."""
    check_sheet(first)
    check_sheet(second)
    if cal.norm_name(first["reviewer"]) == cal.norm_name(second["reviewer"]):
        raise ValueError("both sheets come from the same reviewer (after name normalisation)")
    if set(first["labels"]) != set(second["labels"]):
        raise ValueError("the two reviewers did not label the same samples")
    shared = set(first["labels"]) & set(second["labels"])
    if shared and all(first["labels"][i] == second["labels"][i] for i in shared):
        raise ValueError("the two reviewers are identical on every shared sample: rejected")


def write_reviewer_sheets(
    out_dir: str | Path, reviewers: int = 2, access: cal.Access | None = None
) -> list[Path]:
    """One blank sheet per reviewer, each in its own order so they cannot copy a position."""
    folder = Path(out_dir)
    _core, _border, rows = cal.all_rows(access)  # refuses before anything is written
    folder.mkdir(parents=True, exist_ok=True)
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
    check_pair(first, second)
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
    """Agreed labels plus the adjudicated ones, over exactly the reviewers' common ids. The record
    must name the same two reviewers, its adjudicator is a third person (a different normalised
    name) and every disagreement is resolved, otherwise this refuses."""
    check_pair(first, second)
    if not isinstance(record, dict):
        raise ValueError("the disagreement record must be a mapping")
    names = {cal.norm_name(first["reviewer"]), cal.norm_name(second["reviewer"])}
    listed = record.get("reviewers")
    if not isinstance(listed, list) or {cal.norm_name(r) for r in listed} != names:
        raise ValueError("the disagreement record must name the same two reviewers as the sheets")
    adjudicator = cal.norm_name(record.get("adjudicator"))
    if not adjudicator:
        raise ValueError("the disagreement record must name its adjudicator")
    if adjudicator in names:
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


def _languages_and_scorer(
    access: cal.Access | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    cases = cal.load_cases()
    by_id = {c["id"]: c for c in cases}
    samples = cal.load_samples() + cal.load_borderline_samples()
    languages = {s["sample_id"]: by_id[s["case_id"]]["language"] for s in samples}
    return languages, cal.scorer_labels(cases, samples, access)


def process_report(
    first: dict[str, Any],
    second: dict[str, Any],
    record: dict[str, Any] | None = None,
    grader: Any = None,
    access: cal.Access | None = None,
) -> str:
    """A neutral report: numbers and normalised names, never a verdict. Invalid or inconsistent
    sheets raise ValueError. Adjudicated labels are built here from the record, never trusted."""
    check_pair(first, second)
    adjudicated = adjudicated_labels(first, second, record) if record is not None else None
    n1, n2 = cal.norm_name(first["reviewer"]), cal.norm_name(second["reviewer"])
    both = len(set(first["labels"]) & set(second["labels"]) & cal.known_sample_ids())
    lines = [
        f"Human review: reviewers {n1!r} and {n2!r} (normalised names), "
        f"{both} samples labelled by both",
        "",
    ]
    if both < MIN_HUMAN_SAMPLES:
        lines += [
            f"Too few samples, no agreement shown (have {both}, at least {MIN_HUMAN_SAMPLES} "
            "are needed).",
            "",
            IDENTITY_NOTE,
        ]
        return "\n".join(lines) + "\n"
    languages, scorer = _languages_and_scorer(access)
    lines += cal._fmt(
        "reviewer vs reviewer", cal.agreement(first["labels"], second["labels"], languages)
    )
    lines.append("")
    if adjudicated is not None:
        pairs = [("adjudicated vs scorer", scorer)]
        if grader is not None:
            try:
                pairs.append(("adjudicated vs grader", cal.validate_grader(grader)))
            except ValueError as exc:
                lines += [f"{exc}; no grader comparison is shown.", ""]
        for name, other in pairs:
            result = cal.agreement(adjudicated, other, languages)
            if not result["n"]:
                lines += [f"{name}: no overlap between the two label sets, nothing to compare", ""]
            else:
                lines += cal._fmt(name, result) + [""]
    lines.append(IDENTITY_NOTE)
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewer-sheets", default="", help="write blank per-reviewer sheets")
    parser.add_argument("--reviewer-a", default="")
    parser.add_argument("--reviewer-b", default="")
    parser.add_argument("--disagreements-out", default="")
    parser.add_argument("--adjudication", default="", help="filled disagreement record")
    parser.add_argument("--grader", default="", help="grader results JSON: id -> verdict")
    parser.add_argument("--access-log", default="", help="needed only if a Held-out case is read")
    parser.add_argument("--who", default="")
    parser.add_argument("--why", default="")
    args = parser.parse_args()
    access = cal.Access(args.access_log, args.who, args.why) if args.access_log else None
    if args.reviewer_sheets:
        for path in write_reviewer_sheets(args.reviewer_sheets, access=access):
            print("wrote", path)
    if args.reviewer_a and args.reviewer_b:
        first, second = load_reviewer_sheet(args.reviewer_a), load_reviewer_sheet(args.reviewer_b)
        if args.disagreements_out:
            record = disagreement_record(first, second)
            Path(args.disagreements_out).write_text(
                json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
            )
            print("wrote", args.disagreements_out, f"({len(record['items'])} disagreements)")
        filled = _load(args.adjudication) if args.adjudication else None
        grader = _load(args.grader) if args.grader else None
        print(process_report(first, second, filled, grader, access))


if __name__ == "__main__":
    main()
