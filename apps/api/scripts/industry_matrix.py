"""Stage 1 industry matrix: one row per industry (211) plus overlays (11). Documentation tool only.

Usage (from apps/api, repo .venv):
    python scripts/industry_matrix.py --cases-ref pi/ps0-baseline \
        --out-csv ../../docs/pi-saas/pi-industry-matrix.csv

It reads packs/industry/<key>.json, packs/solutions/<key>.json,
docs/pi-saas/pi-211-industry-check.csv and, through `git show <ref>:<path>`, the three evalkit
case files. From the case files it reads ONLY the `industry` field, the `id` (for the stable
split hash) and `provenance.reviewer`; it never reads, prints or stores case text, so no
Held-out case content is touched. No model call, no database.

Verification rule (stated, not inferred): Verified needs independent labelled cases for the industry
AND owner-set thresholds, both met. Thresholds are not set yet and independent cases are 0, so no
industry can be Verified today. Failing = a probe in pi-211-industry-check.csv failed. Everything
else is Not yet measured.
"""

import argparse
import csv
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PI = HERE.parent / "app" / "modules" / "pi"
PACKS = PI / "packs"
CHECK = HERE.parent.parent.parent / "docs" / "pi-saas" / "pi-211-industry-check.csv"
CASE_FILES = ("extraction", "plan", "problem_solving")
CASE_DIR = "apps/api/app/modules/pi/evalkit/cases"

# Owner's target schema -> how a current pack field maps. "present" needs the real element,
# "partial" a related field that is not the element, "absent" nothing.
TARGET = (
    ("terminology", "vocabulary", "present"),
    ("problems", "problems", "present"),
    ("uncommon_problems", None, "absent"),  # no rarity or frequency field on a problem
    ("workflows", None, "absent"),
    ("kpis", None, "absent"),
    ("roles_permissions", "exchange", "partial"),  # exchange lines carry a speaker role only
    ("constraints", "shape_facts", "partial"),  # scoping facts, not structured constraints
    ("root_cause_patterns", None, "absent"),  # causes live in taxonomy.py, not in the pack
    ("solution_patterns", "build_ideas", "present"),
    ("risks_compliance", "care", "partial"),  # care notes are free text marked for human review
    ("integrations", None, "absent"),
    ("validation_scenarios", "exchange", "partial"),  # one illustrative exchange, unlabelled
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def count(value: object) -> int:
    return len(value) if hasattr(value, "__len__") else 0


def element_status(pack: dict, field: str | None, level: str) -> str:
    if field is None:
        return "absent"
    return level if count(pack.get(field)) else "absent"


def case_rows(ref: str) -> dict[str, Counter]:
    """industry -> Counter(total, dev_visible, independent) per file; no case text is kept."""
    out: dict[str, Counter] = defaultdict(Counter)
    for name in CASE_FILES:
        raw = subprocess.run(
            ["git", "show", f"{ref}:{CASE_DIR}/{name}.json"],
            capture_output=True,
            check=True,
            cwd=HERE,
        ).stdout.decode("utf-8")
        for case in json.loads(raw):
            key = case.get("industry") or "(none)"
            held_out = (
                int(hashlib.sha256(str(case.get("id")).encode()).hexdigest()[:2], 16) % 100 < 25
            )
            out[key][f"{name}_total"] += 1
            out[key]["total"] += 1
            if not held_out:
                out[key]["dev_hash_split"] += 1
            reviewer = (case.get("provenance") or {}).get("reviewer")
            if reviewer:
                out[key]["independent"] += 1
    return out


def probes() -> dict[str, dict]:
    with CHECK.open(encoding="utf-8", newline="") as handle:
        return {row["industry_id"]: row for row in csv.DictReader(handle)}


def probe_failed(row: dict | None) -> bool:
    if not row:
        return False
    return (
        row["identified_on_probe"] != row["probes"]
        or row["retrieved_on_probe"] != "yes"
        or row["tool_word_lines"] != "0"
        or row["ending_repeat"] != "no"
    )


def status(key: str, row: dict | None, cases: Counter) -> str:
    # Verified is unreachable until owner-set thresholds exist (none today); see module docstring.
    if probe_failed(row):
        return "Failing"
    return "Not yet measured"


def build(cases_ref: str) -> list[dict]:
    cases = case_rows(cases_ref)
    probe_rows = probes()
    rows = []
    for path in sorted((PACKS / "industry").glob("*.json")):
        pack = load(path)
        key = pack["key"]
        sol_path = PACKS / "solutions" / f"{key}.json"
        sol = load(sol_path) if sol_path.exists() else {}
        sol_problems = sol.get("problems") or []
        probe = probe_rows.get(key)
        c = cases.get(key, Counter())
        row = {
            "key": key,
            "kind": pack["kind"],
            "sector": (pack.get("sector") or {}).get("title", ""),
            "signals": count(pack.get("signals")),
            "problems": count(pack.get("problems")),
            "vocabulary": count(pack.get("vocabulary")),
            "care": count(pack.get("care")),
            "build_ideas": count(pack.get("build_ideas")),
            "questions": count(pack.get("questions")),
            "exchange": count(pack.get("exchange")),
            "solution_problems": len(sol_problems),
            "solution_version": sol.get("version", ""),
            "solution_quick_ideas": sum(count(p.get("quick_ideas")) for p in sol_problems),
        }
        for name, field, level in TARGET:
            row[f"el_{name}"] = element_status(pack, field, level)
        row["probe_runs"] = probe["probes"] if probe else ""
        row["probe_identified"] = probe["identified_on_probe"] if probe else ""
        row["probe_retrieved"] = probe["retrieved_on_probe"] if probe else ""
        row["probe_tool_word_lines"] = probe["tool_word_lines"] if probe else ""
        row["probe_ending_repeat"] = probe["ending_repeat"] if probe else ""
        row["cases_total"] = c["total"]
        row["cases_extraction"] = c["extraction_total"]
        row["cases_plan"] = c["plan_total"]
        row["cases_problem_solving"] = c["problem_solving_total"]
        row["cases_independent"] = c["independent"]
        row["status"] = status(key, probe, c)
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases-ref", default="pi/ps0-baseline")
    parser.add_argument("--out-csv", required=True)
    args = parser.parse_args()
    rows = build(args.cases_ref)
    with open(args.out_csv, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    industries = [r for r in rows if r["kind"] == "industry"]
    print(
        json.dumps(
            {
                "industries": len(industries),
                "overlays": len(rows) - len(industries),
                "status": dict(Counter(r["status"] for r in industries)),
                "with_cases": sum(1 for r in industries if r["cases_total"]),
                "with_independent": sum(1 for r in industries if r["cases_independent"]),
            }
        )
    )


if __name__ == "__main__":
    main()
