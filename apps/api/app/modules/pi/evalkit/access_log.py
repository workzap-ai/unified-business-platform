"""Append-only Held-out access log (rule-only sealing, FT-A3).

Held-out cases sit in the repository, so what keeps them honest is a rule (never tune on them) and a
record of every run that reads them. `splits.held_out_access` only builds a record; this writes it,
one JSON line per read, and never rewrites or truncates the file.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def append(
    path: str | Path, who: str, why: str, run_id: str, split: str, count: int
) -> dict[str, Any]:
    if not who.strip() or not why.strip():
        raise ValueError("a Held-out read needs who and why")
    row = {
        "who": who,
        "why": why,
        "when": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_id": run_id,
        "split": split,
        "count": count,
    }
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


_MINT = object()


class Pass:
    """Proof that a Held-out read was logged. Only `grant` makes one, so a caller cannot pass a
    plain True to a function that scores Held-out cases (an accident guard, not security)."""

    def __init__(self, row: dict[str, Any], *, _mint: object = None) -> None:
        if _mint is not _MINT:
            raise TypeError("a Pass is minted by access_log.grant after the line is written")
        self.row = row


def grant(path: str | Path, who: str, why: str, run_id: str, split: str, count: int) -> Pass:
    """Write the access line, then hand back the Pass that proves it."""
    return Pass(append(path, who, why, run_id, split, count), _mint=_MINT)


def read(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line]
