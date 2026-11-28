"""A memory harness for pi: does the block a model receives hold what the question needs?

Modelled on the five abilities of LongMemEval (ICLR 2025): finding one buried fact, joining facts
from different sessions, knowing when something was said, preferring the newer value, and not
treating a guess as something the person said. It is deterministic and uses no model and no
database: it builds the same `context["memory"]` the chat turn builds, with a long history around
the fact, and asks `shared_memory.from_context` for the block under the 1,800-character cap.

Run it for a table:  python tests/unit/pi_memory_bench.py   (from apps/api)
`test_pi_memory_bench.py` fails the build when a case regresses.
"""

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.modules.pi import shared_memory  # noqa: E402

TOPICS = (
    "the delivery van broke down again on monday",
    "customers keep asking about the winter sale",
    "our accountant sends the sheet at month end",
    "the printer in the back office jams a lot",
    "two staff members were absent last week",
    "we want a better sign outside the shop",
    "the website photos look old and blurry",
    "a cousin helps with the packing on weekends",
    "tea and biscuits are given to every guest",
    "the generator runs when the power goes",
    "raw cloth arrives from the mill in bales",
    "returns are mostly for the wrong size",
)


def noise(count: int = 60) -> list[dict[str, Any]]:
    """A long history of unrelated owner messages, each a little different and dated."""
    out = []
    for i in range(count):
        out.append(
            {
                "source": "messages",
                "kind": "message",
                "status": "owner_said",
                "text": f"{TOPICS[i % len(TOPICS)]} (note {i})",
                "at": f"2025-{1 + i % 12:02d}-{1 + i % 27:02d}",
            }
        )
    return out


def message(text: str, at: str) -> dict[str, Any]:
    return {"source": "messages", "kind": "message", "status": "owner_said", "text": text, "at": at}


def fact(key: str, value: str, status: str = "owner_said") -> dict[str, Any]:
    return {"source": "facts", "kind": key, "status": status, "text": f"{key}: {value}"}


@dataclass
class Case:
    ability: str
    name: str
    query: str
    records: list[dict[str, Any]]
    check: Callable[[dict[str, Any]], bool]
    note: str = ""
    cap: int = shared_memory.CAP_CHARS
    extra: dict[str, Any] = field(default_factory=dict)


def texts(block: dict[str, Any]) -> list[str]:
    return [str(r["text"]) for r in block.get("records") or []]


def position(block: dict[str, Any], needle: str) -> int:
    """Where the first record holding `needle` sits in the block (a large number when absent)."""
    for i, text in enumerate(texts(block)):
        if needle in text:
            return i
    return 10_000


CASES = [
    Case(
        "extraction",
        "a fact said once, long ago, among many messages",
        "which day do we close the shop",
        [*noise(), message("we close the shop every friday for the weekly market", "2025-03-04")],
        lambda b: position(b, "friday") < 3,
    ),
    Case(
        "extraction",
        "the same fact asked in other words (plural, tense)",
        "when do the customers come for the orders",
        [*noise(), message("the customer collects the order on thursday evening", "2025-02-11")],
        lambda b: position(b, "thursday") < 3,
    ),
    Case(
        "multi-session",
        "two facts from two different months answer one question",
        "when does my faisalabad supplier deliver",
        [
            *noise(),
            message("our best supplier is in faisalabad", "2025-01-10"),
            message("the supplier delivers every tuesday morning", "2025-02-02"),
        ],
        lambda b: position(b, "faisalabad") < 4 and position(b, "tuesday") < 4,
    ),
    Case(
        "temporal",
        "two values for the same thing: the newer is read first and dated",
        "what is my monthly rent",
        [
            message("monthly rent is 90000", "2025-01-05"),
            *noise(),
            message("monthly rent is 110000", "2025-09-01"),
        ],
        lambda b: (
            position(b, "110000") < position(b, "90000")
            and any(r.get("when") == "2025-09-01" for r in b["records"])
        ),
    ),
    Case(
        "knowledge-update",
        "a stated value outranks a pi guess about the same thing",
        "what is my budget",
        [
            *noise(),
            fact("budget", "about 5 lakh", status="pi_inferred"),
            fact("budget", "8 lakh rupees", status="owner_said"),
        ],
        lambda b: position(b, "8 lakh") < position(b, "5 lakh"),
    ),
    Case(
        "knowledge-update",
        "a correction is kept with what it replaced",
        "how many staff do we have",
        [
            *noise(),
            {
                "source": "corrections",
                "kind": "correction",
                "status": "confirmed",
                "text": "problem P1 staff: 12 (before: 9)",
            },
        ],
        lambda b: position(b, "staff: 12") < 3,
    ),
    Case(
        "guess-vs-said",
        "a pi guess stays labelled as a guess and is never ahead of what was said",
        "what tools do we use for billing",
        [
            *noise(),
            fact("tools", "probably a spreadsheet", status="pi_inferred"),
            fact("tools", "we use a paper register", status="owner_said"),
        ],
        lambda b: (
            position(b, "paper register") < position(b, "spreadsheet")
            and all(
                r["status"] == "pi_inferred"
                for r in b["records"]
                if "spreadsheet" in str(r["text"])
            )
        ),
    ),
    Case(
        "dedupe",
        "the same message said five times takes one place",
        "tell me about the loom",
        [
            *[
                message("the old loom in the workshop needs a new motor", f"2025-0{d}-01")
                for d in range(1, 6)
            ],
            *noise(20),
        ],
        lambda b: sum("loom" in t for t in texts(b)) == 1,
    ),
    Case(
        "no-question",
        "with no message the old order is kept (nothing is reordered by guesswork)",
        "",
        [fact("business", "cloth shop"), *noise(10)],
        lambda b: position(b, "cloth shop") == 0,
    ),
]


def block_for(case: Case, ranked: bool) -> dict[str, Any]:
    context = {"memory": {"known": case.records}}
    return shared_memory.from_context(context, cap=case.cap, query=case.query if ranked else "")


def run() -> list[tuple[Case, bool, bool, int]]:
    """(case, passes with ranking, passes in the old fixed order, characters used)."""
    rows = []
    for case in CASES:
        ranked = block_for(case, True)
        plain = block_for(case, False)
        rows.append(
            (
                case,
                bool(ranked) and case.check(ranked),
                bool(plain) and case.check(plain),
                len(json.dumps(ranked, ensure_ascii=False)),
            )
        )
    return rows


if __name__ == "__main__":
    rows = run()
    for case, new, old, size in rows:
        print(
            f"{'PASS' if new else 'FAIL'}  old={'pass' if old else 'FAIL'}  "
            f"{size:>4} chars  [{case.ability}] {case.name}"
        )
    ranked_ok = sum(r[1] for r in rows)
    old_ok = sum(r[2] for r in rows)
    print(f"\nranked: {ranked_ok}/{len(rows)}   old order: {old_ok}/{len(rows)}")
