# ruff: noqa: E501
"""Parse the generic Solution Library (platform spec Book 2 Part 7.4, 'Library by category') into
app/modules/pi/packs/library/generic_library.json.

    python scripts/build_generic_library.py --text spec.txt

`spec.txt` is the extracted text of pi-platform-spec.pdf (pages 103 to 106 hold the section; any text
that contains the section works). The quick ideas are taken verbatim, apart from the PDF's modifier
apostrophe written as a plain one. Each idea goes through pi's own idea guard
(solution_rules.check_idea): one that fails is NOT edited, it is moved to `dropped` with the reason,
so a person can see what the spec holds that pi may not say as written.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.pi import solution_rules, solutions, taxonomy  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "app" / "modules" / "pi" / "packs" / "library"
HEADER = re.compile(r"^(?P<name>[^\n(]+?)\s*\((?P<key>[a-z_]+)\)\s*$")
NEEDS_REVIEW_WORDS = ("CCTV",)


def clean(text: str) -> str:
    text = text.replace("ʼ", "'").replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()


def parse(text: str) -> dict[str, dict[str, object]]:
    start = text.index("Library by category")
    body = text[start:]
    end = body.find("Part 8")
    body = body[: end if end > 0 else len(body)]
    lines = [
        ln for ln in body.splitlines() if not ln.startswith("=====") and not ln.startswith("[p")
    ]
    categories: dict[str, dict[str, object]] = {}
    current: dict[str, object] | None = None
    field = ""
    for raw in lines[1:]:
        line = raw.strip()
        header = HEADER.match(line)
        if header and header.group("key") in {c.key for c in taxonomy.CATEGORIES}:
            current = {"quick": "", "build": "", "never": ""}
            categories[header.group("key")] = current
            field = ""
            continue
        if current is None or not line:
            continue
        for label, name in (
            ("Quick ideas:", "quick"),
            ("Workzap would build:", "build"),
            ("Never say:", "never"),
        ):
            if line.startswith(label):
                field = name
                line = line[len(label) :].strip()
                break
        if field:
            current[field] = f"{current[field]} {line}".strip()
    return categories


def build(text: str) -> dict[str, object]:
    categories = parse(text)
    catalogue = set(solutions.CATALOGUE)
    out: dict[str, object] = {
        "version": "1.0",
        "source": "pi-platform-spec Book 2 Part 7.4",
        "categories": {},
    }
    for key, parts in categories.items():
        kept, dropped = [], []
        for idea in str(parts["quick"]).split(" · "):
            idea = clean(idea).rstrip(". ")
            if not idea:
                continue
            verdict = solution_rules.check_idea(idea + ".")
            reasons = [*verdict.reject, *verdict.review]
            if reasons:
                dropped.append({"text": idea, "why": "; ".join(reasons)})
            else:
                kept.append(idea[:1].upper() + idea[1:] + ".")
        keys = [
            k
            for k in re.findall(r"[a-z_]{4,}", str(parts["build"]).split(".")[0])
            if k in catalogue
        ]
        never = clean(str(parts["never"])).rstrip(".")
        out["categories"][key] = {  # type: ignore[index]
            "ideas": kept,
            "dropped": dropped,
            "build_keys": keys,
            "never_say": never,
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True, help="extracted text of pi-platform-spec.pdf")
    args = parser.parse_args()
    data = build(Path(args.text).read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "generic_library.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    cats = data["categories"]
    kept = sum(len(c["ideas"]) for c in cats.values())  # type: ignore[union-attr]
    dropped = sum(len(c["dropped"]) for c in cats.values())  # type: ignore[union-attr]
    print(f"{len(cats)} categories, {kept} ideas kept, {dropped} dropped")


if __name__ == "__main__":
    main()
