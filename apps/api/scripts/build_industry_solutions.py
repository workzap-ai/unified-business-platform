"""Build pi's industry solutions from "pi Industry Solutions" (Addendum 2), Part 4.

Usage (from apps/api, repo .venv):
    python scripts/build_industry_solutions.py <pi-industry-solutions.pdf> \
        [--out app/modules/pi/packs/solutions] [--report report.json]

Part 4 has the same shape for every one of the 211 industries (problem in the owner's words with
category/sub-type, two quick ideas, what Workzap would build, where the free part stops, the
question to ask first, never-say lines, one sample reply), so the PDF text is split mechanically
into one JSON file per industry, linked to the industry pack by key. Re-running overwrites the
files; the output is committed.

Part 2.4 step 2 is applied while parsing, and nothing is invented to fix an error:
- the build keys of a problem that is not about visibility put an action before a view;
- a view build leads for at most one in four problems of an industry (the rest are reported);
- a Workzap sentence that uses a tool word (dashboard, system, software...) is flagged, and the
  runtime says the phrase-bank sentence of the lead build instead of it (RBUILD01);
- every category must be in the taxonomy, every build key in the catalogue, every problem has
  exactly two quick ideas, and no idea or sentence carries a currency amount or a percentage.
Errors go to the report, the process exits non-zero when there is one.
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.pi import taxonomy  # noqa: E402
from app.modules.pi.language import detect_language  # noqa: E402
from app.modules.pi.solutions import (  # noqa: E402
    ACTION_BUILDS,
    CATALOGUE,
    VIEW_BUILDS,
    banned_tool_words,
)

PACKS = Path(__file__).resolve().parents[1] / "app" / "modules" / "pi" / "packs"
PART4 = "Part 4  Industry solutions"
PAGE = re.compile(r"^=====PAGE \d+=====$")
SECTOR = re.compile(r"^7\.[A-Z] ")
PROBLEM = re.compile(r"^(\d+)\.\s+(.*)$")
BUILD_KEYS = re.compile(
    r"^((?:[a-z]+(?:_[a-z]+)*)(?:\s*\+\s*[a-z]+(?:_[a-z]+)*)*)\s*[^\w\s+]?\s*(.*)$", re.S
)
MONEY = re.compile(
    r"\b(?:rs\.?|pkr|aed|cad|usd)\s*\d|\d\s*(?:%|percent|per cent)|[$₨]\s*\d"
    r"|\d[\d,.]*\s*(?:rupees?|dirhams?)\b",
    re.IGNORECASE,
)
VISIBILITY = "reporting_visibility"
VIEW_SHARE = 4  # a view build may lead at most one problem in this many


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKD", text).lower())


def slug(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "_", name.lower().replace("&", " and ")).strip("_")
    return base[:60].strip("_")


def extract(pdf: Path) -> list[str]:
    from pypdf import PdfReader

    lines: list[str] = []
    for page in PdfReader(str(pdf)).pages:
        lines += (page.extract_text() or "").split("\n")
    return lines


def clean_line(line: str) -> str:
    line = line.replace("ʼ", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    line = line.replace("ˮ", '"').replace("\x00", "")
    line = re.sub(r"[-]", "", line)  # private-use glyphs the PDF font leaves behind
    return re.sub(r"\s+", " ", line).strip()


def contents(lines: list[str]) -> list[tuple[str, str]]:
    """(sector, title) in order, from the Part 4 entries of the table of contents."""
    out: list[tuple[str, str]] = []
    sector = ""
    begun = False
    for raw in lines:
        line = clean_line(raw)
        if not begun:
            begun = line == PART4.replace("  ", " ") or line.startswith("Part 4 Industry")
            continue
        if SECTOR.match(line):
            sector = line
            continue
        if line.startswith("=====PAGE") or not line:
            continue
        if line.startswith(("Part ", "How to use")):
            break
        out.append((sector, line))
    return out


def start_of_part4(lines: list[str]) -> int:
    seen = 0
    for i, raw in enumerate(lines):
        if clean_line(raw).startswith("Part 4 Industry solutions"):
            seen += 1
            if seen == 2:  # the first is the table of contents
                return i
    raise SystemExit("Part 4 heading not found")


def split_entries(lines: list[str], titles: list[tuple[str, str]]) -> list[dict[str, Any]]:
    body = [clean_line(raw) for raw in lines[start_of_part4(lines) :]]
    body = [line for line in body if line and not PAGE.match(line)]
    marks = [i for i, line in enumerate(body) if line == "Top problems and solutions:"]
    if len(marks) != len(titles):
        raise SystemExit(f"{len(marks)} entries in Part 4 but {len(titles)} in the contents")
    entries: list[dict[str, Any]] = []
    sector_of_line: dict[int, str] = {}
    for i, line in enumerate(body):
        if SECTOR.match(line):
            sector_of_line[i] = line
    starts: list[int] = []
    for mark, (_sector, title) in zip(marks, titles, strict=True):
        for width in (1, 2, 3, 4):
            if mark - width >= 0 and norm(" ".join(body[mark - width : mark])) == norm(title):
                starts.append(mark - width)
                break
        else:
            raise SystemExit(f"title not found before its entry: {title!r}")
    for n, (mark, (sector, title)) in enumerate(zip(marks, titles, strict=True)):
        end = starts[n + 1] if n + 1 < len(starts) else len(body)
        chunk = body[mark + 1 : end]
        cut = next((j for j, line in enumerate(chunk) if SECTOR.match(line)), len(chunk))
        entries.append({"title": title, "sector": sector, "lines": chunk[:cut]})
    return entries


FIELDS = (
    ("quick", "- Quick ideas (this week):"),
    ("build", "- Workzap would build:"),
    ("stops", "- Where the free part stops:"),
    ("ask", "- Ask first (only if needed):"),
)


def parse_entry(entry: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    title = entry["title"]
    problems: list[dict[str, Any]] = []
    never: list[str] = []
    person: list[str] = []
    reply: list[str] = []
    mode = "problems"
    current: dict[str, Any] | None = None
    field = ""

    def add(text: str) -> None:
        nonlocal current
        if current is None:
            return
        current[field] = (current.get(field, "") + " " + text).strip()

    for line in entry["lines"]:
        if line.startswith("Never say in this industry"):
            mode, field = "never", ""
            continue
        if line.startswith("Sample solution reply"):
            mode = "sample"
            continue
        if mode == "never":
            bullet = re.match(r"^[•\-–]\s*(.*)$", line) or re.match(r"^(.+)$", line)
            fresh = re.match(r"^[•\-–]\s+", line) or not never
            if fresh:
                never.append(bullet.group(1) if bullet else line)
            else:
                never[-1] = (never[-1] + " " + line).strip()
            continue
        if mode == "sample":
            if line.startswith("> Person:"):
                field = "person"
                person.append(line[len("> Person:") :].strip())
            elif line.startswith("> pi:"):
                field = "pi"
                reply.append(line[len("> pi:") :].strip())
            elif field == "person":
                person.append(line.lstrip("> ").strip())
            elif field == "pi":
                reply.append(line.lstrip("> ").strip())
            continue
        match = PROBLEM.match(line)
        if match and (current is None or field in ("ask", "stops", "build", "quick", "")):
            number = int(match.group(1))
            if number == len(problems) + 1:
                current = {"n": number, "head": match.group(2)}
                problems.append(current)
                field = "head"
                continue
        tagged = next((name for name, prefix in FIELDS if line.startswith(prefix)), None)
        if tagged:
            field = tagged
            add(line[len(dict(FIELDS)[tagged]) :].strip())
        else:
            add(line)
    out_problems = []
    for p in problems:
        parsed, errs = parse_problem(title, p)
        errors += errs
        if parsed:
            out_problems.append(parsed)
    reply_text = " ".join(reply).strip()
    person_text = " ".join(person).strip()
    if not reply_text or not person_text:
        errors.append(f"{title}: sample reply missing")
    sample = {
        "person": person_text,
        "pi": reply_text,
        "language": {"roman_ur": "roman_urdu", "en": "english", "ar": "arabic"}.get(
            detect_language(person_text) or "en", "english"
        ),
    }
    if not never:
        errors.append(f"{title}: no never-say lines")
    return {"problems": out_problems, "never_say": never, "sample_reply": sample}, errors


def parse_problem(title: str, raw: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    n = raw["n"]
    where = f"{title} #{n}"
    head = raw.get("head", "")
    tail = re.match(r"^(.*)\s[—–-]\s*([a-z_]+)/([a-z0-9_]+)\s*$", head)
    if not tail:
        return None, [f"{where}: no category/sub-type in {head[:60]!r}"]
    words = tail.group(1).strip().strip('"').strip()
    category, subtype = tail.group(2), tail.group(3)
    if category not in taxonomy.BY_KEY:
        errors.append(f"{where}: category {category!r} is not in the taxonomy")
    ideas = [i.strip() for i in re.split(r"\s·\s", raw.get("quick", "")) if i.strip()]
    if len(ideas) != 2:
        errors.append(f"{where}: {len(ideas)} quick ideas, exactly 2 are required")
    built = BUILD_KEYS.match(raw.get("build", ""))
    if not built:
        return None, errors + [f"{where}: no build keys in {raw.get('build', '')[:60]!r}"]
    keys = [k.strip() for k in built.group(1).split("+")]
    text = built.group(2).strip().lstrip("—–- ").strip()
    for key in keys:
        if key not in CATALOGUE:
            errors.append(f"{where}: build key {key!r} is not in the catalogue")
    for label, value in (
        ("idea", " ".join(ideas)),
        ("build", text),
        ("stops", raw.get("stops", "")),
    ):
        if MONEY.search(value):
            errors.append(f"{where}: an amount or percentage in the {label} text")
    original = list(keys)
    if category != VISIBILITY and keys and keys[0] in VIEW_BUILDS:
        actions = [k for k in keys if k in ACTION_BUILDS or k not in VIEW_BUILDS]
        if actions:
            keys = [actions[0], *[k for k in keys if k != actions[0]]]
    problem = {
        "id": f"p{n}_{subtype}",
        "n": n,
        "words": words,
        "category": category,
        "subtype": subtype,
        "quick_ideas": ideas,
        "workzap_build": {
            "keys": keys,
            "text": text,
            "tool_words": banned_tool_words(text),
        },
        "ask_first": raw.get("ask", "").strip(),
        "free_stops": raw.get("stops", "").strip(),
    }
    if keys != original:
        problem["workzap_build"]["reordered_from"] = original
    return problem, errors


def view_cap(problems: list[dict[str, Any]], title: str) -> list[str]:
    """At most one problem in four may lead with a view build; report the rest (not rewritten)."""
    if not problems:
        return []
    allowed = max(1, len(problems) // VIEW_SHARE)
    leading = [p for p in problems if p["workzap_build"]["keys"][0] in VIEW_BUILDS]
    over = len(leading) - allowed
    for p in leading:
        p["workzap_build"]["leads_with_view"] = True
    return [f"{title}: {over} view-first problem(s) over the cap of {allowed}"] if over > 0 else []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path, default=PACKS / "solutions")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    lines = extract(args.pdf)
    titles = contents(lines)
    entries = split_entries(lines, titles)
    names = {
        norm(json.loads(p.read_text(encoding="utf-8"))["name"]): p.stem
        for p in (PACKS / "industry").glob("*.json")
    }
    errors: list[str] = []
    warnings: list[str] = []
    args.out.mkdir(parents=True, exist_ok=True)
    written = 0
    for entry in entries:
        title = entry["title"]
        key = names.get(norm(title))
        if key is None:
            key = next((k for n, k in names.items() if n.startswith(norm(title)[:30])), slug(title))
            warnings.append(f"{title}: matched pack {key!r} by prefix")
        if not (PACKS / "industry" / f"{key}.json").exists():
            errors.append(f"{title}: no industry pack {key!r}")
        parsed, errs = parse_entry(entry)
        errors += errs
        warnings += view_cap(parsed["problems"], title)
        data = {
            "industry": key,
            "name": title,
            "sector": entry["sector"],
            "version": "1.0",
            **parsed,
        }
        (args.out / f"{key}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        written += 1
    flagged = sum(
        1
        for p in args.out.glob("*.json")
        for pr in json.loads(p.read_text(encoding="utf-8"))["problems"]
        if pr["workzap_build"]["tool_words"]
    )
    total = sum(
        len(json.loads(p.read_text(encoding="utf-8"))["problems"]) for p in args.out.glob("*.json")
    )
    usage = Counter(
        pr["workzap_build"]["keys"][0]
        for p in args.out.glob("*.json")
        for pr in json.loads(p.read_text(encoding="utf-8"))["problems"]
    )
    report = {
        "industries": written,
        "problems": total,
        "tool_word_sentences": flagged,
        "lead_builds": dict(usage.most_common()),
        "warnings": warnings,
        "errors": errors,
    }
    if args.report:
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps({k: v for k, v in report.items() if k not in ("warnings", "errors")}, indent=2)
    )
    print(f"{len(warnings)} warnings, {len(errors)} errors")
    for line in errors[:40]:
        print("ERROR", line)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
