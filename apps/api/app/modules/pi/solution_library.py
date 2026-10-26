"""The generic Solution Library (platform spec Book 2 Part 7.4, retrieval order in Book 3 Part 2.1).

When a person asks for a solution and the industry entries have nothing for the problem (no industry
known yet, a trade the entries do not name, a problem none of them covers), pi still gives two
ideas: those of the problem's category in this library. The ideas are the spec's own, kept only if
they pass pi's idea guard (scripts/build_generic_library.py), so no idea here is edited.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

LIBRARY = Path(__file__).parent / "packs" / "library" / "generic_library.json"
SAME_IDEA = 0.75  # word overlap at which an idea counts as already said


@lru_cache(maxsize=1)
def load() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(LIBRARY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dict(data.get("categories") or {})


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w{3,}", (text or "").lower()))


def already_said(idea: str, given: list[str]) -> bool:
    mine = _words(idea)
    return bool(mine) and any(len(mine & _words(g)) / len(mine) >= SAME_IDEA for g in given)


def ideas_for(category: str, given: list[str] | None = None, count: int = 2) -> list[str]:
    """Up to `count` ideas of the category not yet given (in order, the spec's best first)."""
    entry = load().get(category) or {}
    said = list(given or [])
    chosen: list[str] = []
    for idea in entry.get("ideas") or []:
        if not already_said(str(idea), said + chosen):
            chosen.append(str(idea))
        if len(chosen) == count:
            break
    return chosen


def build_keys(category: str) -> list[str]:
    return [str(k) for k in (load().get(category) or {}).get("build_keys") or []]


def never_say(category: str) -> str:
    return str((load().get(category) or {}).get("never_say") or "")
