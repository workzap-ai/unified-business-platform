"""Measure industry detection against the packs' own illustrative exchanges (spec Part 7).

Every industry pack carries an exchange from the specification; the "Person" turns are what a
real owner of that trade said. This feeds them to `industry_packs.detect` three ways (the first
message, the first two, the whole story) and counts how often the primary pack is the pack's own
(right), nothing is loaded (none) or another pack is (wrong). Wrong is the costly one: it loads
another trade's care rules, so prefer no pack over a wrong pack.

Usage (from apps/api, repo .venv):
    python scripts/measure_industry_detection.py [--list wrong|none] [--scenario first|two|all]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.pi import industry_packs  # noqa: E402

SCENARIOS = {
    "first": lambda said: said[:1],
    "two": lambda said: said[:2],
    "all": lambda said: said,
}


def person_turns(pack: dict) -> list[str]:
    return [t["text"] for t in pack.get("exchange", []) if t["role"] == "Person"]


def measure() -> dict[str, dict[str, list[tuple[str, str | None]]]]:
    """scenario -> {"right": [...], "none": [...], "wrong": [...]} of (pack key, picked key)."""
    packs = [p for p in industry_packs.load_packs().values() if p["kind"] == "industry"]
    result: dict[str, dict[str, list[tuple[str, str | None]]]] = {}
    for scenario, pick in SCENARIOS.items():
        buckets: dict[str, list[tuple[str, str | None]]] = {"right": [], "none": [], "wrong": []}
        for pack in packs:
            said = pick(person_turns(pack))
            found = industry_packs.detect(said)
            if not found.industries:
                buckets["none"].append((pack["key"], None))
            elif found.primary == pack["key"]:
                buckets["right"].append((pack["key"], found.primary))
            else:
                buckets["wrong"].append((pack["key"], found.primary))
        result[scenario] = buckets
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", choices=["wrong", "none", "right"])
    parser.add_argument("--scenario", choices=list(SCENARIOS), default="first")
    args = parser.parse_args()
    result = measure()
    for scenario, buckets in result.items():
        total = sum(len(v) for v in buckets.values())
        print(
            f"{scenario:>5}: right {len(buckets['right'])}  none {len(buckets['none'])}  "
            f"wrong {len(buckets['wrong'])}  (of {total})"
        )
    if args.list:
        for key, picked in result[args.scenario][args.list]:
            print(f"  {key} -> {picked}")


if __name__ == "__main__":
    main()
