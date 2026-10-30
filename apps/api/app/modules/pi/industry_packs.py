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

from app.modules.pi.industry_words import TRADE_PHRASES, TRADE_WORDS

PACKS_DIR = Path(__file__).parent / "packs" / "industry"
MAX_PACKS = 3  # industries per business, primary first
MIN_SCORE = 4.0  # below this a pack is not evidence enough to load
SECONDARY_SHARE = 0.75  # a secondary pack needs this share of the primary's score
STRONG_TERM = 5.0  # one rare term is not enough alone unless the person states their trade (below)
# catch-all packs match on everyday words, so they need more evidence than a specific one
GENERIC = {"general_factories_and_workshops", "retail_shops_and_chains"}
GENERIC_MIN_SCORE = 9.0
UNNAMED_MIN_SCORE = 8.0  # two terms, none of them a word of the trade's name: total weight needed
UNNAMED_MIN_TERM = 4.5  # ... and the heavier of the two must be at least this rare
KNOWN_BONUS = 4.0  # packs already stored for the business stay eligible without new evidence
PHRASE_BOOST = 1.5
NAME_BOOST = 2.2

# An explicit statement of the trade (spec 7.0: "I run a pharmacy", "hamara garments ka kaam hai").
# One word that names an industry is trusted on its own only inside such a statement: measured on
# the packs' own exchanges, trusting any single rare word picked the wrong industry about twice as
# often as the right one, and picked one for everyday text that names no trade at all.
STATEMENT = re.compile(
    r"\b(?:i|we)(?:'m|'re| am| are)?\s+(?:\w+\s+){0,2}?"
    r"(?:run|own|have|manage|operate|work in|working in|am in|are in|am an?|are an?|"
    r"sell|install|service|rent|make|manufacture|supply|provide|offer|repair|export|import|"
    r"build|grow|produce|deal in|do)\b"
    r"|\b(?:my|our)\s+(?:\w+\s+){0,2}?(?:business|company|work|shop|firm|factory|clinic|store|farm|school)\b"
    # a role in the trade counts too: "I'm the store manager at a pharmacy chain" (golden G13)
    r"|\b(?:i'm|i am|we're|we are)\s+(?:the |a |an )?(?:\w+\s+){0,2}?"
    r"(?:manager|owner|director|partner|employee|supervisor|accountant)\s+(?:at|of|in|for)\b"
    r"|\b(?:i|we)\s+(?:work|worked|working)\s+(?:at|in|for)\b"
    r"|\b(?:my|our)\s+(?:boss|father|brother|family|uncle|partner)\s+(?:\w+\s+){0,2}?"
    r"(?:own|owns|run|runs|manage|manages)\b"
    # "we're an airline", "I'm a tailor", "own a car repair shop", "we process milk"
    r"|\b(?:i'm|im|we're|i am|we are)\s+an?\b"
    r"|^\s*(?:own|run|have)\s+an?\b"
    r"|\b(?:i|we)\s+(?:process|breed|raise|trade|distribute|bottle|print|pack|ship|transport|"
    r"deliver|clean|cater|host|train|treat|teach|hatch|fatten|bake|stitch|tailor|"
    r"dye|weave|knit|mill|grind|fabricate|assemble|recruit|insure|ferment|brew)\b"
    r"|\b(?:mera|meri|mere|hamara|hamari|hamare|humara|humari|humare)\b"
    r"|\b(?:ki|ka|ke)\s+(?:dukaan|dukan|shop|factory|farm|agency|company|clinic|centre|center|"
    r"school|kaarkhana|karkhana|godown|showroom|office|firm)\s+(?:hai|hain|he|chalata|chalate|chalati)\b"
    r"|\b(?:dealer|supplier|distributor|contractor|beopari|thekedar|darzi)\s+(?:hoon|hun|hain)\b"
    # Arabic and Urdu script: "we have", "I own", "I run", "my", "our", "the business of"
    r"|\b(?:عندي|عندنا|لدي|لدينا|أملك|املك|نملك|أدير|ادير|ندير|صاحب|مالك)\b"
    r"|\b(?:میرا|میری|میرے|ہمارا|ہماری|ہمارے)\b|(?:چلاتا|چلاتی|چلاتے)\s+(?:ہوں|ہیں)"
    r"|\bکا\s+(?:کاروبار|کام)\b"
    r"|\b(?:chalata|chalati|chalate|chalaata)\s+(?:hun|hoon|hain)\b"
    r"|\bka\s+(?:kaam|karobar|business)\b"
    r"|\b(?:bechta|bechti|bechte|banata|banati|banate|karta|karti|karte)\s+(?:hun|hoon|hain)\b"
    r"|\b(?:نبيع|نصنع|نقدم|نؤجر|نركب|نصلح|أبيع|ابيع|أصنع|اصنع)\b"
    r"|(?:بیچتے|بناتے|کرتے)\s+ہیں",
    re.IGNORECASE,
)

# pi asking what the business is (prompt line "What kind of business is it?" and its translations)
TRADE_QUESTION = re.compile(
    r"\b(?:kind|type|sort) of (?:business|work|company|shop)\b|\bwhat (?:business|trade)\b"
    r"|\bwhat (?:do you|does your (?:business|company)) (?:do|sell|make)\b"
    r"|\b(?:kis|kaun ?si|konsi|kaunsa|konsa)\s+(?:qism|type|tarah|kism)\b"
    r"|\b(?:business|karobar|kaam)\s+(?:kis|kya|kaunsa|konsa)\b|\bkya kaam karte\b"
    r"|ما نوع|ما هو (?:نشاط|عمل)|کس (?:قسم|طرح) کا|کیا کام کرتے",
    re.IGNORECASE,
)
ANSWER_MAX_WORDS = 20  # longer replies are a story, judged clause by clause as usual

NAME_STOP = frozenset(
    "and the for with shops shop services service companies company businesses business "
    "operators operator agencies agency centres centre stores store suppliers supply dealers "
    "dealer admin including incl units unit retail manufacturing general other firm practice "
    "group club house plant collection delivery distribution production processing management "
    "repair installation operations agents agent providers trade traders sales rental hire "
    "support facility field eid ramadan online payment payments client clients customer "
    "customers contractor contractors chain chains network networks outlet outlets branch "
    "branches".split()  # how a business is arranged, not what trade it is
)

# Words that are part of a pack's name but are everyday English in their own right: "call" is half
# of "call centres" and also "he called me", "used" is half of "used car dealers" and also "we used
# to", "driving us mad" is not a driving school. Measured on the packs' own exchanges they named the
# wrong trade far more often than the right one, so a name word on this list is not evidence alone.
AMBIGUOUS_NAME_WORDS = frozenset(
    "call used private abroad material design building book patient seller air driving lot "
    "part front desk class lesson order record data real free power care health".split()
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
    stated: bool = False  # the person states their own trade or role in the primary's clause

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


# Arabic and Urdu script: one shape for the letters people write several ways, so "مطعم", "المطعم"
# and the Urdu spelling of the same word meet. Vowel marks and the tatweel are dropped.
_MARKS = re.compile("[ً-ٰٟۖ-ۜ۟-۪ۤۧۨ-ۭـ]")
_SCRIPT_FOLD = str.maketrans(
    {
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ۃ": "ه", "ى": "ي", "ی": "ي",
        "ے": "ي", "ې": "ي", "ہ": "ه", "ھ": "ه", "ک": "ك", "ں": "ن", "ؤ": "و", "ئ": "ي",
    }
)  # fmt: skip
_ARABIC_LETTER = re.compile("[؀-ۿ]")
_ARABIC_PREFIXES = ("وال", "بال", "فال", "كال", "لل", "ال")  # "and the", "with the", ..., "the"


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().replace("’", "'")
    text = _MARKS.sub("", text).translate(_SCRIPT_FOLD)
    return re.sub(r"[^\w']+", " ", text).replace("'", "").strip()


def _arabic_stem(word: str) -> str:
    """Drop the article and a joining "و" ("والطلبات" -> "طلبات", "ومطعم" -> "مطعم")."""
    if not _ARABIC_LETTER.search(word):
        return word
    for prefix in _ARABIC_PREFIXES:
        if word.startswith(prefix) and len(word) - len(prefix) >= 3:
            return word[len(prefix) :]
    return word[1:] if word.startswith("و") and len(word) >= 5 else word


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("ches", "shes", "sses", "xes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def _normal(text: str) -> str:
    return " ".join(_stem(_arabic_stem(word)) for word in _fold(text).split())


@lru_cache(maxsize=1)
def _core_name_words() -> dict[str, set[str]]:
    """pack key -> the words of its own name that identify the trade."""
    names: dict[str, set[str]] = {}
    for key, pack in load_packs().items():
        plain = re.sub(r"\([^)]*\)", " ", pack["name"])  # "(incl. Eid ...)" is not part of the name
        words = (_stem(w) for w in _fold(plain).split())
        names[key] = {
            w for w in words if len(w) >= 3 and w not in NAME_STOP and w not in AMBIGUOUS_NAME_WORDS
        }
    return names


@lru_cache(maxsize=1)
def _name_words() -> dict[str, set[str]]:
    """pack key -> the words that name the trade: its own name, and the same trade in Arabic and
    Urdu script (`industry_words`)."""
    names = {key: set(words) for key, words in _core_name_words().items()}
    for table in (TRADE_WORDS, TRADE_PHRASES):
        for key, trade_words in table.items():
            if key in names:
                names[key] |= {n for n in (_normal(w) for w in trade_words) if len(n) >= 3}
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


_CLAUSE_SPLIT = re.compile(r"[.!?؟۔،,;:\n]+|\b(?:and|but|while|aur|lekin|magar)\b", re.IGNORECASE)


_TRADE_VERBS = "sell|rent|make|install|repair|service|supply|import|export|build|buy|hire"
_VERB_PAIR = re.compile(rf"\b({_TRADE_VERBS})\s+and\s+({_TRADE_VERBS})\b", re.IGNORECASE)


def _statement_clauses(text: str) -> list[str]:
    """The folded clauses of `text` (padded with spaces) in which the person states their own
    trade or role. A statement elsewhere in the message does not vouch for a trade word:
    "I have a toothache, is there a dental clinic nearby" is not a dental clinic."""
    found = []
    # "we sell and install AC units" is one statement, not two clauses
    text = _VERB_PAIR.sub(lambda m: f"{m.group(1)} {m.group(2)}", text)
    for clause in _CLAUSE_SPLIT.split(text):
        if clause and clause.strip():
            folded = _normal(clause)
            # on the folded text too, so vowel marks or a joining "و" do not hide an Arabic one
            if STATEMENT.search(clause) or STATEMENT.search(folded):
                found.append(f" {folded} ")
    return found


def _name_share(key: str, normal: str) -> float:
    """How much of the pack's name the person's words fill: 1.0 when all of its name words are
    there."""
    names = _core_name_words()[key]
    padded = f" {normal} "
    return len([w for w in names if f" {w} " in padded]) / len(names) if names else 0.0


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
    if total < floor:
        return False
    if strongest >= STRONG_TERM and named and stated:
        return True
    # Two terms is enough when one of them names the trade. Two everyday words ("load" and
    # "driver", "khata" and "udhaar") are not: measured on the packs' own exchanges they picked
    # the wrong trade as often as the right one, so they must also carry real weight.
    return count >= 2 and (named or (total >= UNNAMED_MIN_SCORE and strongest >= UNNAMED_MIN_TERM))


def trade_answers(said: Sequence[tuple[bool, str]]) -> list[str]:
    """The person's messages that answer pi's "What kind of business is it?" directly. `said` is
    the chat oldest first as (from_pi, text). A short reply to that question is a statement of the
    trade even without "I run" ("small city hotel", "genset rental", "joote ki dukaan")."""
    answers: list[str] = []
    asked = False
    for from_pi, text in said:
        if from_pi:
            asked = bool(TRADE_QUESTION.search(text or ""))
        elif asked:
            if text and len(text.split()) <= ANSWER_MAX_WORDS:
                answers.append(text)
            asked = False
    return answers


def detect(
    texts: Iterable[str],
    known: Sequence[str] = (),
    limit: int = MAX_PACKS,
    answers: Sequence[str] = (),
) -> Detection:
    """Choose up to `limit` industry packs (primary first) and the overlays that apply.

    `texts` are what the person said (their own words only). `known` are packs already stored
    for the business; they get a bonus so the primary does not flip on one stray word. `answers`
    are their replies to pi's question about the kind of business (`trade_answers`): each counts
    as a statement of the trade.
    """
    packs = load_packs()
    texts = list(texts)
    texts += [a for a in answers if a not in texts]
    joined = " . ".join(texts)
    normal = _normal(joined)
    statement_clauses = _statement_clauses(joined)
    statement_clauses += [f" {_normal(a)} " for a in answers if a.strip()]

    def stated_for(term: str) -> bool:
        """The person states their trade or role in the same clause as this trade word."""
        return bool(term) and (
            any(f" {term} " in clause for clause in statement_clauses) or _possessed(normal, term)
        )

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
            if (key in known and scores[key] >= MIN_SCORE)  # stored packs stay eligible
            or _qualifies(
                key,
                scores[key],
                ev[1],
                ev[2],
                bool(ev[3]),
                stated_for(ev[3]),
            )
        ),
        # On equal evidence the pack whose name the matched word fills most comes first ("clinic"
        # is half of "clinics and gp practices", a fifth of the veterinary pack's name); the
        # alphabet only settles what is still tied.
        key=lambda r: (round(r[0], 6), _name_share(r[1], normal), r[1]),
        reverse=True,
    )
    # A pack that matched on a longer phrase beats the pack whose word is only part of that phrase:
    # "dermatology clinic" is the aesthetic and dermatology pack, not the general clinic. (Without
    # this the choice between them fell to the alphabet.)
    trade_term = {key: evidence[key][3].split() for _, key in ranked if evidence[key][3]}
    ranked = [
        r
        for r in ranked
        if r[1] not in trade_term  # only packs that matched on a trade word can be outranked
        or not any(
            other != r[1] and set(trade_term[r[1]]) < set(words)
            for other, words in trade_term.items()
        )
    ]
    # A catch-all pack matches everyday words ("store", "chain"). When the person states their own
    # trade or role and the word names a specific trade, that trade comes first: "the store manager
    # at a pharmacy chain" is a pharmacy (golden G13). Telling problems alone never reorders.
    common = max((evidence[r[1]][2] for r in ranked if r[1] in GENERIC), default=0.0)
    if any(
        r[1] not in GENERIC
        and stated_for(evidence[r[1]][3])
        and evidence[r[1]][2] >= common  # a trade word at least as rare as the catch-all's best
        for r in ranked
    ):
        ranked = [r for r in ranked if r[1] not in GENERIC] + [r for r in ranked if r[1] in GENERIC]
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
    stated = bool(chosen) and stated_for(evidence[chosen[0]][3])
    return Detection(
        chosen, overlays, {k: round(scores[k], 2) for k in [*chosen, *overlays]}, stated
    )


def evidence_score(text: str, key: str) -> float:
    """How much of this text points at one pack (0 when nothing does)."""
    found = _evidence(text).get(key)
    return float(found[0]) if found else 0.0


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


SECTOR_RULES_PATH = Path(__file__).parent / "packs" / "sector_rules.json"


@lru_cache(maxsize=1)
def sector_intros() -> dict[str, dict[str, Any]]:
    """Each sector's intro from the specification, keyed "C.1", "C.2", "I.1" (built with packs)."""
    if not SECTOR_RULES_PATH.exists():
        return {}
    loaded: dict[str, dict[str, Any]] = json.loads(SECTOR_RULES_PATH.read_text(encoding="utf-8"))
    return loaded


def sector_key(pack: dict[str, Any]) -> str:
    sector = pack.get("sector") or {}
    return f"{sector.get('code', '')}.{sector.get('part', 1)}"


def sector_rules(pack: dict[str, Any]) -> str:
    """The never-rules of the pack's sector, as the specification words them (7.C to 7.M). They
    bind every pack of the sector, however the pack itself was reached (primary or secondary)."""
    entry = sector_intros().get(sector_key(pack), {})
    rules = str(entry.get("rules") or "").strip()
    # The Industry Solutions addendum states its own scope limit for the sector (Part 4 intros):
    # it adds to the Brain spec's rules, never replaces them, and is not repeated when equal.
    scope = str(entry.get("addendum_scope") or "").strip()
    if scope and scope.lower() not in rules.lower():
        rules = f"{rules} {scope}".strip()
    return rules


_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"(])")
_PROHIBITION = re.compile(
    r"\b(?:never|no|not|nor|without|refuse[sd]?|declines?|stops?|stop|avoid|don'?t|only)\b", re.I
)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(" ".join(text.split())) if s.strip()]


def _clip_sentences(text: str, limit: int) -> str:
    """Whole sentences up to `limit` characters, never a cut sentence. When they do not all fit,
    the sentences that forbid something go first and the rest are dropped: a prohibition is never
    the part that was clipped."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    sentences = _sentences(text)
    order = sorted(range(len(sentences)), key=lambda i: (not _PROHIBITION.search(sentences[i]), i))
    kept: set[int] = set()
    used = 0
    for i in order:
        if used + len(sentences[i]) + 1 <= limit or not kept:
            kept.add(i)
            used += len(sentences[i]) + 1
    return " ".join(sentences[i] for i in sorted(kept))


def _clip(text: str, limit: int) -> str:
    """Clip at a word with an ellipsis. For lists of words and phrases, never for rules."""
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


COUNTRY_MARKS = {
    "PK": re.compile(r"\b(?:pakistan\w*|pk|karachi|lahore|punjab|sindh)\b", re.I),
    "AE": re.compile(r"\b(?:uae|dubai|emirates|sharjah|abu dhabi)\b", re.I),
    "CA": re.compile(r"\b(?:canada|canadian|ontario|alberta|toronto)\b", re.I),
}
_SEASON_SPLIT = re.compile(r"\s+-\s+|;\s+")


def seasons_for(seasons: Any, country: str | None, limit: int = 760) -> str:
    """The pack's seasons text for this customer: the parts that name no country, and the parts
    for their country, each whole (never cut); every country's first part when it is not known."""
    text = str(seasons or "").strip().lstrip("- ")
    parts = [p.strip(" .") for p in _SEASON_SPLIT.split(text) if p.strip(" .")]
    tagged: list[tuple[int, str | None]] = []
    for index, part in enumerate(parts):
        named = [c for c, mark in COUNTRY_MARKS.items() if mark.search(part)]
        tagged.append((index, named[0] if len(named) == 1 else None))
    if country in COUNTRY_MARKS:
        order = [i for i, c in tagged if c == country] + [i for i, c in tagged if c is None]
        wanted = {i for i, c in tagged if c in (None, country)}
    else:
        firsts: list[int] = []
        seen: set[str] = set()
        for i, c in tagged:
            if c and c not in seen:
                seen.add(c)
                firsts.append(i)
        order = firsts + [i for i, c in tagged if c is None] + [i for i, _ in tagged]
        wanted = set(range(len(parts)))
    kept: list[int] = []
    used = 0
    for i in order:
        if i in kept or i not in wanted:
            continue
        size = len(parts[i]) + 2
        if used + size > limit and kept:
            continue
        kept.append(i)
        used += size
    return "; ".join(parts[i] for i in sorted(kept))


def pick_questions(
    pack: dict[str, Any], categories: Sequence[str] = (), rotation: int = 0, limit: int = 6
) -> list[str]:
    """The questions to offer pi. For what was just noted: the questions for those problem
    categories. Otherwise the opening question of the first area and of three more areas, the
    three moving on each turn so every area (cash, people, growth ...) gets its turn."""
    asked: list[str] = []
    for category in categories:
        for question in questions_for(pack, category)[:3]:
            if question not in asked:
                asked.append(question)
    if asked:
        return asked[:limit]
    bank = [qs for qs in pack.get("questions", {}).values() if qs]
    if not bank:
        return []
    rest = bank[1:]
    picked = [bank[0][0]]
    if rest:
        start = (max(rotation, 0) * 3) % len(rest)
        picked += [rest[(start + n) % len(rest)][0] for n in range(min(3, len(rest)))]
    return picked


def pick_problems(
    pack: dict[str, Any], categories: Sequence[str] = (), rotation: int = 0, limit: int = 12
) -> list[dict[str, str]]:
    """The "heard as" phrases: those of the noted categories, else a spread across categories
    that moves on each turn (not the first dozen in the order of the PDF)."""
    problems = list(pack.get("problems", []))
    if categories:
        return [p for p in problems if p["category"] in categories][:limit]
    by_category: dict[str, list[dict[str, str]]] = {}
    for item in problems:
        by_category.setdefault(item["category"], []).append(item)
    lanes = list(by_category.values())
    spread: list[dict[str, str]] = []
    for depth in range(max((len(lane) for lane in lanes), default=0)):
        spread += [lane[depth] for lane in lanes if depth < len(lane)]
    if not spread:
        return []
    start = (max(rotation, 0) * 4) % len(spread)
    return (spread[start:] + spread[:start])[:limit]


def brief(
    pack: dict[str, Any],
    categories: Sequence[str] = (),
    max_chars: int = 2400,
    with_example: bool = False,
    *,
    country: str | None = None,
    rotation: int = 0,
    include_sector: bool = True,
) -> str:
    """Prompt text for one pack: how to listen and classify. Never includes build ideas.

    Lines are added most important first and any that no longer fit are dropped whole, so a rule
    is never cut: the sector's never-rules, then the pack's care rules, then its scope rule, then
    the questions, seasons for the customer's country, the trade's words and the problem phrases.
    `categories` are the problem categories just noted, `rotation` moves the spread of questions
    and phrases on each turn.
    """
    candidates: list[str] = []
    if include_sector and (rules := sector_rules(pack)):
        candidates.append("Sector rules, never: " + rules)
    for item in pack.get("care", [])[:10]:
        candidates.append("Care: " + _clip_sentences(item, 480))
    if pack.get("scope_rule"):
        candidates.append("Scope: " + _clip_sentences(pack["scope_rule"], 1000))
    asked = pick_questions(pack, categories, rotation)
    if asked:
        candidates.append("Questions, one at a time: " + " | ".join(asked))
    if pack.get("seasons") and (text := seasons_for(pack["seasons"], country)):
        candidates.append("Seasons and peaks: " + text)
    if pack.get("shape_facts"):
        facts = pack["shape_facts"][: 3 if categories else 7]
        candidates.append(
            "Learn only from what they say: " + "; ".join(_clip(f, 140) for f in facts)
        )
    words = list(pack.get("vocabulary", {}).items())[:14]
    if words:
        candidates.append("Their words: " + "; ".join(f"{w} = {_clip(m, 60)}" for w, m in words))
    local = list(pack.get("signal_glosses", {}).items())[:12]
    if local:
        candidates.append("Local words: " + "; ".join(f"{w} = {_clip(m, 50)}" for w, m in local))
    for item in pick_problems(pack, categories, rotation):
        candidates.append(
            f"Heard as {item['category']}/{item['subtype']}: {_clip(item['phrase'], 120)}"
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


def core_size(pack: dict[str, Any], include_sector: bool = True) -> int:
    """Characters the pack's rules need (sector rules, care, scope) so a smaller room can be
    widened to keep every one of them."""
    return len(
        brief(pack, max_chars=10_000, with_example=False, include_sector=include_sector).split(
            "\nQuestions"
        )[0]
    )


PRIMARY_ROOM = 5200
SECONDARY_ROOM = 2000
DEFAULT_BUDGET = 10_500  # was 9000: three packs whose rules are all long no longer lose any


def prompt_section(
    detection: Detection,
    categories: Sequence[str] = (),
    budget: int = DEFAULT_BUDGET,
    *,
    country: str | None = None,
    rotation: int = 0,
) -> str:
    """The INDUSTRY KNOWLEDGE block: primary pack fullest, then the others, then overlays.

    A pack's rules are never what is dropped for room: a secondary pack's room grows to hold its
    care and scope rules (and its sector's rules once, for the first pack of that sector).
    """
    packs = load_packs()
    keys = [*detection.industries, *detection.overlays]
    blocks: list[str] = []
    used = 0
    shown_sectors: set[str] = set()
    for position, key in enumerate(keys):
        pack = packs[key]
        sector = sector_key(pack)
        first_of_sector = sector not in shown_sectors
        base = PRIMARY_ROOM if position == 0 else SECONDARY_ROOM
        needed = core_size(pack, first_of_sector) + 300
        room = min(max(base, needed) if position else base, budget - used)
        if room < 300:
            break
        block = brief(
            pack,
            categories,
            max_chars=room,
            with_example=position == 0,
            country=country,
            rotation=rotation,
            include_sector=first_of_sector,
        )
        shown_sectors.add(sector)
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)
