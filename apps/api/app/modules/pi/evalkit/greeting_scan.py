"""Scan pi text for the old opening (spec v1.5 18.2, "Forbidden strings"). No model, no write.

`scan` counts the texts that contain it and keeps a short, cut sample of each hit. The same pattern
that blocks a live reply (`reply_gates.forbidden_opening`) is used, so the scan and the gate agree.
"""

from collections.abc import Iterable
from typing import Any

from app.modules.pi import reply_gates

SAMPLE = 80


def scan(texts: Iterable[tuple[str, str]]) -> dict[str, Any]:
    """`texts` is (where, text) pairs. Returns the counts and the hits as (where, cut text)."""
    total = 0
    hits: list[tuple[str, str]] = []
    for where, text in texts:
        total += 1
        found = reply_gates.FORBIDDEN_OPENING.search(text or "")
        if found:
            start = max(0, found.start() - 20)
            hits.append((where, (text or "")[start : start + SAMPLE].replace("\n", " ")))
    return {"scanned": total, "hits": len(hits), "samples": hits[:20]}
