# ruff: noqa: E501
"""Write docs/pi-saas/SPEC-INDEX-v2.md and spec-extraction-verification.md from extract_specs.py output.

Pure tooling (no network, deterministic). Run after extract_specs.py (and its --verify-samples):

    python -I -X utf8 apps/api/scripts/build_spec_index_v2.py --text-dir docs/pi-saas/spec-text-v2 \
        --docs-dir docs/pi-saas [--old-dir docs/pi-saas/spec-text]

It also writes spec-precedence-statements.csv (every line that states which text wins or supersedes).
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("extract_specs", HERE / "extract_specs.py")
assert _spec and _spec.loader
ES = importlib.util.module_from_spec(_spec)
sys.modules["extract_specs"] = ES
_spec.loader.exec_module(ES)

MARK = re.compile(r"^=== PAGE (\d+) / (\d+) ===$")
FOOT = re.compile(r"\bpage \d+ of \d+\s*$", re.I)
PREC = re.compile(
    r"\b(wins|win when|supersed\w*|overrid\w*|overrul\w*|takes? precedence|governing text|governs|"
    r"source of truth|outranks?|replaces?)\b",
    re.I,
)


def read_pages(path: Path) -> list[list[str]]:
    pages: list[list[str]] = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        if MARK.match(line):
            pages.append([])
        elif pages:
            pages[-1].append(line)
    return pages


def line_page(path: Path, wanted: set[int]) -> dict[int, int]:
    out: dict[int, int] = {}
    page = 0
    for i, line in enumerate(path.read_text(encoding="utf-8").split("\n"), start=1):
        m = MARK.match(line)
        if m:
            page = int(m.group(1))
        if i in wanted:
            out[i] = page
    return out


def ranges(nums: list[int]) -> str:
    if not nums:
        return "none"
    out: list[str] = []
    s = p = nums[0]
    for n in nums[1:] + [None]:  # type: ignore[list-item]
        if n is not None and n == p + 1:
            p = n
            continue
        out.append(str(s) if s == p else f"{s}-{p}")
        if n is not None:
            s = p = n
    return ", ".join(out)


def version_line(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").split("\n")[:12]:
        if line.startswith("Version "):
            return line.strip()
    return "not found on page 1"


def quote_table(path: Path, start_line: int) -> tuple[int, int, str]:
    lines = path.read_text(encoding="utf-8").split("\n")
    end = start_line
    while end < len(lines) and not FOOT.search(lines[end - 1]):
        end += 1
    return start_line, end, "\n".join(lines[start_line - 1 : end])


def old_defects(old_dir: Path, new_dir: Path) -> list[str]:
    rows = []
    for stem in ES.SPEC_FILES:
        old = old_dir / f"{stem}.txt"
        if not old.exists():
            continue
        o = old.read_text(encoding="utf-8")
        n = (new_dir / f"{stem}.txt").read_text(encoding="utf-8")
        pua = re.findall("[-]", o)
        pat = r"R-?(?:LANG|OFFER|SELL|VAL|ANS)-?\d"
        rows.append(
            f"| {stem} | {len(pua)} / {len(set(pua))} | {len(re.findall('R[' + chr(0xE000) + '-' + chr(0xF8FF) + '][A-Z]', o))} | "
            f"{len(re.findall(pat, o))} -> {len(re.findall(pat, n))} | {o.count(chr(0x2EE))} / {o.count(chr(0x2BC))} | "
            f"{len(re.findall('[' + chr(0xFB50) + '-' + chr(0xFDFF) + chr(0xFE70) + '-' + chr(0xFEFF) + ']', o))} |"
        )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text-dir", required=True, type=Path)
    ap.add_argument("--docs-dir", required=True, type=Path)
    ap.add_argument("--old-dir", type=Path)
    a = ap.parse_args()
    td, dd = a.text_dir, a.docs_dir
    summary: dict[str, Any] = json.loads(
        (td / "extraction-summary.json").read_text(encoding="utf-8")
    )
    samples: dict[str, Any] = json.loads(
        (td / "verification-sample.json").read_text(encoding="utf-8")
    )
    rows = json.loads((dd / "spec-rule-index.json").read_text(encoding="utf-8"))
    pagemeta = {
        s: json.loads((td / f"{s}.pages.json").read_text(encoding="utf-8")) for s in summary
    }

    # ---- precedence statements csv
    prec_rows: list[dict[str, Any]] = []
    for stem in summary:
        page = 0
        for i, line in enumerate(
            (td / f"{stem}.txt").read_text(encoding="utf-8").split("\n"), start=1
        ):
            m = MARK.match(line)
            if m:
                page = int(m.group(1))
            elif PREC.search(line) and 8 < len(line.strip()) < 400:
                prec_rows.append({"pdf": stem, "page": page, "line": i, "text": line.strip()})
    with (dd / "spec-precedence-statements.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["pdf", "page", "line", "text"], lineterminator="\n")
        w.writeheader()
        w.writerows(prec_rows)

    # ---- SPEC-INDEX-v2.md
    L: list[str] = []
    L.append(
        "# Specification index v2 (page-marked, glyph-normalised extraction of the seven PDFs)\n"
    )
    L.append(
        "Generated by `apps/api/scripts/extract_specs.py` and `build_spec_index_v2.py`. Replaces nothing: the older "
        "`SPEC-INDEX.md` and `spec-text/` stay as they were. The PDFs remain the version of record (outside git).\n"
    )
    L.append(
        "**What pypdf text does not capture.** Diagrams, drawn boxes and arrows, images, colour and layout, and the "
        "column structure of tables (cells come out in reading order, so a three-column table reads as interleaved "
        "lines). Urdu / Roman-Urdu Arabic-script text is extracted in presentation-form order with some glyphs "
        "missing. Every page where this matters is listed below as needing a human look at the PDF. Nothing here "
        "claims those pages are fully captured.\n"
    )
    L.append("## 1. The seven PDFs\n")
    L.append(
        "| Stem | PDF file | SHA-256 | Bytes | Pages (pypdf = markers = baseline) | Version / date (page 1) |"
    )
    L.append("|---|---|---|---|---|---|")
    for stem, s in summary.items():
        ok = "yes" if s["pages"] == s["expected_pages"] else "NO"
        L.append(
            f"| {stem} | `{s['file']}` | `{s['sha256']}` | {s['bytes']:,} | {s['pages']} (match: {ok}) | {version_line(td / (stem + '.txt'))} |"
        )
    L.append(
        "\nOutput per PDF in `docs/pi-saas/spec-text-v2/`: `<stem>.txt` (normalised, `=== PAGE n / N ===` markers, "
        "1-based as in a PDF viewer), `<stem>.raw.txt` (unmodified pypdf text, same markers), `<stem>.pages.json` "
        "(per page: chars, first heading, flags, warnings), plus `extraction-summary.json`, "
        "`verification-sample.json`. The rule index is `docs/pi-saas/spec-rule-index.csv` / `.json`; every "
        "precedence-style sentence is in `spec-precedence-statements.csv`.\n"
    )
    L.append("## 2. Precedence (what the specs' own tables say)\n")
    L.append(
        "The authoritative statements are the specs' own. Quoted text below is copied from the normalised extraction "
        "(page and line are of `spec-text-v2/<stem>.txt`); the table cells are interleaved because pypdf reads in "
        "reading order: each row is `Topic`, `Older text`, `Governing text`.\n"
    )
    tables = [
        ("pi-platform-spec", 121),
        ("pi-platform-spec-1", 143),
        ("pi-platform-spec-v1.4-2026-10-27", 496),
        ("pi-platform-spec-v1.5-2026-10-28", 525),
        ("pi-platform-spec-v1.6-2026-10-30", 565),
    ]
    lp = {s: line_page(td / f"{s}.txt", {ln}) for s, ln in tables}
    for stem, ln in tables:
        a0, b0, q = quote_table(td / f"{stem}.txt", ln)
        L.append(
            f'### {stem}: "Which rule wins when books disagree", page {lp[stem][ln]}, lines {a0}-{b0}\n'
        )
        L.append("```text\n" + q + "\n```\n")
    L.append("### Other precedence statements found\n")
    L.append(
        "- Contents entry for the same section: line 11-13 of each platform-spec text (contents page 2)."
    )
    L.append(
        "- `pi-platform-spec-v1.6` page 19, line 851 onward (Part A.5 Conflict Register, resolution principles): "
        '"2. The constitution wins, then Solution Mode and the value line, then voice, then industry packs, then '
        'learned examples. A learned example never outranks a rule." (the same principle sits in each older platform spec.)'
    )
    L.append(
        '- `pi-brain-v3` page 441, line 39747 (CLAUDE.md text inside the spec): "If code and the document disagree, '
        'the document wins. Ask before deviating." Same sentence on `pi-platform-spec*` (v1.6 page 90, line 4166).'
    )
    L.append(
        '- `pi-industry-solutions` page 8, line 288: "This is the second addendum to pi — The Brain v3. It sits on top of '
        'Addendum 1 (Solution Mode). Where they disagree, this one wins." (v1.6 page 126, line 5827 repeats it for Addendum 2.)'
    )
    L.append(
        f"- All {len(prec_rows)} lines that contain wins / supersedes / overrides / takes precedence / source of truth / "
        "replaces are in `spec-precedence-statements.csv` (pdf, page, line, text). Read them before building "
        "the traceability matrix; they include in-book overrides that are not in the main table.\n"
    )
    L.append("### Precedence position (derived, not a spec statement)\n")
    L.append(
        "1. Within the platform-spec files, the table above decides topic by topic, and the newest file adds rows "
        "(v1.6 over v1.5 over v1.4 over platform-spec-1 over platform-spec). Compare the quoted tables: rows "
        "present only in later files are the later amendments."
    )
    L.append(
        "2. Where a topic has no row, the later book / later file wins (platform-spec Books 2 to 5 over Brain v3 "
        "and Addenda 1 and 2) except the Constitution (Part 1, L0), which the table says always wins over everything above it."
    )
    L.append(
        "3. Code versus document: the document wins; ask before deviating (CLAUDE.md of the repository says the same).\n"
    )
    L.append("## 3. Extraction statistics\n")
    L.append(
        "| Stem | Pages | Chars | Private-use glyphs mapped | Glyphs with no Unicode (U+FFFD) | Unmapped private-use | Rule ids (unique) | Mentions (all kinds) |"
    )
    L.append("|---|---|---|---|---|---|---|---|")
    for stem, s in summary.items():
        L.append(
            f"| {stem} | {s['pages']} | {s['chars']:,} | {s['pua_mapped']:,} | {s['nul_glyphs']} | "
            f"{sum(s['unknown_pua'].values())} | {s['rule_ids_unique']} | {s['rule_mentions']} |"
        )
    L.append("\n### Rule-id pattern families (mentions) per PDF\n")
    fams = sorted({f for s in summary.values() for f in s["families"]})
    L.append("| Family | kind | " + " | ".join(summary) + " |")
    L.append("|---|---|" + "---|" * len(summary))
    kind_of = {f: k for f, k, _ in ES.FAMILIES}
    kind_of["SECTION"] = "section"
    for f in fams:
        L.append(
            f"| {f} | {kind_of.get(f, '')} | "
            + " | ".join(str(s["families"].get(f, 0)) for s in summary.values())
            + " |"
        )
    L.append(
        "\n`R-WORD-NN` = `R-OFFER-03`/`ROFFER03` (also expanded ranges such as `R-SELL-01..05`); `R-WORD` = a family cited "
        "without a number (`R-ANS`); `A#-n` = audit-table items (`A6-12`); `PREFIX-n` = every other letters-then-digits "
        "code (`G1..G56`, `R1..R4`, `B1..B7`, `S0..S22`, `X1..`, `L0..L2`, `OG1`, `OF1`, `IL1`, `AA1`, `EO1`, `MD1`, "
        "`BS1`, `DQ1`, `ST1`, `SL-1`, `RT1`, `M1`, `P1`, ...); `WORD-NN` = a hyphenated word-number without the R; "
        "`SECTION` = Book / Part / Addendum / numbered section headings. `PREFIX-n` includes labels that are not "
        "rules (layer names L0-L2, table row numbers): filter by `kind` and by `definition_like` when building the matrix.\n"
    )
    L.append(
        "### Pattern-family counts: prefix breakdown for `PREFIX-n` (unique codes, all PDFs)\n"
    )
    pref = Counter()
    seen: set[tuple[str, str]] = set()
    for r in rows:
        if r["family"] == "PREFIX-n":
            m = re.match(r"[A-Z]+", r["rule_id"])
            key = (m.group(0) if m else "?", r["rule_id"])
            if key not in seen:
                seen.add(key)
                pref[key[0]] += 1
    L.append(
        ", ".join(f"{p} {n}" for p, n in sorted(pref.items(), key=lambda x: (-x[1], x[0]))) + "\n"
    )
    L.append("## 4. Glyph normalisation (the known defect and what else was found)\n")
    L.append(
        "The platform specs and the Industry Solutions addendum were typeset in Inter with OpenType alternates; the PDF "
        "producer gave those alternates private-use code points. `R-OFFER-03` therefore came out of pypdf as "
        "`R<U+E088>OFFER<U+E088>03`. The mapping was proved from the Type3 glyph outlines (each private-use glyph "
        "rendered and read, allocation identical in all six PDFs that contain them; Brain v3 has none):\n"
    )
    L.append("| Code point | Becomes | Meaning |\n|---|---|---|")
    names = {
        0xE088: "raised hyphen in rule ids",
        0xE089: "en dash (ranges)",
        0xE08B: "em dash",
        0xE08C: "bullet",
        0xE092: "colon",
        0xE094: "full stop after list numbers",
        0xE097: "less-than",
        0xE098: "greater-than",
        0xE099: "less-or-equal",
        0xE09A: "greater-or-equal",
        0xE09B: "equals",
        0xE09D: "plus",
        0xE09E: "minus",
        0xE09F: "multiplication",
        0xE0A1: "plus-minus",
        0xE0A3: "tilde (approximately)",
        0xE1D7: "arrow",
    }
    for cp, ch in ES.PUA_MAP.items():
        if 0xE071 <= cp <= 0xE07A:
            continue
        L.append(f"| U+{cp:04X} | `{ch}` | {names.get(cp, 'bracket form')} |")
    L.append("| U+E071 .. U+E07A | `0` .. `9` | tabular digits (numbered lists) |")
    L.append(
        "\nAlso normalised: U+02EE becomes a closing double quote and U+02BC a right single quote (the font maps both "
        "as modifier letters); NBSP and TAB become a space; soft hyphens are removed; fi/fl ligatures and Arabic "
        "presentation forms go through NFKC (letters only, order untouched). NUL glyphs (no Unicode value, nearly "
        "all Arabic/Urdu marks) become U+FFFD and are counted, never deleted. Any unknown private-use glyph would "
        "become `<<U+XXXX>>` and a warning: the run produced none.\n"
    )
    if a.old_dir and a.old_dir.exists():
        L.append("## 5. Defects found in the existing extraction (`spec-text/`)\n")
        L.append(
            "| Stem | Private-use glyphs (total / distinct) | `R<glyph>WORD` ids damaged | Matches of R-LANG/OFFER/SELL/VAL/ANS ids: old -> new | U+02EE / U+02BC | Arabic presentation forms |"
        )
        L.append("|---|---|---|---|---|---|")
        L.extend(old_defects(a.old_dir, td))
        L.append(
            "\nOther defects of the old files: (a) page markers are `=== page N ===` with no total, so a truncated file "
            "cannot be detected; (b) NUL bytes were silently deleted (the counts in the old SPEC-INDEX.md), erasing "
            "Urdu marks without a trace; (c) the old index tells readers to search for words not punctuation, because `ˮ` and `ʼ` replace "
            "every closing quote and apostrophe; (d) numbered-list digits, brackets, colons, dashes, comparison operators "
            "and arrows inside the six Inter-set PDFs are private-use glyphs, so `>= 3`, `1-3`, `(step 7)` and "
            "`[B, D]` do not search; (e) no per-page flags, so no list of pages needing visual review; "
            "(f) the old Brain v3 text has TAB characters between words (32,929 lines contain one). Brain v3 also has a few "
            "words split by a stray space inside the PDF itself (for example `I f`), which remain.\n"
        )
    L.append("## 6. Pages that need a human look at the PDF (pypdf cannot see them)\n")
    L.append(
        "Reasons: **low text** (under 200 characters: cover, divider, blank or image-only page); **box drawing** (a "
        "diagram or flow drawn with box characters: text is captured but the layout and arrows are not); **glyphs without "
        "Unicode** (Urdu / Arabic marks missing); **Arabic script** (order and shaping unreliable). No page contains a "
        "raster image or inline image (the image detector returned zero for every page of all seven PDFs, "
        "so there are no scanned pages); vector diagrams and drawn tables are not detectable from text and "
        "are covered only by the table-like flag in the pages.json files.\n"
    )
    for stem, s in summary.items():
        pm = {p["page"]: p for p in pagemeta[stem]["pages"]}
        L.append(f"### {stem}\n")
        L.append(
            f"- Low text pages: {ranges(s['low_text_pages'])}; empty pages: {ranges(s['empty_pages'])}"
        )
        L.append(f"- Box-drawing pages: {ranges(s['box_drawing_pages'])}")
        L.append(f"- Pages with glyphs lacking Unicode: {ranges(s['unmapped_glyph_pages'])}")
        L.append(f"- Pages with Arabic-script text: {ranges(s['arabic_pages'])}")
        L.append(
            f"- Table-like pages (heuristic: 20 or more drawn rectangles, or tab/pipe/box rows): {len(s['table_like_pages'])} of {s['pages']}; list in `{stem}.pages.json`"
        )
        L.append("")
        L.append("| Page | Reasons | First heading |\n|---|---|---|")
        for pg in sorted(set(s["needs_visual_review_pages"]) | set(s["arabic_pages"])):
            f = pm[pg]["flags"]
            why = [
                n
                for n, k in (
                    ("low text", "low_text_page"),
                    ("box drawing", "has_box_drawing"),
                    ("glyphs without Unicode", "has_unmapped_glyphs"),
                    ("Arabic script", "has_arabic_script"),
                    ("image", "has_images"),
                )
                if f[k]
            ]
            L.append(
                f"| {pg} | {', '.join(why)} | {pm[pg]['first_heading'].replace('|', '/')[:70]} |"
            )
        L.append("")
    (dd / "SPEC-INDEX-v2.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")

    # ---- verification report
    V: list[str] = []
    V.append("# Spec extraction verification\n")
    V.append(
        "Independent-style check: every figure below comes from a **fresh pypdf read of the PDF**, not from the stored "
        "text, using seed `20261031` (`extract_specs.py --verify-samples`, results in "
        "`spec-text-v2/verification-sample.json`). It proves the text layer was captured faithfully. It does not "
        "prove that the text layer itself is right, and it cannot see anything pypdf cannot read.\n"
    )
    V.append("## 1. Page counts\n")
    V.append(
        "| PDF | pypdf pages | markers in .txt | baseline (coordinator) | match | pages with empty/low text | empty |"
    )
    V.append("|---|---|---|---|---|---|---|")
    for stem, s in summary.items():
        r = samples[stem]
        ok = "yes" if s["pages"] == r["pages_marked"] == s["expected_pages"] else "NO"
        V.append(
            f"| {stem} | {r['pages_pypdf']} | {r['pages_marked']} | {s['expected_pages']} | {ok} | "
            f"{len(s['low_text_pages'])} ({ranges(s['low_text_pages'])}) | {ranges(s['empty_pages'])} |"
        )
    V.append(
        "\n`extract_specs.py --verify` also re-checks that markers run 1..N in order with the right total, that raw and "
        "normalised markers agree, that no private-use glyph remains, and that CSV/JSON/summary rule counts agree.\n"
    )
    V.append("## 2. Rule ids re-found on their recorded page (50 per PDF, fixed seed)\n")
    V.append(
        "A sampled id (kind `rule_id`) counts as found when its letters and digits (hyphens and spacing ignored) occur in "
        "a fresh read of its recorded page. `pi-industry-solutions` has only 24 id-and-page pairs, so all of them were checked.\n"
    )
    V.append(
        "| PDF | id-and-page pairs available | sampled | found | not found |\n|---|---|---|---|---|"
    )
    for stem, r in samples.items():
        V.append(
            f"| {stem} | {r['ids_available']} | {r['ids_sampled']} | {r['ids_sampled'] - len(r['ids_not_found'])} | "
            f"{len(r['ids_not_found'])} {r['ids_not_found'] if r['ids_not_found'] else ''} |"
        )
    V.append("\n## 3. Table-like regions (20 pages per PDF)\n")
    V.append(
        "Pages flagged table-like (20 or more drawn rectangles, or tab/pipe/box rows) were drawn at random and compared "
        "word-for-word (whitespace-insensitive) between a fresh extraction-plus-normalisation and the stored page. This "
        "proves the stored text matches the PDF text layer; it does **not** prove the table's column structure, which "
        "pypdf flattens to reading order. Column reading was done only by eye on the quoted precedence tables in "
        "SPEC-INDEX-v2.md.\n"
    )
    V.append(
        "| PDF | table-like pages | sampled | identical | mismatching |\n|---|---|---|---|---|"
    )
    for stem, r in samples.items():
        V.append(
            f"| {stem} | {r['tables_available']} | {len(r['tables_sampled'])} | "
            f"{len(r['tables_sampled']) - len(r['tables_mismatch'])} | {r['tables_mismatch'] or 0} |"
        )
    V.append("\nSampled pages:\n")
    for stem, r in samples.items():
        V.append(f"- {stem}: {ranges(r['tables_sampled'])}")
    V.append("\n## 4. Examples (up to 10 per PDF)\n")
    V.append(
        "Example lines are lines that start with Example, Sample reply, Sample, Worked example, Bad:, Good: or Instead: . "
        "Each sampled line was searched for in a fresh read of its page. Examples that are not introduced by those words "
        "(for instance chat transcripts) are not sampled.\n"
    )
    V.append(
        "| PDF | example lines found | sampled | found on page | mismatching |\n|---|---|---|---|---|"
    )
    for stem, r in samples.items():
        V.append(
            f"| {stem} | {r['examples_available']} | {len(r['examples_sampled'])} | "
            f"{len(r['examples_sampled']) - len(r['examples_mismatch'])} | {r['examples_mismatch'] or 0} |"
        )
    V.append("\nSampled lines:\n")
    for stem, r in samples.items():
        V.append(f"**{stem}**\n")
        for pg, ln in r["examples_sampled"]:
            V.append(f"- p{pg}: {ln}")
        V.append("")
    V.append("## 5. Sampled rule ids (for reproducibility)\n")
    import random

    for stem in summary:
        rng = random.Random(f"20261031:{stem}")
        ids = sorted(
            {(r["rule_id"], r["page"]) for r in rows if r["pdf"] == stem and r["kind"] == "rule_id"}
        )
        pick = sorted(rng.sample(ids, min(50, len(ids))), key=lambda x: (x[1], x[0]))
        V.append(f"- **{stem}**: " + ", ".join(f"{i}@{p}" for i, p in pick))
    V.append("\n## 6. What could NOT be verified\n")
    V.append(
        "- **Diagrams, drawn boxes, arrows, images, colour, layout.** pypdf has no access to them. Pages with box characters "
        "(a diagram drawn as text) are listed in SPEC-INDEX-v2.md section 6; other vector drawings leave no trace at all."
    )
    V.append(
        "- **Table column structure.** Cells are in reading order; the mapping of cells to columns was not machine-checked."
    )
    V.append(
        "- **Arabic / Urdu script.** Presentation-form letters are normalised to base letters but the order and some "
        "marks are lost (glyphs with no Unicode value are shown as U+FFFD). The Urdu example text on the pages listed "
        "as Arabic-script must be read in the PDF."
    )
    V.append(
        "- **Private-use glyph mapping.** Proved by reading the rendered glyph outlines and by context in many places, "
        "and checked to be identical across the six PDFs that contain them; it was not compared glyph-by-glyph "
        "against a full render of every page."
    )
    V.append(
        "- **Completeness of the rule index.** The patterns find every token of the shapes listed; a rule written in a "
        "shape not listed (or an id split across lines) would be missed. The sample check shows the index has no false ids "
        "in the sample; it cannot show there are no missing ones. Counting `R-WORD-NN` across versions (the five "
        "platform specs agree to within a few ids) is a consistency signal, not a proof."
    )
    V.append(
        "- **Brain v3 and Industry Solutions word spacing.** A few words are split by a stray space inside the PDF "
        "text layer; searches should tolerate that."
    )
    V.append(
        "- **Scanned pages / OCR.** No page has an image, so OCR was not needed; `pi-industry-solutions` page 50 is a "
        "genuinely blank page (no content stream)."
    )
    (dd / "spec-extraction-verification.md").write_text(
        "\n".join(V) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        "wrote SPEC-INDEX-v2.md, spec-extraction-verification.md, spec-precedence-statements.csv;",
        len(prec_rows),
        "precedence lines",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
