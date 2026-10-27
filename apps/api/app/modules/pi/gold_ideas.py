"""The owner's gold ideas (packs/library/gold_ideas.json): 28 trades, two ideas each, written and
approved by the owner as the level pi's own ideas should reach. They are shown to the expert advisor
as examples of level (never to copy) and used as the reference in tests."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.modules.pi import solution_ideas

GOLD_FILE = Path(__file__).parent / "packs" / "library" / "gold_ideas.json"


@lru_cache(maxsize=1)
def load() -> list[dict[str, Any]]:
    try:
        return list(json.loads(GOLD_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []


def nearest(words: str, industry: str, count: int = 3) -> list[dict[str, Any]]:
    """The gold problems closest to the owner's words and trade, by shared evidence (trade nouns
    and general words do not count); only those that share something."""
    heard = solution_ideas._evidence(f"{words} {industry}")  # noqa: SLF001
    scored = []
    for item in load():
        theirs = solution_ideas._evidence(f"{item['problem']} {item['industry']}")  # noqa: SLF001
        shared = (heard & theirs) - solution_ideas.WEAK - solution_ideas.TRADE
        if shared:
            scored.append((len(shared), item))
    scored.sort(key=lambda pair: -pair[0])
    return [item for _n, item in scored[:count]]


def examples(words: str, industry: str, count: int = 2) -> list[str]:
    """One idea from each of the nearest gold problems."""
    return [
        str(item["ideas"][0])[:240] for item in nearest(words, industry, count) if item["ideas"]
    ]
