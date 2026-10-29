"""Build `spec/supersession.json`: the parts of Brain v3 that the platform specification replaced.

`spec/handbook.json` was built from pi-brain-v3.pdf, so it still carries rules the platform
specification (pi-platform-spec.pdf, "Which rule wins when books disagree", page 5) says are
superseded: R-SELL-01, R-SELL-02 and R-SELL-04 ("no solution while the person is describing",
"the document comes once the problems are noted"). `spec_handbook.sections()` applies this file on
top of the handbook, so the model is given the governing text and never the old one.

The governing text is the platform specification's own words (Book 2 Part 3: R-ANS, R-SOL,
R-OFFER), cut out of the PDF; nothing is written by hand except the list of what is replaced and
the two rules the owner decided to leave out (see EXCLUDED).

Run from apps/api (needs pymupdf, which the repo's virtual environment has):
    ../../.venv/Scripts/python.exe scripts/build_spec_supersession.py "<pi-platform-spec.pdf>"
"""

import argparse
import json
import re
from pathlib import Path

import pymupdf

OUT = Path("app/modules/pi/spec/supersession.json")
HANDBOOK = Path("app/modules/pi/spec/handbook.json")

# Rules of Book 2 that are left out on purpose, by the owner's decision of 2026-10-26.
EXCLUDED = {
    "R-SOL-10": "the unprompted offer after four stuck turns: the owner chose the progress rule "
    "(9.3) only, so 'pi never pushes' stays absolute",
    "R-OFFER-07": "quote-fact questions after a yes: the owner chose to ask the scope once "
    "(R-OFFER-04) on a plain yes, and a direct request for the document is confirmed at once",
}
# Brain v3 text replaced by the platform specification (old fragment -> governing fragment).
REPLACE_0_2 = (
    "P8 pi doesn't pitch while you're describing a problem.\nWhen problems are sorted, it asks "
    "whether you'd like a solution document and a quote. You can say no.",
    "P8 pi doesn't push a pitch while you're describing a problem, but if you ask for a solution "
    "it answers (Book 2). When problems are sorted, it asks whether you'd like a solution "
    "document and a quote. You can say no.",
)
REPLACE_3_2 = (
    "Acknowledge, ask 1 question\nSuggest, sell, summarise early",
    "Acknowledge, ask 1 question (a solution request moves to S_ADVISE: answer it, Book 2 Part 9)"
    "\nSell, summarise early",
)
RULE = re.compile(r"(?m)^(R-[A-Z]+-\d+(?: \([a-z ]+\))?)\s")


def platform_text(pdf: Path) -> str:
    doc = pymupdf.open(str(pdf))
    return "\n".join(page.get_text() for page in doc)


def governing_rules(text: str) -> dict[str, str]:
    """Book 2 Part 3 (3.1 Answering, 3.2 Solutions, 3.3 The offer): rule id -> its sentence(s)."""
    start = text.index("R-ANS-01 Answer the question first")
    end = text.index("Part 4 — Solution Mode: the Solution Ladder", start)
    block = re.sub(r"=+PAGE \d+=+", "", text[start:end])
    parts = RULE.split(block)
    rules: dict[str, str] = {}
    for rule_id, body in zip(parts[1::2], parts[2::2], strict=False):
        rules[rule_id] = re.sub(r"\s+3\.\d [A-Z][A-Za-z ]+$", "", " ".join(body.split()))
    return rules


OLD_OPENING_TAIL = "Tell me what's going wrong in your business and I'll start on it."
NEW_OPENING_TAIL = "What does your business do?"


def old_section(book: list[dict[str, str]], section_id: str) -> dict[str, str]:
    return next(item for item in book if item["id"] == section_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    text = platform_text(args.pdf)
    book = json.loads(HANDBOOK.read_text(encoding="utf-8"))
    rules = governing_rules(text)
    kept = {k: v for k, v in rules.items() if k.split(" ")[0] not in EXCLUDED}
    old = old_section(book, "1.2")["text"].replace("R-SELL-05\n", "R-SELL-05 ")
    stand = [line for line in old.split("\n") if line.startswith(("R-SELL-03", "R-SELL-05"))]
    banner = (
        "R-SELL-01, R-SELL-02 and R-SELL-04 of Brain v3 are SUPERSEDED by Book 2 (R-ANS / R-SOL): "
        "if the person asks for a solution, pi answers with ideas in the first sentence. R-SELL-03 "
        "and R-SELL-05 stand."
    )
    lines = [banner, *stand]
    lines += [f"{rule_id} {body}" for rule_id, body in kept.items()]
    section = {
        "id": "1.2",
        "title": "Listening, and answering when asked (Book 2 replaces R-SELL-01, 02, 04)",
        "part": "1",
        "text": "\n".join(lines),
    }
    data = {
        "source": "pi-platform-spec.pdf: page 5 (which rule wins), page 15 (1.2 banner), Book 2 "
        "Part 3 (R-ANS, R-SOL, R-OFFER), Book 2 Part 9 (S_ADVISE)",
        "replace": [section],
        "patch": [
            {"id": "0.2", "old": REPLACE_0_2[0], "new": REPLACE_0_2[1]},
            {"id": "3.2", "old": REPLACE_3_2[0], "new": REPLACE_3_2[1]},
            # Part 14 deletes the old opening; Brain v3 still prints it as the "canonical" first
            # message in 1.1 and in the 2.3 table, and a model copies a canonical line (live
            # 2026-10-28: "Tell me what's going wrong ... I'll start on it").
            {"id": "1.1", "old": OLD_OPENING_TAIL, "new": NEW_OPENING_TAIL},
            {"id": "2.3", "old": OLD_OPENING_TAIL, "new": NEW_OPENING_TAIL},
        ],
        "remove": [],
        "open_decision": "G4 (can you make an app for this? answered with the superseded R-SELL-04 "
        "line) stays until the owner decides: Book 2 4.2 answers a capability question with yes "
        "and ideas, the platform spec still prints G4 in Part 10.1, and the code has a deliberate "
        "path for it (BUILD_REQUEST)",
        "excluded": EXCLUDED,
    }
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(kept)} rules, {len(section['text'])} characters -> {args.out}")


if __name__ == "__main__":
    main()
