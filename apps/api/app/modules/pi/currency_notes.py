"""Sector currency briefings: what is current in 2026 for small businesses in PK, UAE and CA.

Each cluster file in packs/currency/<cluster>.json covers a group of industry ids. An advisor
prompt reads `prompt_block(industry_key)` so ideas are never 2010-era. The notes are data placed
below the rules; they never override them. They are dated (`as_of`) and marked for human review.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CURRENCY_DIR = Path(__file__).parent / "packs" / "currency"
REQUIRED_FIELDS = (
    "cluster",
    "version",
    "as_of",
    "industries",
    "how_customers_find_and_choose",
    "what_works_now",
    "outdated_or_weak",
    "local_context",
    "never_assume",
    "review_status",
)
LIST_FIELDS = (
    "industries",
    "how_customers_find_and_choose",
    "what_works_now",
    "outdated_or_weak",
    "never_assume",
)


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """All clusters by name, and the cluster name of each industry id."""
    clusters: dict[str, dict[str, Any]] = {}
    index: dict[str, str] = {}
    if CURRENCY_DIR.is_dir():
        for path in sorted(CURRENCY_DIR.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            name = str(data.get("cluster") or path.stem)
            clusters[name] = data
            for key in data.get("industries") or []:
                index.setdefault(str(key), name)
    return clusters, index


def clusters() -> dict[str, dict[str, Any]]:
    return dict(_load()[0])


def for_industry(industry_key: str) -> dict[str, Any] | None:
    """The briefing of the cluster that covers this industry, or None."""
    all_clusters, index = _load()
    name = index.get(str(industry_key or ""))
    return all_clusters.get(name) if name else None


def validate(data: dict[str, Any]) -> list[str]:
    """Problems with one cluster file (empty when it is well formed)."""
    problems = [f"missing {f}" for f in REQUIRED_FIELDS if f not in data]
    for f in LIST_FIELDS:
        value = data.get(f)
        if f in data and (not isinstance(value, list) or not value):
            problems.append(f"{f} must be a non-empty list")
    ctx = data.get("local_context")
    if "local_context" in data and not (
        isinstance(ctx, dict) and all(ctx.get(c) for c in ("PK", "UAE", "CA"))
    ):
        problems.append("local_context needs PK, UAE and CA lists")
    return problems


def _bullets(items: list[str], count: int) -> str:
    return "\n".join(f"- {text}" for text in items[:count])


def prompt_block(industry_key: str, max_chars: int = 1800) -> str:
    """Compact text for a prompt; empty when the industry has no briefing."""
    data = for_industry(industry_key)
    if not data:
        return ""
    ctx = data.get("local_context") or {}
    sections = [
        (f"Current as of {data.get('as_of', '')} (check with the owner, do not assert):", ""),
        ("How customers find and choose now:", _bullets(data["how_customers_find_and_choose"], 4)),
        ("Works now:", _bullets(data["what_works_now"], 5)),
        ("Dated or weak, avoid:", _bullets(data["outdated_or_weak"], 4)),
        (
            "Local context:",
            "\n".join(f"- {c}: {(ctx.get(c) or [''])[-1]}" for c in ("PK", "UAE", "CA")),
        ),
        ("Never assume the owner has:", _bullets(data["never_assume"], 4)),
    ]
    out = ""
    for title, body in sections:
        chunk = f"{title}\n{body}\n" if body else f"{title}\n"
        if len(out) + len(chunk) > max_chars:
            break
        out += chunk
    return out.strip()[:max_chars]
