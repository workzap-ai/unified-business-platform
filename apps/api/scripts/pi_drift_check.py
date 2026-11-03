"""Run the daily drift checks by hand (platform spec A.3 steps 2, 4, 8; A.8). Read-only: no
database, no model call, nothing written unless you ask for a file.

From apps/api with the repo venv:
    python scripts/pi_drift_check.py                       # summary and gaps
    python scripts/pi_drift_check.py --baseline b.json     # also drift against a saved run
    python scripts/pi_drift_check.py --baseline b.json --save   # then save this run as b.json
    python scripts/pi_drift_check.py --csv table.csv       # the 211-row A.4 table
Exit code 1 when drift is found (so a pipeline can alert), 0 otherwise.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.pi import drift_check  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", help="JSON file holding the previous run's baseline")
    parser.add_argument("--save", action="store_true", help="write this run to --baseline")
    parser.add_argument("--csv", help="write the A.4 table here")
    parser.add_argument("--json", help="write the whole report here")
    args = parser.parse_args()
    report = drift_check.build_report()
    previous = None
    if args.baseline and Path(args.baseline).exists():
        previous = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    findings = drift_check.compare(previous, report)
    print(json.dumps({"summary": report["summary"], "versions": report["versions"]}, indent=1))
    print("baseline:", "found" if previous else "none (gaps only)")
    for finding in findings:
        print(finding.line())
    if not findings:
        print("no gaps, no drift")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(report["rows"][0]))
            writer.writeheader()
            writer.writerows(report["rows"])
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1), encoding="utf-8")
    if args.save and args.baseline:
        Path(args.baseline).write_text(
            json.dumps(drift_check.baseline_of(report, findings), indent=1), encoding="utf-8"
        )
    return 1 if any(f.kind == "drift" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
