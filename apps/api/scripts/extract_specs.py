# ruff: noqa: E501
"""Extract the seven authoritative pi specification PDFs to page-marked, glyph-normalised text.

Pure tooling: deterministic, idempotent, no network, no model calls. Not imported by the app.

    python -I apps/api/scripts/extract_specs.py --pdf-dir <dir with the PDFs> --out <output dir>
    python -I apps/api/scripts/extract_specs.py --pdf-dir <dir> --out <dir> --verify

Per PDF it writes into --out:
  <stem>.txt         normalised text, one `=== PAGE n / N ===` marker per page (1-based, as in a PDF viewer)
  <stem>.raw.txt     the unmodified pypdf text with the same markers (proves the normalisation)
  <stem>.pages.json  per page: chars, first heading, flags, warnings
and, for all PDFs together:
  spec-rule-index.csv / spec-rule-index.json   every rule or requirement id found, with page and line
  extraction-summary.json                       counts used by --verify and by the index documents

Why normalisation is needed. The platform specs were typeset with the Inter font using OpenType alternates
(case-sensitive forms, tabular digits). The PDF producer gave those alternates private-use code points
(U+E071 and up) in the ToUnicode map, so pypdf returns `R<U+E088>OFFER<U+E088>03` for the id `R-OFFER-03`.
The table PUA_MAP below was derived by reading the Type3 glyph outlines of every private-use code point
(rendered and inspected), and the allocation was checked to be identical in all seven PDFs. Any private-use
code point not in the table is kept as `<<U+XXXX>>` and reported as a warning, never silently dropped.
pypdf cannot read diagrams, images or Arabic/Urdu shaping reliably: such pages are flagged for visual review.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

# stem -> PDF file name (the v1.5 file has " (1)" in its name on disk; its stem drops it)
SPEC_FILES: dict[str, str] = {
    "pi-brain-v3": "pi-brain-v3.pdf",
    "pi-industry-solutions": "pi-industry-solutions.pdf",
    "pi-platform-spec": "pi-platform-spec.pdf",
    "pi-platform-spec-1": "pi-platform-spec-1.pdf",
    "pi-platform-spec-v1.4-2026-10-27": "pi-platform-spec-v1.4-2026-10-27.pdf",
    "pi-platform-spec-v1.5-2026-10-28": "pi-platform-spec-v1.5-2026-10-28 (1).pdf",
    "pi-platform-spec-v1.6-2026-10-30": "pi-platform-spec-v1.6-2026-10-30.pdf",
}
# page counts the coordinator verified with pypdf (the verification baseline)
EXPECTED_PAGES: dict[str, int] = {
    "pi-brain-v3": 448,
    "pi-industry-solutions": 467,
    "pi-platform-spec": 141,
    "pi-platform-spec-1": 189,
    "pi-platform-spec-v1.4-2026-10-27": 224,
    "pi-platform-spec-v1.5-2026-10-28": 238,
    "pi-platform-spec-v1.6-2026-10-30": 253,
}

# Private-use code point -> real character, read off the Type3 glyph outlines (see module docstring).
PUA_MAP: dict[int, str] = {
    **{0xE071 + i: str(i) for i in range(10)},  # tabular digits 0..9
    0xE081: "(",
    0xE082: ")",
    0xE083: "[",
    0xE084: "]",
    0xE085: "{",
    0xE086: "}",
    0xE088: "-",  # raised (case-sensitive) hyphen: the hyphens inside rule ids, "R-OFFER-03"
    0xE089: "–",  # en dash (ranges such as 1-3)
    0xE08B: "—",  # em dash
    0xE08C: "•",  # bullet
    0xE092: ":",
    0xE094: ".",
    0xE097: "<",
    0xE098: ">",
    0xE099: "≤",
    0xE09A: "≥",
    0xE09B: "=",
    0xE09D: "+",
    0xE09E: "−",  # minus sign
    0xE09F: "×",
    0xE0A1: "±",
    0xE0A3: "~",
    0xE1D7: "→",
}
# Characters the ToUnicode maps give as modifier letters but that are really quotes/apostrophes.
QUOTE_FIX = {"ˮ": "”", "ʼ": "’"}
PUA_RE = re.compile("[-]")
FILLER = "�"  # NUL (a glyph with no Unicode value, mostly Arabic marks) becomes this and is counted

# ---------------------------------------------------------------- normalisation


def normalise(raw: str) -> tuple[str, dict[str, Any]]:
    """Return (normalised text, per-page stats)."""
    stats: dict[str, Any] = {
        "pua_mapped": 0,
        "pua_unknown": [],
        "nul": 0,
        "ligatures": 0,
        "arabic": 0,
        "nbsp": 0,
    }
    out: list[str] = []
    for ch in raw:
        cp = ord(ch)
        if 0xE000 <= cp <= 0xF8FF:
            if cp in PUA_MAP:
                out.append(PUA_MAP[cp])
                stats["pua_mapped"] += 1
            else:
                out.append(f"<<U+{cp:04X}>>")
                stats["pua_unknown"].append(f"U+{cp:04X}")
        elif cp == 0:
            out.append(FILLER)
            stats["nul"] += 1
        elif ch in QUOTE_FIX:
            out.append(QUOTE_FIX[ch])
        elif cp == 0xA0 or ch == chr(9):
            out.append(" ")  # brain v3 separates words with TAB; non-breaking spaces too
            stats["nbsp"] += 1
        elif cp == 0xAD:
            continue  # soft hyphen
        elif 0xFB00 <= cp <= 0xFB06:
            out.append(unicodedata.normalize("NFKC", ch))
            stats["ligatures"] += 1
        elif 0xFB50 <= cp <= 0xFDFF or 0xFE70 <= cp <= 0xFEFF:
            out.append(
                unicodedata.normalize("NFKC", ch)
            )  # presentation forms -> base letters (order untouched)
            stats["arabic"] += 1
        elif 0x600 <= cp <= 0x6FF or 0x750 <= cp <= 0x77F:
            out.append(ch)
            stats["arabic"] += 1
        else:
            out.append(ch)
    text = "".join(out)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text, stats


# ---------------------------------------------------------------- per-page analysis

BOX_RE = re.compile("[─-╿▲►◄▼]")
FOOTER_RE = re.compile(r"\bpage \d+ of \d+\s*$", re.I)


def _count_images(page: Any) -> int:
    n = 0
    try:
        res = page.get("/Resources")
        xo = res.get_object().get("/XObject") if res else None
        if xo:
            for _k, v in xo.get_object().items():
                v = v.get_object()
                if v.get("/Subtype") == "/Image":
                    n += 1
                elif v.get("/Subtype") == "/Form":
                    sub = v.get("/Resources")
                    sx = sub.get_object().get("/XObject") if sub else None
                    if sx:
                        for _k2, v2 in sx.get_object().items():
                            if v2.get_object().get("/Subtype") == "/Image":
                                n += 1
    except Exception:  # noqa: BLE001 - tooling: report, never crash
        return -1
    return n


def _content_ops(page: Any, reader: Any) -> tuple[int, int]:
    """(rectangle operators, inline images) in the page content stream; tables are drawn with rectangles."""
    try:
        from pypdf.generic import ContentStream

        raw = page.get_contents()
        if raw is None:
            return 0, 0
        ops = Counter(op for _args, op in ContentStream(raw, reader).operations)
        return ops.get(b"re", 0), ops.get(b"BI", 0)
    except Exception:  # noqa: BLE001
        return -1, 0


def first_heading(text: str) -> str:
    for line in text.split("\n"):
        s = line.strip()
        if s and not FOOTER_RE.search(s) and not s.startswith("==="):
            return s[:120]
    return ""


def table_like(text: str, rect_ops: int) -> bool:
    if rect_ops >= 20:
        return True
    if len(BOX_RE.findall(text)) >= 12:
        return True
    lines = [x for x in text.split("\n") if x.strip()]
    pipes = sum(1 for x in lines if x.count("|") >= 2 or x.count("\t") >= 2 or "  " in x.strip())
    return pipes >= 4


def extract_pdf(args: tuple[str, str, str]) -> dict[str, Any]:
    stem, pdf_path, out_dir = args
    import pypdf  # imported here so worker processes import it themselves

    path = Path(pdf_path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    reader = pypdf.PdfReader(str(path))
    total = len(reader.pages)
    raw_parts: list[str] = []
    norm_parts: list[str] = []
    pages: list[dict[str, Any]] = []
    warnings: list[str] = []
    unknown_pua: Counter[str] = Counter()
    for i, page in enumerate(reader.pages, start=1):
        pw: list[str] = []
        try:
            raw = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            raw = ""
            pw.append(f"extract_text failed: {type(exc).__name__}: {exc}")
        norm, st = normalise(raw)
        for u in st["pua_unknown"]:
            unknown_pua[u] += 1
        if st["pua_unknown"]:
            pw.append(f"unmapped private-use glyphs: {sorted(set(st['pua_unknown']))}")
        if st["nul"]:
            pw.append(
                f"{st['nul']} glyph(s) without a Unicode value (shown as U+FFFD; mostly Arabic/Urdu marks)"
            )
        images = _count_images(page)
        rects, inline_imgs = _content_ops(page, reader)
        images = images + inline_imgs if images >= 0 else images
        chars = len(norm.strip())
        if chars == 0:
            pw.append("empty page text")
        low = chars < 200
        flags = {
            "low_text_page": low,
            "contains_table_like_rows": table_like(norm, rects),
            "has_images": images > 0,
            "has_box_drawing": len(BOX_RE.findall(norm)) >= 3,
            "has_unmapped_glyphs": st["nul"] > 0 or bool(st["pua_unknown"]),
            "has_arabic_script": st["arabic"] > 0,
        }
        flags["needs_visual_review"] = bool(
            flags["low_text_page"]
            or flags["has_images"]
            or flags["has_box_drawing"]
            or flags["has_unmapped_glyphs"]
        )
        marker = f"=== PAGE {i} / {total} ===\n"
        raw_parts.append(marker + raw.rstrip("\n") + "\n")
        norm_parts.append(marker + norm.rstrip("\n") + "\n")
        pages.append(
            {
                "page": i,
                "chars": chars,
                "raw_chars": len(raw.strip()),
                "first_heading": first_heading(norm),
                "image_count": images,
                "rect_ops": rects,
                "pua_mapped": st["pua_mapped"],
                "nul_glyphs": st["nul"],
                "ligatures": st["ligatures"],
                "arabic_chars": st["arabic"],
                "flags": flags,
                "warnings": pw,
            }
        )
        for w in pw:
            warnings.append(f"page {i}: {w}")
    out = Path(out_dir)
    (out / f"{stem}.raw.txt").write_text("".join(raw_parts), encoding="utf-8", newline="\n")
    (out / f"{stem}.txt").write_text("".join(norm_parts), encoding="utf-8", newline="\n")
    meta = {
        "pdf": stem,
        "file": path.name,
        "sha256": sha,
        "bytes": path.stat().st_size,
        "pages_pypdf": total,
        "pages": pages,
        "warnings": warnings,
        "unknown_pua": dict(unknown_pua),
    }
    (out / f"{stem}.pages.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {k: v for k, v in meta.items() if k != "pages"} | {"n_pages": total}


# ---------------------------------------------------------------- rule ids

MARK_RE = re.compile(r"^=== PAGE (\d+) / (\d+) ===$")

# An id must not continue a longer token: not preceded by a letter/digit/underscore, nor by `<letters>-` (so the
# `OFFER-03` inside `R-OFFER-03` is not counted twice), and not followed by a letter/digit/underscore.
_B = r"(?<![A-Za-z0-9_])(?<![A-Za-z0-9]-)"
_E = r"(?![A-Za-z0-9_])"
# Scanned in this order on every line; a later family never re-reports text already taken by an earlier one.
#   (family, kind, regex).  kind: rule_id | rule_family_ref | label_code
FAMILIES: list[tuple[str, str, re.Pattern[str]]] = [
    # R-OFFER-03 (platform specs, hyphenated) and ROFFER03 / RSELL01 (brain v3, industry solutions, no hyphens)
    ("R-WORD-NN", "rule_id", re.compile(_B + r"(R-?[A-Z][A-Z]+(?:-[A-Z]+)*-?\d{1,3}[a-z]?)" + _E)),
    # R-OFFER, R-ANS / R-SOL: a whole rule family cited without a number
    ("R-WORD", "rule_family_ref", re.compile(_B + r"(R-[A-Z]{2,}(?:-[A-Z]+)*)" + _E)),
    # items numbered inside an audit table: A4-4, A6-12
    ("A#-n", "label_code", re.compile(_B + r"(A\d-\d{1,3})" + _E)),
    # R1..R4 and B1..B7 (offer conditions), G1..G56 (idea filter and gates), S0..S22 (states), X1.., L0..L2, E1..,
    # OG1, OF1, IL1, AA1, EO1, MD1, BS1, DQ1, TC1, ST1, SL-1, RT1, M1, P1, HO1 ... : letters then digits, one family
    # per letter prefix. Everything of that shape is reported; `kind` and `family` let the matrix filter it.
    ("PREFIX-n", "label_code", re.compile(_B + r"([A-Z]{1,6}-?\d{1,3}[a-z]?)" + _E)),
    # WORD-NN written without the R (VAL-01 in tables)
    ("WORD-NN", "rule_id", re.compile(_B + r"([A-Z]{3,}-\d{1,3}[a-z]?)" + _E)),
    # numbered spec items such as 7.O1
    ("N.On", "label_code", re.compile(_B + r"(\d{1,2}\.[A-Z]\d{1,2})" + _E)),
]
RANGE_RE = re.compile(r"(?:\.\.|…|–|—)\s*(?:R-?[A-Z]+-?)?(\d{1,3})(?![0-9])")
# Section headings: Book n, Part x, Addendum n, numbered sections n.n(.n), A.n
HEAD_RES: list[tuple[int, re.Pattern[str]]] = [
    (1, re.compile(r"^(Book \d+)(?:\s*[:—–-]|$)")),
    (1, re.compile(r"^(Part [A-Z0-9]+)(?:\s*[:—–-]|$)")),
    (1, re.compile(r"^(Addendum \d+)(?:\s*[:—–-]|$)")),
    (2, re.compile(r"^(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)\s+\S")),
    (2, re.compile(r"^([A-Z]\.\d{1,2})\s+\S")),
]


def normalise_id(rule_id: str) -> str:
    """R-OFFER-03 -> ROFFER03 (the key used in code, tests and RULE_INDEX); other ids lose only hyphens."""
    return rule_id.replace("-", "")


def hyphenated(rule_id: str, family: str) -> str:
    """ROFFER03 -> R-OFFER-03, the hyphenated style of docs/pi-saas/pi-rule-coverage.md. Other ids are unchanged."""
    if family != "R-WORD-NN":
        return rule_id
    mm = re.fullmatch(r"R([A-Z]+)(\d{1,3}[a-z]?)", rule_id.replace("-", ""))
    return f"R-{mm.group(1)}-{mm.group(2)}" if mm else rule_id


def scan_rules(stem: str, norm_text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    heads: dict[int, str] = {}
    page = 0
    for lineno, line in enumerate(norm_text.split("\n"), start=1):
        m = MARK_RE.match(line)
        if m:
            page = int(m.group(1))
            continue
        s = line.strip()
        if not s:
            continue
        for level, hre in HEAD_RES:
            hm = hre.match(s)
            if hm and len(s) < 140 and not FOOTER_RE.search(s):
                heads = {k: v for k, v in heads.items() if k < level}
                heads[level] = s[:90]
                rows.append(
                    {
                        "pdf": stem,
                        "page": page,
                        "section_path": " > ".join(heads[k] for k in sorted(heads)),
                        "family": "SECTION",
                        "kind": "section",
                        "rule_id": hm.group(1),
                        "rule_id_hyphenated": hm.group(1),
                        "rule_id_as_printed": hm.group(1),
                        "definition_like": True,
                        "range_expansion": False,
                        "text200": s[:200],
                        "line": lineno,
                    }
                )
                break
        path = " > ".join(heads[k] for k in sorted(heads))
        taken: list[tuple[int, int]] = []
        for fam, kind, fre in FAMILIES:
            for rm in fre.finditer(s):
                a, b = rm.span(1)
                if any(a < tb and ta < b for ta, tb in taken):
                    continue
                taken.append((a, b))
                rid = rm.group(1)
                lead = s[:a].strip(" \t-\u2022*([{\"'\u201c")
                rows.append(
                    {
                        "pdf": stem,
                        "page": page,
                        "section_path": path,
                        "family": fam,
                        "kind": kind,
                        "rule_id": normalise_id(rid),
                        "rule_id_hyphenated": hyphenated(normalise_id(rid), fam),
                        "rule_id_as_printed": rid,
                        # the id opens its line (a definition or list item) rather than being cited mid-sentence
                        "definition_like": lead == "",
                        "range_expansion": False,
                        "text200": s[a : a + 200],
                        "line": lineno,
                    }
                )
    rows.sort(key=lambda r: (r["line"], r["family"] == "SECTION" and -1 or 0))
    return rows


# ---------------------------------------------------------------- driver


def build_index(out_dir: Path, stems: list[str], index_dir: Path) -> dict[str, Any]:
    """Scan the written normalised text for rule ids and write the index and the summary."""
    all_rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    for stem in stems:
        text = (out_dir / f"{stem}.txt").read_text(encoding="utf-8")
        rows = scan_rules(stem, text)
        all_rows.extend(rows)
        meta = json.loads((out_dir / f"{stem}.pages.json").read_text(encoding="utf-8"))
        pg = meta["pages"]
        by_kind = Counter(x["kind"] for x in rows)
        uniq_rules = {x["rule_id"] for x in rows if x["kind"] == "rule_id"}
        summary[stem] = {
            "file": meta["file"],
            "sha256": meta["sha256"],
            "bytes": meta["bytes"],
            "pages": meta["pages_pypdf"],
            "expected_pages": EXPECTED_PAGES[stem],
            "low_text_pages": [p["page"] for p in pg if p["flags"]["low_text_page"]],
            "empty_pages": [p["page"] for p in pg if p["chars"] == 0],
            "image_pages": [p["page"] for p in pg if p["flags"]["has_images"]],
            "box_drawing_pages": [p["page"] for p in pg if p["flags"]["has_box_drawing"]],
            "unmapped_glyph_pages": [p["page"] for p in pg if p["flags"]["has_unmapped_glyphs"]],
            "arabic_pages": [p["page"] for p in pg if p["flags"]["has_arabic_script"]],
            "table_like_pages": [p["page"] for p in pg if p["flags"]["contains_table_like_rows"]],
            "needs_visual_review_pages": [
                p["page"] for p in pg if p["flags"]["needs_visual_review"]
            ],
            "pua_mapped": sum(p["pua_mapped"] for p in pg),
            "nul_glyphs": sum(p["nul_glyphs"] for p in pg),
            "ligatures": sum(p["ligatures"] for p in pg),
            "unknown_pua": meta["unknown_pua"],
            "chars": sum(p["chars"] for p in pg),
            "rule_mentions": len(rows),
            "rule_ids_unique": len(uniq_rules),
            "distinct_codes_unique": len({x["rule_id"] for x in rows if x["kind"] != "section"}),
            "mentions_by_kind": dict(sorted(by_kind.items())),
            "families": dict(sorted(Counter(x["family"] for x in rows).items())),
            "warnings": len(meta["warnings"]),
        }
    fields = [
        "pdf",
        "page",
        "section_path",
        "family",
        "kind",
        "rule_id",
        "rule_id_hyphenated",
        "rule_id_as_printed",
        "definition_like",
        "range_expansion",
        "text200",
        "line",
    ]
    with (index_dir / "spec-rule-index.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(all_rows)
    (index_dir / "spec-rule-index.json").write_text(
        json.dumps(all_rows, ensure_ascii=False, indent=0) + "\n", encoding="utf-8", newline="\n"
    )
    (out_dir / "extraction-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return summary


def run(
    pdf_dir: Path, out_dir: Path, only: list[str] | None, rules_only: bool, index_dir: Path
) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    index_dir.mkdir(parents=True, exist_ok=True)
    stems = [s for s in SPEC_FILES if not only or s in only]
    if not rules_only:
        jobs = []
        for stem in stems:
            p = pdf_dir / SPEC_FILES[stem]
            if not p.exists():
                print(f"MISSING: {p}", file=sys.stderr)
                return 2
            jobs.append((stem, str(p), str(out_dir)))
        with ProcessPoolExecutor(max_workers=min(4, len(jobs))) as ex:
            list(ex.map(extract_pdf, jobs))
    summary = build_index(out_dir, stems, index_dir)
    print_summary(summary)
    return 0


def print_summary(summary: dict[str, Any]) -> None:
    print(
        f"{'pdf':40} {'pages':>5} {'low':>4} {'img':>4} {'box':>4} {'nul':>5} {'pua':>6} {'ids':>5} {'mentions':>8}"
    )
    for stem, s in summary.items():
        print(
            f"{stem:40} {s['pages']:>5} {len(s['low_text_pages']):>4} {len(s['image_pages']):>4} "
            f"{len(s['box_drawing_pages']):>4} {s['nul_glyphs']:>5} {s['pua_mapped']:>6} {s['rule_ids_unique']:>5} "
            f"{s['rule_mentions']:>8}"
        )
        if s["unknown_pua"]:
            print(f"   WARNING unknown private-use glyphs: {s['unknown_pua']}")


def verify(out_dir: Path, index_dir: Path) -> int:
    """Re-check the written files: markers vs page counts vs baseline, no private-use residue, id counts."""
    summary = json.loads((out_dir / "extraction-summary.json").read_text(encoding="utf-8"))
    bad = 0
    for stem, s in summary.items():
        text = (out_dir / f"{stem}.txt").read_text(encoding="utf-8")
        raw = (out_dir / f"{stem}.raw.txt").read_text(encoding="utf-8")
        markers = [int(m.group(1)) for line in text.split("\n") if (m := MARK_RE.match(line))]
        rmarkers = [int(m.group(1)) for line in raw.split("\n") if (m := MARK_RE.match(line))]
        total_ok = all(
            (m := MARK_RE.match(line)) is None or int(m.group(2)) == s["pages"]
            for line in text.split("\n")
        )
        problems = []
        if markers != list(range(1, s["pages"] + 1)):
            problems.append("page markers not 1..N in order")
        if rmarkers != markers:
            problems.append("raw and normalised markers differ")
        if s["pages"] != EXPECTED_PAGES[stem]:
            problems.append(f"page count {s['pages']} != baseline {EXPECTED_PAGES[stem]}")
        if not total_ok:
            problems.append("a marker states a different total")
        if PUA_RE.search(text):
            problems.append("private-use glyph residue in normalised text")
        rows = scan_rules(stem, text)
        if len(rows) != s["rule_mentions"]:
            problems.append(f"rule mentions {len(rows)} != recorded {s['rule_mentions']}")
        if len({r["rule_id"] for r in rows if r["kind"] == "rule_id"}) != s["rule_ids_unique"]:
            problems.append("unique rule id count differs from recorded")
        pj = json.loads((out_dir / f"{stem}.pages.json").read_text(encoding="utf-8"))
        if len(pj["pages"]) != s["pages"]:
            problems.append("pages.json length differs")
        print(f"{stem:40} {'OK' if not problems else 'FAIL'} {'; '.join(problems)}")
        bad += bool(problems)
    csv_rows = list(
        csv.DictReader((index_dir / "spec-rule-index.csv").open(encoding="utf-8", newline=""))
    )
    per_pdf = Counter(r["pdf"] for r in csv_rows)
    for stem, s in summary.items():
        if per_pdf.get(stem, 0) != s["rule_mentions"]:
            print(
                f"{stem:40} FAIL csv has {per_pdf.get(stem, 0)} rows, summary {s['rule_mentions']}"
            )
            bad += 1
    print(
        f"csv rows: {len(csv_rows)}; json rows: {len(json.loads((index_dir / 'spec-rule-index.json').read_text(encoding='utf-8')))}"
    )
    return 1 if bad else 0


def _squash(s: str) -> str:
    """Letters and digits only, upper-cased: lets an id be compared across hyphen/space/glyph differences."""
    return re.sub(
        r"[^A-Za-z0-9]", "", PUA_RE.sub(lambda m: PUA_MAP.get(ord(m.group(0)), ""), s)
    ).upper()


def verify_samples(
    pdf_dir: Path, out_dir: Path, index_dir: Path, seed: int, n_ids: int, n_tables: int, n_ex: int
) -> dict[str, Any]:
    """Independent re-check against a fresh pypdf read of the PDF (not the stored text): sampled ids, tables, examples."""
    import random

    import pypdf

    rows = json.loads((index_dir / "spec-rule-index.json").read_text(encoding="utf-8"))
    report: dict[str, Any] = {}
    for stem, fname in SPEC_FILES.items():
        rng = random.Random(f"{seed}:{stem}")
        reader = pypdf.PdfReader(str(pdf_dir / fname))
        cache: dict[int, str] = {}

        def fresh(pg: int, reader: Any = reader, cache: dict[int, str] = cache) -> str:
            if pg not in cache:
                cache[pg] = reader.pages[pg - 1].extract_text() or ""
            return cache[pg]

        ids = sorted(
            {(r["rule_id"], r["page"]) for r in rows if r["pdf"] == stem and r["kind"] == "rule_id"}
        )
        sample = rng.sample(ids, min(n_ids, len(ids)))
        miss = [(i, pg) for i, pg in sample if i.upper() not in _squash(fresh(pg))]
        meta = json.loads((out_dir / f"{stem}.pages.json").read_text(encoding="utf-8"))["pages"]
        text = (out_dir / f"{stem}.txt").read_text(encoding="utf-8")
        pages_txt = re.split(r"^=== PAGE \d+ / \d+ ===$", text, flags=re.M)[1:]
        tp = [p["page"] for p in meta if p["flags"]["contains_table_like_rows"]]
        tsample = sorted(rng.sample(tp, min(n_tables, len(tp))))
        tfail = []
        for pg in tsample:
            fn_, _ = normalise(fresh(pg))
            a = fn_.strip().split()
            b = pages_txt[pg - 1].strip().split()
            if a != b:
                tfail.append(pg)
        ex_lines = []
        for pg, body in enumerate(pages_txt, start=1):
            for ln in body.split(chr(10)):
                if re.match(
                    r"^\s*(Example|Sample reply|Sample|Worked example|Bad:|Good:|Instead:)\b", ln
                ):
                    ex_lines.append((pg, ln.strip()))
        esample = rng.sample(ex_lines, min(n_ex, len(ex_lines)))
        efail = []
        for pg, ln in esample:
            fn_, _ = normalise(fresh(pg))
            if " ".join(ln.split()) not in " ".join(fn_.split()):
                efail.append((pg, ln[:80]))
        report[stem] = {
            "pages_pypdf": len(reader.pages),
            "pages_marked": len(pages_txt),
            "ids_available": len(ids),
            "ids_sampled": len(sample),
            "ids_not_found": miss,
            "tables_available": len(tp),
            "tables_sampled": tsample,
            "tables_mismatch": tfail,
            "examples_available": len(ex_lines),
            "examples_sampled": [(pg, ln[:100]) for pg, ln in esample],
            "examples_mismatch": efail,
            "low_text_pages": [p["page"] for p in meta if p["flags"]["low_text_page"]],
        }
    (out_dir / "verification-sample.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )
    return report


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--pdf-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument(
        "--verify", action="store_true", help="re-check written output instead of extracting"
    )
    ap.add_argument(
        "--index-dir", type=Path, help="where spec-rule-index.csv/.json go (default: --out)"
    )
    ap.add_argument(
        "--verify-samples",
        action="store_true",
        help="fresh-read sample check of ids, tables, examples (needs --pdf-dir)",
    )
    ap.add_argument("--seed", type=int, default=20261031)
    ap.add_argument(
        "--rules-only",
        action="store_true",
        help="rebuild the rule index from the text already written",
    )
    ap.add_argument("--only", nargs="*", help="limit to these stems")
    a = ap.parse_args()
    if a.verify_samples:
        rep = verify_samples(a.pdf_dir, a.out, a.index_dir or a.out, a.seed, 50, 20, 10)
        for stem, r in rep.items():
            print(
                f"{stem:40} ids {r['ids_sampled'] - len(r['ids_not_found'])}/{r['ids_sampled']} "
                f"tables {len(r['tables_sampled']) - len(r['tables_mismatch'])}/{len(r['tables_sampled'])} "
                f"examples {len(r['examples_sampled']) - len(r['examples_mismatch'])}/{len(r['examples_sampled'])}"
            )
        return 0
    if a.verify:
        return verify(a.out, a.index_dir or a.out)
    return run(a.pdf_dir, a.out, a.only, a.rules_only, a.index_dir or a.out)


if __name__ == "__main__":
    sys.exit(main())
