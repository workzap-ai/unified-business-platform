"""Build pi's spec handbook from pi-brain-v3.pdf (Parts 0-3, 5, 6 and the golden conversations).

The handbook is what makes the model itself "know" the specification: `spec_handbook.py` puts the
rules, the voice, the stage guidance and the edge-case answers into pi's prompt each turn, and the
golden conversations as worked examples. Nothing here is written by hand: it is the PDF's own text,
split at its section headings.

Run from apps/api:
    ../../.venv/Scripts/python.exe scripts/build_spec_handbook.py "<path to pi-brain-v3.pdf>"
"""

import argparse
import json
import re
from pathlib import Path

import pypdf

OUT = Path("app/modules/pi/spec/handbook.json")
# (first page, last page), 1-based, inclusive.
PARTS: dict[str, list[tuple[int, int]]] = {
    "0": [(10, 11)],
    "1": [(12, 13)],
    "2": [(14, 18)],
    "3": [(19, 22)],
    "4": [(23, 26)],
    "5": [(27, 29)],
    "6": [(30, 34)],
    "7": [(35, 36), (418, 422)],  # 7.0, then 7.N to 7.Q (the 211 industries are packs)
    "10": [(434, 436)],
}
# 7.N is a list of overlays, each with its own heading line: one handbook section per overlay.
OVERLAYS = {
    "family": "Family businesses and owner-led groups",
    "franchise": "Franchises (franchisor and franchisee)",
    "multi_country": "Multi-country and cross-border businesses",
    "startup": "Startups and early-stage businesses",
    "seasonal": "Seasonal businesses",
    "b2b_b2c": "B2B versus B2C businesses",
    "regulated": "Regulated and restricted trades",
    "enterprise": "Large enterprises and business groups",
    "public": "Public-sector and government clients",
    "existing": "Existing Workzap customers",
    "distress": "Businesses in distress",
}
SKIP = {"4.2", "4.5", "4.7"}  # the schema, the taxonomy table and the scoring live in code
HEADING = re.compile(r"^(\d+(?:\.\d+)+|7\.[A-Z])\s+([A-Z“\"].{2,90})$")
GOLDEN = re.compile(r"^(G\d+)\s+—\s+(.{3,80})$")
ARABIC = re.compile(r"[؀-ۿﭐ-﷿ﹰ-﻿]+")


def clean(text: str) -> str:
    text = text.replace("\t", " ").replace("ʼ", "'").replace("ˮ", '"').replace("“", '"')
    text = text.replace("”", '"').replace("’", "'")
    text = re.sub(r"[  ]+", " ", text)
    return text


def lines_of(reader: pypdf.PdfReader, first: int, last: int) -> list[str]:
    rows: list[str] = []
    for number in range(first, last + 1):
        rows += clean(reader.pages[number - 1].extract_text() or "").split("\n")
    return [r.rstrip() for r in rows]


def sections(rows: list[str], part: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for row in rows:
        stripped = row.strip()
        head = GOLDEN.match(stripped) if part == "10" else HEADING.match(stripped)
        if head and (part == "10" or head.group(1).split(".")[0] == part):
            current = {
                "id": head.group(1),
                "title": head.group(2).strip(),
                "part": part,
                "text": "",
            }
            found.append(current)
            continue
        if current is not None and stripped:
            current["text"] += stripped + "\n"
    return found


def tidy(text: str) -> str:
    """Drop right-to-left runs the extractor reversed (they cannot be read back) and join lines."""
    text = ARABIC.sub("", text)
    text = re.sub(r"[ ]+\n", "\n", text)
    text = re.sub(r"\n(?=[a-z(\"'])", " ", text)  # a sentence the page break split in two
    return re.sub(r"[ ]{2,}", " ", text).strip()


def split_overlays(item: dict[str, str]) -> list[dict[str, str]]:
    """Cut 7.N into one section per overlay at its own heading line."""
    text = item["text"]
    starts = []
    for key, title in OVERLAYS.items():
        at = text.find(title)
        if at >= 0:
            starts.append((at, key, title))
    starts.sort()
    parts: list[dict[str, str]] = []
    for n, (at, key, title) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(text)
        parts.append(
            {"id": f"7.N.{key}", "title": title, "part": "7", "text": text[at:end].strip()}
        )
    return parts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    reader = pypdf.PdfReader(str(args.pdf))
    built: list[dict[str, str]] = []
    for part, ranges in PARTS.items():
        for first, last in ranges:
            for item in sections(lines_of(reader, first, last), part):
                if item["id"] in SKIP or len(item["text"]) < 40:
                    continue
                item["text"] = tidy(item["text"])
                if item["id"] == "7.N":
                    built += split_overlays(item)
                else:
                    built.append(item)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(built, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    total = sum(len(i["text"]) for i in built)
    print(f"{len(built)} sections, {total} characters -> {args.out}")


if __name__ == "__main__":
    main()
