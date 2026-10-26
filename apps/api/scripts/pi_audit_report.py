"""The loaded-versus-intended audit table (platform spec Part A.4), offline, one row per industry.

For each of the 211 industries: is the pack stored, is the solution entry stored (and which
version: a short hash of the file), does the live detection path pick that industry from three
probe messages written the way an owner says them (the first thing the pack's person says, and
the words of the first two problems of its solution entry), does the pack survive into the
assembled prompt block, how many stored lines carry a banned tool word, and does the sample reply
still end on the shared "automatically" line.

Pass mark (A.4): pack and solution stored 211 of 211; retrieved on at least 2 of 3 probes for
each; present in the prompt block whenever retrieved. Anything below is listed as a gap.
No database, no model call. Usage (from apps/api, repo .venv):
    python scripts/pi_audit_report.py [--json out.json] [--markdown out.md]
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.pi import industry_overlap, industry_packs, solutions  # noqa: E402

PACK_DIR = Path(industry_packs.__file__).parent / "packs" / "industry"
AUTOMATIC = re.compile(r"automatic|khud[- ]?ba[- ]?khud", re.IGNORECASE)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10] if path.exists() else ""


def _probes(pack: dict[str, Any], entry: dict[str, Any] | None) -> list[str]:
    said = [t["text"] for t in pack.get("exchange", []) if t["role"] == "Person"][:1]
    said += [p["words"] for p in (entry or {}).get("problems", [])[:2] if p.get("words")]
    return said[:3]


def _picked(text: str) -> str | None:
    found = industry_overlap.fuse(industry_packs.detect([text]), [text])
    return found.primary


def audit() -> list[dict[str, Any]]:
    packs = industry_packs.load_packs()
    rows: list[dict[str, Any]] = []
    for key in sorted(k for k, p in packs.items() if p["kind"] == "industry"):
        pack = packs[key]
        entry = solutions.load(key)
        probes = _probes(pack, entry)
        hits = sum(1 for probe in probes if _picked(probe) == key)
        in_prompt = ""
        for probe in probes:
            detection = industry_overlap.fuse(industry_packs.detect([probe]), [probe])
            if detection.primary == key:
                block = industry_packs.prompt_section(detection)
                in_prompt = "yes" if pack["name"].lower() in block.lower() else "no"
                break
        lines = 0
        sample = ""
        for problem in (entry or {}).get("problems", []):
            build = (problem.get("workzap_build") or {}).get("text", "")
            lines += bool(solutions.banned_tool_words(build))
        sample = ((entry or {}).get("sample_reply") or {}).get("pi", "")
        rows.append(
            {
                "industry_id": key,
                "pack_stored": "yes" if (PACK_DIR / f"{key}.json").exists() else "no",
                "pack_version": _digest(PACK_DIR / f"{key}.json"),
                "solution_stored": "yes" if entry and entry.get("problems") else "no",
                "solution_version": _digest(solutions.SOLUTIONS_DIR / f"{key}.json"),
                "retrieved_on_probe": f"{hits}/{len(probes)}",
                "final_prompt_contains": in_prompt or "n/a",
                "tool_word_lines": lines,
                "ending_repeat": "yes" if AUTOMATIC.search(sample) else "no",
            }
        )
    return rows


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    weak = [r["industry_id"] for r in rows if int(r["retrieved_on_probe"].split("/")[0]) < 2]
    return {
        "industries": len(rows),
        "pack_stored": sum(r["pack_stored"] == "yes" for r in rows),
        "solution_stored": sum(r["solution_stored"] == "yes" for r in rows),
        "retrieved_on_2_of_3": len(rows) - len(weak),
        "not_retrieved_on_2_of_3": weak,
        "block_missing_from_prompt": [
            r["industry_id"] for r in rows if r["final_prompt_contains"] == "no"
        ],
        "tool_word_lines": sum(r["tool_word_lines"] for r in rows),
        "ending_repeat": sum(r["ending_repeat"] == "yes" for r in rows),
    }


def markdown(rows: list[dict[str, Any]]) -> str:
    cols = list(rows[0])
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json")
    parser.add_argument("--markdown")
    args = parser.parse_args()
    rows = audit()
    print(json.dumps(summary(rows), indent=1))
    if args.json:
        Path(args.json).write_text(json.dumps({"summary": summary(rows), "rows": rows}, indent=1))
    if args.markdown:
        Path(args.markdown).write_text(markdown(rows), encoding="utf-8")


if __name__ == "__main__":
    main()
