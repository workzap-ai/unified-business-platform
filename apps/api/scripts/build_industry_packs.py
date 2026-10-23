"""Build pi's industry packs from the "pi - The Brain" specification PDF (Part 7).

Usage (from apps/api, repo .venv):
    python scripts/build_industry_packs.py <pi-brain.pdf> [--out app/modules/pi/packs/industry]

Each industry in Part 7 has the same sections, so the PDF text is split mechanically into one
JSON file per industry (the spec calls for YAML; JSON keeps the backend free of a new
dependency and parses the same). Re-running overwrites the packs; the output is committed.
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

SECTIONS = {
    "Recognise": "recognise",
    "Shape facts pi learns": "shape_facts",
    "Scope rule": "scope_rule",
    "Words they use": "words",
    "Problems pi will hear": "problems",
    "Problems": "problems",
    "Questions pi asks": "questions",
    "Questions": "questions",
    "Seasons and peaks": "seasons",
    "Handle with care": "care",
    "What Workzap might build": "build",
    "Might build": "build",
    "Illustrative exchange": "exchange",
}
HEADING = re.compile(
    r"^(" + "|".join(re.escape(h) for h in sorted(SECTIONS, key=len, reverse=True)) + r")"
    r"(?: \([^)]*\))?:\s*(.*)$"
)
# overlays without a "Recognise:" heading
EXTRA_STARTS = ("B2B versus B2C businesses", "Public-sector and government clients")
SECTOR = re.compile(r"^7\.([A-Z]) (.+)$")
OPEN, CLOSE = "“", "ˮ"  # the PDF closes “quotes” with a modifier letter


def extract(pdf: Path) -> str:
    from pypdf import PdfReader

    pages = [page.extract_text() or "" for page in PdfReader(str(pdf)).pages]
    text = "\n".join(pages).replace("\t", " ")
    start = text.rfind("Part 7 — Industry playbooks (Layer L3)")
    end = text.find("Part 8 — The self-learning brain", start)
    if start < 0 or end < 0:
        sys.exit("Part 7 not found in the PDF")
    return text[start:end]


ARABIC_CHARS = r"\u0600-\u06ff\u0750-\u077f\ufb50-\ufdff\ufe70-\ufeff"
ARABIC = rf"[{ARABIC_CHARS}]"
GAP = "\u2016"  # marks where a lost ")" and its separator were


def strip_arabic(line: str) -> str:
    """The PDF prints an Arabic gloss as "( <reversed glyphs>,)", split over lines, with the
    closing bracket and the separator after it lost. Remove the glyphs and keep the structure:
    a closed gloss that ends a list item becomes its comma, an open one becomes a GAP marker
    that the signal and vocabulary parsers read as the separator."""
    if not re.search(ARABIC, line):
        return line
    arab = rf"{ARABIC}[\s{ARABIC_CHARS}]*"
    line = re.sub(rf"\(\s*{arab}\s*,\s*\)", ",", line)  # "( x,)"  ->  ","
    line = re.sub(rf"\(\s*{arab}\s*\.\s*\)", ".", line)  # "( x.)"  ->  "."
    line = re.sub(rf"\(\s*{arab}\s*\)", "", line)  # "( x)"   ->  nothing
    line = re.sub(rf"\(\s*{arab}\s*,", "(", line)  # "( x, branch)" -> "( branch)"
    line = re.sub(rf"\(\s*{arab}", GAP, line)  # "( x" (the ")" was lost) -> a gap
    line = re.sub(arab, "", line)  # any bare run (a heading such as the retail names)
    return re.sub(r"\s+", " ", line).strip()


def unwrap(text: str) -> str:
    """A hyphen at a line break is a compound word, not a hyphen and a space."""
    return re.sub(r"(?<=[A-Za-z])- (?=[A-Za-z])", "-", text)


def clean(text: str) -> list[str]:
    text = text.replace("\t", " ").replace("=====PAGE=====", "")
    text = re.sub(r"-\s*\n\*([^*\n]+)\*\n\s*—\s*", r"- *\1* — ", text)
    text = text.replace(CLOSE, "”").replace("ʼ", "’")
    lines = [strip_arabic(re.sub(r"\s+", " ", line).strip()) for line in text.split("\n")]
    return merge([line for line in lines if line])


def merge(lines: list[str]) -> list[str]:
    """Rejoin the fragments the PDF leaves around bold/code spans and wrapped bullets."""
    merged: list[str] = []
    for line in lines:
        previous = merged[-1] if merged else ""
        if previous == "-":
            merged[-1] = "- " + line
        elif previous and (re.match(r"^[,;.)/:—→]", line) or previous.endswith(("→", "(", "/"))):
            joiner = "" if re.match(r"^[,;.)/:]", line) else " "
            merged[-1] = previous + joiner + line
        else:
            merged.append(line)
    return merged


def slug(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = re.sub(r"\([^)]*\)", " ", name.lower().replace("&", " and "))
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")
    return base[:60].strip("_")


def split_commas(text: str) -> list[str]:
    parts, depth, quoted, current = [], 0, False, ""
    for char in text:
        if char == OPEN:
            quoted = True
        elif char == "”":
            quoted = False
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == "," and not quoted and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return [p.strip(" .;") for p in parts if p.strip(" .;")]


def _close_open_brackets(text: str) -> str:
    """A "(" whose ")" was lost with an Arabic gloss separates two list items."""
    out = []
    for at, char in enumerate(text):
        if char == "(":
            rest = text[at + 1 :]
            close = rest.find(")")
            nxt = rest.find("(")
            if close < 0 or (0 <= nxt < close):
                out.append(",")
                continue
        out.append(char)
    return "".join(out)


def _signal_term(part: str) -> str:
    """The word to listen for: a quoted signal keeps the words after it (“L” plate)."""
    quoted = re.match(r"^“([^”]+)”(.*)$", part)
    if quoted:
        rest = re.sub(r"\s*\([^)]*\)", "", quoted.group(2)).strip()
        return f"{quoted.group(1)} {rest}".strip()
    return re.sub(r"\s*\([^)]*\)", "", part).strip()


def signals(text: str) -> list[str]:
    found: list[str] = []
    for part in split_commas(_close_open_brackets(unwrap(text).replace(GAP, ","))):
        term = _signal_term(part)
        if term and term.lower() not in (s.lower() for s in found):
            found.append(term)
    return found


def signal_glosses(text: str) -> dict[str, str]:
    """ "asmida (fertilisers)" in the signal list: what the local word means."""
    glosses: dict[str, str] = {}
    for part in split_commas(_close_open_brackets(unwrap(text).replace(GAP, ","))):
        meaning = re.search(r"\(([^()]+)\)\s*$", part)
        term = _signal_term(part)
        if (
            meaning
            and term
            and meaning.group(1).strip()[:1].isalpha()
            and meaning.group(1).strip().lower() != term.lower()
        ):
            glosses.setdefault(term, meaning.group(1).strip())
    return glosses


def bullets(lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        if line.startswith("- "):
            items.append(line[2:].strip())
        elif items:
            items[-1] += " " + line
        elif line:
            items.append(line)
    return items


def vocabulary(lines: list[str]) -> dict[str, str]:
    words: dict[str, str] = {}
    for item in bullets(lines):
        item = item.replace(GAP, "—")  # the dash was lost with the Arabic gloss
        match = re.match(r"^\*?([^*]+?)\*?\s*—\s*(.+)$", item)
        if not match:
            continue
        term, meaning = match.group(1).strip(), match.group(2).strip()
        # two terms on one bullet ("chhota gosht = mutton; bara gosht — beef") stay together
        words[unwrap(term)] = unwrap(meaning)
    return words


# The specification files these under a category the taxonomy does not put them in: the
# subtype is right, the category is a slip. The pack follows the taxonomy.
FIX_SUBTYPE = {
    ("communication_coordination", "handoffs"): ("operations_process", "handoffs"),
    ("marketing_leads", "conversion_low"): ("sales_revenue", "conversion_low"),
    ("cash_collections", "cash_leakage"): ("loss_security", "cash_leakage"),
    ("loss_security", "shrinkage_theft"): ("stock_inventory", "shrinkage_theft"),
    ("suppliers_purchasing", "raw_material_shortage"): (
        "stock_inventory",
        "raw_material_shortage",
    ),
    ("suppliers_purchasing", "slow_replenishment"): ("stock_inventory", "slow_replenishment"),
    ("operations_process", "rework"): ("quality_complaints", "rework"),
}


def problems(lines: list[str]) -> list[dict[str, str]]:
    text = " ".join(lines)
    found = []
    for match in re.finditer(r"(.+?)\s*→\s*([a-z_]+)/([a-z0-9_]+)", text):
        phrase = re.sub(r"^[\s;.\-]+|\s*\([^)]*\)\s*$", "", match.group(1)).strip()
        phrase = re.sub(r"^\([^)]*\)\s*-?\s*", "", phrase).strip(' “”"')
        if phrase:
            category, subtype = FIX_SUBTYPE.get(
                (match.group(2), match.group(3)), (match.group(2), match.group(3))
            )
            found.append({"phrase": phrase, "category": category, "subtype": subtype})
    return found


def questions(lines: list[str]) -> dict[str, list[str]]:
    bank: dict[str, list[str]] = {}
    for item in bullets(lines):
        area, _, rest = item.partition(":")
        asked = [q.strip() for q in rest.split("→") if q.strip()]
        if asked:
            bank[area.strip().lower()] = asked
    return bank


def exchange(lines: list[str]) -> list[dict[str, str]]:
    turns: list[dict[str, str]] = []
    for line in lines:
        if line in (">", "> Person:", "> pi:"):
            continue
        match = re.match(r"^(Person|pi):\s*(.*)$", line)
        if match:
            turns.append({"role": match.group(1), "text": match.group(2)})
        elif turns:
            turns[-1]["text"] = (turns[-1]["text"] + " " + line).strip()
    return [t for t in turns if t["text"]]


def build_pack(name: str, sector: dict[str, str], body: dict[str, list[str]]) -> dict:
    pack = _build_pack(name, sector, body)
    return _unwrapped(pack)


def _unwrapped(value: Any) -> Any:
    if isinstance(value, str):
        return unwrap(value)
    if isinstance(value, list):
        return [_unwrapped(v) for v in value]
    if isinstance(value, dict):
        return {k: _unwrapped(v) for k, v in value.items()}
    return value


def _build_pack(name: str, sector: dict[str, str], body: dict[str, list[str]]) -> dict:
    return {
        "key": slug(name),
        "name": name,
        "kind": "overlay" if sector["code"] == "N" else "industry",
        "sector": sector,
        "signals": signals(" ".join(body.get("recognise", []))),
        "signal_glosses": signal_glosses(" ".join(body.get("recognise", []))),
        "notes": " ".join(body.get("notes", [])),
        "shape_facts": bullets(body.get("shape_facts", [])),
        "scope_rule": " ".join(body.get("scope_rule", [])),
        "vocabulary": vocabulary(body.get("words", [])),
        "problems": problems(body.get("problems", [])),
        "questions": questions(body.get("questions", [])),
        "seasons": " ".join(body.get("seasons", [])),
        "care": bullets(body.get("care", [])),
        "build_ideas": bullets(body.get("build", [])),  # internal: drafter only, never said
        "exchange": exchange(body.get("exchange", [])),
    }


def sector_entry(code: str, title: str) -> dict[str, Any]:
    """{"code": "C", "title": "...", "part": 2}; `part` only for a sector the PDF splits in two."""
    part = re.search(r" \(part (\d)\)$", title)
    entry: dict[str, Any] = {"code": code, "title": re.sub(r" \(part \d\)$", "", title)}
    if part:
        entry["part"] = int(part.group(1))
    return entry


def sector_key(sector: dict[str, Any]) -> str:
    return f"{sector['code']}.{sector.get('part', 1)}"


# The first mention of "pi" in a sector intro starts its never-rules ("pi notes the business
# problems only. It never ..."). A short lead-in in the same sentence ("Across this sector") stays.
PI_WORD = re.compile(r"\bpi(?:['’]s)?\b")


def sector_rules(intro: str) -> str:
    match = PI_WORD.search(intro)
    if not match:
        return ""
    start = match.start()
    sentence_start = max(intro.rfind(". ", 0, start) + 2, 0)
    if 0 <= start - sentence_start <= 40:
        start = sentence_start
    return intro[start:].strip()


def sector_intros(lines: list[str]) -> dict[str, dict[str, Any]]:
    """Each sector's intro paragraph, verbatim, and the never-rules inside it.

    The intro runs from the sector heading to the name of the sector's first industry (the line
    before its "Recognise:"). Sectors N (overlays) onward have no industry intro and are skipped.
    """
    marks = [
        i for i, line in enumerate(lines) if line == "Recognise:" or line.startswith("Recognise: ")
    ]
    found: dict[str, dict[str, Any]] = {}
    for i, line in enumerate(lines):
        match = SECTOR.match(line)
        if not match or match.group(1) in "NOPQ":
            continue
        following = [m for m in marks if m > i]
        if not following or any(SECTOR.match(x) for x in lines[i + 1 : following[0]]):
            continue  # the table-of-contents list of sectors, or a heading with another after it
        intro = unwrap(" ".join(lines[i + 1 : following[0] - 1]))
        entry = sector_entry(match.group(1), match.group(2))
        entry["intro"] = intro
        entry["rules"] = sector_rules(intro)
        found[sector_key(entry)] = entry
    return found


def parse(lines: list[str]) -> list[dict]:
    marks = [
        i
        for i, line in enumerate(lines)
        if line == "Recognise:" or line.startswith("Recognise: ") or line in EXTRA_STARTS
    ]
    packs: list[dict] = []
    sectors = {
        i: sector_entry(m.group(1), m.group(2))
        for i, line in enumerate(lines)
        if (m := SECTOR.match(line))
    }
    for n, mark in enumerate(marks):
        extra = lines[mark] in EXTRA_STARTS
        name_at = mark if extra else mark - 1
        nxt = (
            marks[n + 1] - (0 if lines[marks[n + 1]] in EXTRA_STARTS else 1)
            if n + 1 < len(marks)
            else len(lines)
        )
        stops = [i for i in sectors if mark < i < nxt]
        end = min(stops) if stops else nxt
        before = [i for i in sectors if i < name_at]
        sector = sectors[max(before)] if before else {"code": "", "title": ""}
        body: dict[str, list[str]] = {}
        current = "notes" if extra else "recognise"
        rest = None if extra else HEADING.match(lines[mark])
        body[current] = [rest.group(2)] if rest and rest.group(2) else []
        for i in range(mark + 1, end):
            line = lines[i]
            heading = HEADING.match(line) or re.match(r"^(What Workzap might build)\b.*:\s*$", line)
            if heading:
                current = SECTIONS[heading.group(1)]
                body.setdefault(current, [])
                if len(heading.groups()) > 1 and heading.group(2):
                    body[current].append(heading.group(2))
                continue
            body.setdefault(current, []).append(line)
        # trailing sector heading + intro paragraph belong to the next pack, not this exchange
        tail = body.get("exchange", [])
        for j in range(len(tail) - 1, -1, -1):
            if SECTOR.match(tail[j]):
                body["exchange"] = tail[:j]
                break
        packs.append(build_pack(lines[name_at], sector, body))
    return packs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path, default=Path("app/modules/pi/packs/industry"))
    args = parser.parse_args()
    lines = clean(extract(args.pdf))
    packs = parse(lines)
    args.out.mkdir(parents=True, exist_ok=True)
    intros = sector_intros(lines)
    (args.out.parent / "sector_rules.json").write_text(
        json.dumps(intros, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"{len(intros)} sector intros -> {args.out.parent / 'sector_rules.json'}")
    seen: dict[str, int] = {}
    for pack in packs:
        seen[pack["key"]] = seen.get(pack["key"], 0) + 1
        if seen[pack["key"]] > 1:
            pack["key"] += f"_{seen[pack['key']]}"
        (args.out / f"{pack['key']}.json").write_text(
            json.dumps(pack, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    print(f"{len(packs)} packs -> {args.out}")


if __name__ == "__main__":
    main()
