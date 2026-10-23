"""Industry knowledge packs for pi (pi Brain spec, Part 7).

Each pack lives in packs/industry/<key>.json (built from the spec by
scripts/build_industry_packs.py). A pack never changes pi's rules or voice: it only tells pi
what to listen for, what to ask next and how to classify a problem. `detect` picks up to
three industry packs for a business, primary first, plus any cross-industry overlays;
`brief` renders the part of a pack that is safe to show the model while listening.
"""

import json
import math
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

PACKS_DIR = Path(__file__).parent / "packs" / "industry"
MAX_PACKS = 3  # industries per business, primary first
MIN_SCORE = 4.0  # below this a pack is not evidence enough to load
SECONDARY_SHARE = 0.75  # a secondary pack needs this share of the primary's score
STRONG_TERM = 5.0  # one rare term is not enough alone unless the person states their trade (below)
# catch-all packs match on everyday words, so they need more evidence than a specific one
GENERIC = {"general_factories_and_workshops", "retail_shops_and_chains"}
GENERIC_MIN_SCORE = 9.0
KNOWN_BONUS = 4.0  # packs already stored for the business stay eligible without new evidence
PHRASE_BOOST = 1.5
NAME_BOOST = 2.2

# An explicit statement of the trade (spec 7.0: "I run a pharmacy", "hamara garments ka kaam hai").
# One word that names an industry is trusted on its own only inside such a statement: measured on
# the packs' own exchanges, trusting any single rare word picked the wrong industry about twice as
# often as the right one, and picked one for everyday text that names no trade at all.
STATEMENT = re.compile(
    r"\b(?:i|we)(?:'m|'re| am| are)?\s+(?:\w+\s+){0,2}?"
    r"(?:run|own|have|manage|operate|work in|working in|am in|are in|am an?|are an?)\b"
    r"|\b(?:my|our)\s+(?:\w+\s+){0,2}?(?:business|company|work|shop|firm|factory|clinic|store|farm|school)\b"
    r"|\b(?:mera|meri|hamara|hamari|humara|humari)\b"
    r"|\b(?:chalata|chalati|chalate|chalaata)\s+(?:hun|hoon|hain)\b"
    r"|\bka\s+(?:kaam|karobar|business)\b",
    re.IGNORECASE,
)

NAME_STOP = frozenset(
    "and the for with shops shop services service companies company businesses business "
    "operators operator agencies agency centres centre stores store suppliers supply dealers "
    "dealer admin including incl units unit retail manufacturing general other firm practice "
    "group club house plant collection delivery distribution production processing management "
    "repair installation operations agents agent providers trade traders sales rental hire "
    "support facility field eid ramadan online payment payments client clients customer "
    "customers contractor contractors".split()
)

# Question-bank areas are written in plain words; map a problem category to the ones that fit.
CATEGORY_AREAS = {
    "stock_inventory": ("stock", "inventory", "supply"),
    "sales_revenue": ("sales", "revenue", "bookings", "orders"),
    "cash_collections": ("cash", "collections", "payments", "money"),
    "margin_cost": ("margin", "costs", "cost", "pricing"),
    "customers_retention": ("customers", "customer", "retention", "patients", "students"),
    "marketing_leads": ("marketing", "leads", "enquiries"),
    "orders_fulfilment": ("orders", "delivery", "dispatch"),
    "suppliers_purchasing": ("buying", "suppliers", "purchasing", "procurement"),
    "people_staff": ("staff", "people", "team", "hiring"),
    "operations_process": ("operations", "process", "workflow"),
    "reporting_visibility": ("reporting", "reports", "visibility"),
    "tech_systems": ("systems", "software", "tools"),
}


@dataclass(frozen=True)
class Detection:
    """Packs chosen for a business. `industries` is primary first and at most MAX_PACKS."""

    industries: list[str] = field(default_factory=list)
    overlays: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def primary(self) -> str | None:
        return self.industries[0] if self.industries else None

    @property
    def confidence(self) -> float:
        """0..1, how sure the primary pack is (rises with its score)."""
        score = self.scores.get(self.primary or "", 0.0)
        return round(1 - math.exp(-score / 8), 2)


@lru_cache(maxsize=1)
def load_packs() -> dict[str, dict[str, Any]]:
    packs: dict[str, dict[str, Any]] = {}
    for path in sorted(PACKS_DIR.glob("*.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        packs[pack["key"]] = pack
    return packs


def get_pack(key: str) -> dict[str, Any] | None:
    return load_packs().get(key)


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().replace("’", "'")
    return re.sub(r"[^\w']+", " ", text).replace("'", "").strip()


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("ches", "shes", "sses", "xes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def _normal(text: str) -> str:
    return " ".join(_stem(word) for word in _fold(text).split())


@lru_cache(maxsize=1)
def _name_words() -> dict[str, set[str]]:
    """pack key -> the words of its name that identify the trade."""
    names: dict[str, set[str]] = {}
    for key, pack in load_packs().items():
        plain = re.sub(r"\([^)]*\)", " ", pack["name"])  # "(incl. Eid ...)" is not part of the name
        words = (_stem(w) for w in _fold(plain).split())
        names[key] = {w for w in words if len(w) >= 3 and w not in NAME_STOP}
    return names


@lru_cache(maxsize=1)
def _index() -> dict[str, dict[str, float]]:
    """pack key -> {normalised signal: weight}; rare signals weigh more than common ones."""
    packs = load_packs()
    raw: dict[str, set[str]] = {}
    for key, pack in packs.items():
        terms = {_normal(term) for term in pack.get("signals", [])}
        terms |= {_normal(word) for word in pack.get("vocabulary", {})}
        raw[key] = {t for t in terms if len(t) >= 3}
    names = _name_words()
    frequency: dict[str, int] = {}
    for key in packs:
        for term in raw[key] | names[key]:
            frequency[term] = frequency.get(term, 0) + 1
    total = max(len(packs), 1)
    index: dict[str, dict[str, float]] = {}
    for key in packs:
        weights: dict[str, float] = {}
        for term in raw[key]:
            weight = math.log(1 + total / frequency[term])
            weights[term] = weight * (PHRASE_BOOST if " " in term else 1.0)
        for term in names[key]:
            weights[term] = max(
                weights.get(term, 0.0), math.log(1 + total / frequency[term]) * NAME_BOOST
            )
        index[key] = weights
    return index


def _evidence(text: str) -> dict[str, tuple[float, int, float, str]]:
    """pack key -> (summed weight, distinct terms matched, strongest single weight, that
    strongest term when it is a word of the pack's own name, else "")."""
    padded = f" {_normal(text)} "
    names = _name_words()
    found: dict[str, tuple[float, int, float, str]] = {}
    for key, weights in _index().items():
        hits = [(weight, term) for term, weight in weights.items() if f" {term} " in padded]
        if hits:
            strongest, term = max(hits)
            found[key] = (
                sum(w for w, _ in hits),
                len(hits),
                strongest,
                term if term in names[key] else "",
            )
    return found


def _possessed(text: str, term: str) -> bool:
    """The person owns the trade word: "our accounting practice", "my pharmacy"."""
    return (
        bool(term)
        and re.search(rf"\b(?:my|our)\s+(?:\w+\s+){{0,2}}{re.escape(term)}\b", text) is not None
    )


def score(text: str) -> dict[str, float]:
    """Evidence for every pack in `text` (only packs with some match)."""
    return {key: round(ev[0], 2) for key, ev in _evidence(text).items()}


def _qualifies(
    key: str, total: float, count: int, strongest: float, named: bool, stated: bool
) -> bool:
    """Enough evidence to load the pack: two different terms, or one rare word that names the
    trade inside an explicit statement of it ("I run a pharmacy", "our accounting practice")."""
    floor = GENERIC_MIN_SCORE if key in GENERIC else MIN_SCORE
    return total >= floor and (count >= 2 or (strongest >= STRONG_TERM and named and stated))


def detect(
    texts: Iterable[str],
    known: Sequence[str] = (),
    limit: int = MAX_PACKS,
) -> Detection:
    """Choose up to `limit` industry packs (primary first) and the overlays that apply.

    `texts` are what the person said (their own words only). `known` are packs already stored
    for the business; they get a bonus so the primary does not flip on one stray word.
    """
    packs = load_packs()
    joined = " . ".join(texts)
    stated = STATEMENT.search(joined) is not None
    normal = _normal(joined)
    evidence = _evidence(joined)
    scores = {key: ev[0] for key, ev in evidence.items()}
    for key in known:
        if key in packs:
            scores[key] = scores.get(key, 0.0) + KNOWN_BONUS
            _, count, strongest, named = evidence.get(key, (0.0, 0, 0.0, ""))
            evidence[key] = (scores[key], max(count, 2), strongest, named)  # stored stay eligible
    ranked = sorted(
        (
            (scores[key], key)
            for key, ev in evidence.items()
            if _qualifies(
                key,
                scores[key],
                ev[1],
                ev[2],
                bool(ev[3]),
                stated or _possessed(normal, ev[3]),
            )
        ),
        reverse=True,
    )
    chosen: list[str] = []
    overlays: list[str] = []
    for value, key in ranked:
        if packs[key]["kind"] == "overlay":
            overlays.append(key)
            continue
        industries_so_far = len(chosen)
        if industries_so_far and (
            value < scores[chosen[0]] * SECONDARY_SHARE or evidence[key][1] < 2
        ):
            continue
        if industries_so_far < limit:
            chosen.append(key)
    return Detection(chosen, overlays, {k: round(scores[k], 2) for k in [*chosen, *overlays]})


def _areas(category: str | None) -> tuple[str, ...]:
    if not category:
        return ()
    return CATEGORY_AREAS.get(category, tuple(category.split("_")))


def questions_for(pack: dict[str, Any], category: str | None = None) -> list[str]:
    """The pack's questions for a problem category, in the order the pack lists them."""
    bank: dict[str, list[str]] = pack.get("questions", {})
    wanted = _areas(category)
    if not wanted:
        return [q for asked in bank.values() for q in asked]
    return [q for area, asked in bank.items() if any(w in area for w in wanted) for q in asked]


def build_ideas(pack: dict[str, Any]) -> list[str]:
    """What Workzap might build. Internal: for the document drafter, never said to the person."""
    return list(pack.get("build_ideas", []))


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def brief(
    pack: dict[str, Any],
    categories: Sequence[str] = (),
    max_chars: int = 2400,
    with_example: bool = False,
) -> str:
    """Prompt text for one pack: how to listen and classify. Never includes build ideas.

    Lines are added most useful first (care rules, the questions, scope, then the trade's
    words and problem phrases) and any that no longer fit are dropped whole.
    """
    candidates: list[str] = []
    for item in pack.get("care", [])[:8]:
        candidates.append("Care: " + _clip(item, 260))
    asked: list[str] = []
    for category in categories or (None,):
        asked += questions_for(pack, category)[: 3 if categories else 4]
    if asked:
        candidates.append("Questions, one at a time: " + " | ".join(asked))
    if pack.get("scope_rule"):
        candidates.append("Scope: " + _clip(pack["scope_rule"], 360))
    if pack.get("seasons"):
        candidates.append("Seasons and peaks: " + _clip(str(pack["seasons"]).lstrip("- "), 420))
    if pack.get("shape_facts") and not categories:
        shape = "; ".join(_clip(f, 90) for f in pack["shape_facts"][:4])
        candidates.append("Learn only from what they say: " + shape)
    words = list(pack.get("vocabulary", {}).items())[:14]
    if words:
        candidates.append("Their words: " + "; ".join(f"{w} = {_clip(m, 60)}" for w, m in words))
    local = list(pack.get("signal_glosses", {}).items())[:12]
    if local:
        candidates.append("Local words: " + "; ".join(f"{w} = {_clip(m, 50)}" for w, m in local))
    found = [p for p in pack.get("problems", []) if not categories or p["category"] in categories]
    for item in found[:14]:
        candidates.append(
            f"Heard as {item['category']}/{item['subtype']}: {_clip(item['phrase'], 110)}"
        )
    if with_example and pack.get("exchange"):
        turns = " / ".join(f"{t['role']}: {_clip(t['text'], 140)}" for t in pack["exchange"][:4])
        candidates.append("Example of the voice, never a script: " + turns)
    lines = [f"{pack['name']}:"]
    used = len(lines[0])
    for line in candidates:
        if used + len(line) + 1 <= max_chars:
            lines.append(line)
            used += len(line) + 1
    return "\n".join(lines)


def prompt_section(
    detection: Detection,
    categories: Sequence[str] = (),
    budget: int = 9000,
) -> str:
    """The INDUSTRY KNOWLEDGE block: primary pack fullest, then the others, then overlays."""
    packs = load_packs()
    keys = [*detection.industries, *detection.overlays]
    blocks: list[str] = []
    used = 0
    for position, key in enumerate(keys):
        room = min(5200 if position == 0 else 2000, budget - used)
        if room < 300:
            break
        block = brief(packs[key], categories, max_chars=room, with_example=position == 0)
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)
