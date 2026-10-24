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
PART4 = re.compile(r"^Part 4\s*[—–-]?\s*Industry solutions$")
PAGE = re.compile(r"^=====PAGE \d+=====$")
SECTOR = re.compile(r"^7\.[A-Z] ")
PROBLEM = re.compile(r"^(\d+)\.\s+(.*)$")
KEY_TOKEN = re.compile(r"^([a-z]+(?:_[a-z]+)*)\b")
JOINER = re.compile(r"^\s*(?:\+|,|and)\s*")
SEPARATOR = re.compile(r"^\s*[—–-]\s*")


def split_build(raw: str) -> tuple[list[str], str] | None:
    """The build keys and the sentence that follows, however the PDF wrote the join: "a + b",
    "a, b", "a and b", or a bare space where the "+" glyph was lost in extraction. Each token is
    checked against the real catalogue as it is consumed, so ordinary prose beginning with a
    plain word is never mistaken for a build key."""
    rest = raw
    keys: list[str] = []
    while True:
        token = KEY_TOKEN.match(rest)
        if not token or token.group(1) not in CATALOGUE:
            break
        keys.append(token.group(1))
        rest = rest[token.end() :]
        joined = JOINER.match(rest)
        if joined and KEY_TOKEN.match(rest[joined.end() :]):
            rest = rest[joined.end() :]
            continue
        break
    if not keys:
        return None
    sep = SEPARATOR.match(rest)
    return keys, (rest[sep.end() :] if sep else rest).strip()


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
    """pypdf resolves this PDF's embedded font cmap wrong for punctuation (hyphens, en/em
    dashes, parentheses, pluses, the bullet, curly quotes all come back as private-use-area
    glyphs, differently per font subset): pymupdf reads the same glyphs correctly. Needs
    `pip install pymupdf`; this script is a one-off generator, not imported by the app, so it
    is not in the hash-locked requirements files."""
    import pymupdf

    lines: list[str] = []
    for n, page in enumerate(pymupdf.open(str(pdf)), start=1):
        lines.append(f"=====PAGE {n}=====")
        lines += (page.get_text() or "").split("\n")
    return lines


def clean_line(line: str) -> str:
    line = line.replace("ʼ", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    line = line.replace("ˮ", '"').replace("\x00", "")
    line = re.sub(r"[-]", "", line)  # defensive: none expected from pymupdf
    return re.sub(r"\s+", " ", line).strip()


def contents(lines: list[str]) -> list[tuple[str, str]]:
    """(sector, title) in order, from the Part 4 entries of the table of contents."""
    out: list[tuple[str, str]] = []
    sector = ""
    begun = False
    for raw in lines:
        line = clean_line(raw)
        if not begun:
            begun = bool(PART4.match(line))
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
        if PART4.match(clean_line(raw)):
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


def glue(before: str, text: str) -> str:
    """Join two line fragments the way the PDF meant them: a compound word split across its own
    visual line wrap ("sign-" / "off") gets no space, unless what follows the hyphen is "and"/"or"
    ("pre- and post-harvest"), which is correct English, not a wrap."""
    coordinator = re.match(r"^(?:and|or)\b", text, re.IGNORECASE)
    sep = "" if re.search(r"[a-z]-$", before) and not coordinator else " "
    return (before + sep + text).strip()


def smart_join(parts: list[str]) -> str:
    text = ""
    for part in parts:
        text = glue(text, part) if text else part
    return text


ARABIC_LETTER = re.compile(r"[؀-ۿ]")


def garbled_script(text: str) -> bool:
    """An Arabic page whose font the extractor could not read: real Arabic prose runs several
    letters per word, so a majority of one-or-two-letter "words" is the signature of per-glyph
    reordering gone wrong. Short English words are completely normal, so this only applies where
    the text is itself mostly Arabic script."""
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 40 or sum(1 for c in letters if ARABIC_LETTER.match(c)) / len(letters) < 0.5:
        return False
    words = [w.strip(".,()،؟!") for w in text.split()]
    words = [w for w in words if w]
    short = sum(1 for w in words if len(w) <= 2)
    return short / len(words) > 0.3


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
        current[field] = glue(current.get(field, ""), text)

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
                never[-1] = glue(never[-1], line)
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
    reply_text = smart_join(reply)
    # The document's own closing sentence leaks into the last industry's sample (end matter).
    reply_text = re.sub(
        r"\s*Every sample conversation in this addendum is Illustrative\.?\s*$", "", reply_text
    )
    person_text = smart_join(person)
    if not reply_text or not person_text:
        errors.append(f"{title}: sample reply missing")
    elif garbled_script(reply_text) or garbled_script(person_text):
        # The PDF's font for this page could not be read correctly (letters reordered within
        # words); nothing here is invented to replace it, so the sample is left out and reported.
        errors.append(f"{title}: the sample reply's script could not be extracted correctly")
        reply_text = person_text = ""
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
    built = split_build(raw.get("build", ""))
    if not built:
        return None, errors + [f"{where}: no build keys in {raw.get('build', '')[:60]!r}"]
    keys, text = built
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
    """At most one problem in four may lead with a view build; report the rest (not rewritten).

    RBUILD02: a view leads without limit when the problem itself is about not seeing
    (category reporting_visibility) — only a view leading for some OTHER kind of problem counts
    against the cap. A problem with no action key among its own listed keys (e.g. both keys are
    views) is reported too: nothing is invented to replace it.
    """
    capped = [p for p in problems if p["category"] != VISIBILITY]
    if not capped:
        return []
    allowed = max(1, len(capped) // VIEW_SHARE)
    leading = [p for p in capped if p["workzap_build"]["keys"][0] in VIEW_BUILDS]
    over = len(leading) - allowed
    for p in leading:
        p["workzap_build"]["leads_with_view"] = True
    return [f"{title}: {over} view-first problem(s) over the cap of {allowed}"] if over > 0 else []


SECTOR_HEADING = re.compile(r"^7\.([A-Z])\s+(.+?)(?:\s*\(part\s*(\d+)\))?$")
SCOPE_START = re.compile(
    r"^(?:Nothing|None of|Everything stays|Personal data stays|Safety,|"
    r"Safety,? labour law|If (?:a child|anyone)|Every idea stays)",
    re.IGNORECASE,
)
SCOPE_MID = re.compile(
    r"\b(?:pi|it)\b.{0,200}?\b(?:never|stays|stops|points to|keeps|sends .{0,40} to)\b",
    re.IGNORECASE,
)


def sector_scopes(lines: list[str]) -> dict[str, str]:
    """Each Addendum 2 sector's own scope-limit sentences (Part 4's intro paragraphs, which Part
    2 of this script otherwise discards): never built from the v3 Brain spec, so packs/
    sector_rules.json has no "rules" for a sector whose BASE intro never says "pi" (A.1, A.2,
    D.1), even though the addendum's own sector intro states limits for every one of them."""
    body = [clean_line(raw) for raw in lines[start_of_part4(lines) :]]
    body = [line for line in body if line and not PAGE.match(line)]
    sectors = [(i, line) for i, line in enumerate(body) if SECTOR.match(line)]
    marks = [i for i, line in enumerate(body) if line == "Top problems and solutions:"]
    scopes: dict[str, str] = {}
    for i, heading in sectors:
        match = SECTOR_HEADING.match(heading)
        following = next((m for m in marks if m > i), None)
        if not match or following is None:
            continue
        intro = smart_join(body[i + 1 : following - 1])
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", intro) if s.strip()]
        scope = [s for s in sentences if SCOPE_START.match(s) or SCOPE_MID.search(s)]
        if scope:
            key = f"{match.group(1)}.{match.group(3) or 1}"
            scopes[key] = smart_join(scope)
    return scopes


def update_sector_rules(scopes: dict[str, str], path: Path) -> list[str]:
    """Add each sector's addendum scope sentence to packs/sector_rules.json, built separately by
    scripts/build_industry_packs.py from the v3 Brain spec. Only a new "addendum_scope" field is
    added; nothing already there (built from a different PDF) is touched or removed."""
    if not path.exists():
        return [f"sector_rules.json not found at {path}, scopes not merged"]
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    warnings = []
    for key, scope in scopes.items():
        if key not in data:
            warnings.append(f"sector {key} has no matching entry in sector_rules.json")
            continue
        data[key]["addendum_scope"] = scope
    missing = sorted(set(data) - set(scopes))
    if missing:
        warnings.append(f"no addendum scope found for sector(s): {', '.join(missing)}")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return warnings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path, default=PACKS / "solutions")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--sector-rules", type=Path, default=PACKS / "sector_rules.json")
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
    scopes = sector_scopes(lines)
    warnings += update_sector_rules(scopes, args.sector_rules)
    report = {
        "industries": written,
        "problems": total,
        "tool_word_sentences": flagged,
        "lead_builds": dict(usage.most_common()),
        "sector_scopes_found": len(scopes),
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
