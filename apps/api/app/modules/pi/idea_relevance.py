# ruff: noqa: E501
"""PS-3: does a candidate idea address the owner's ACTUAL problem? Pure, no database, no model.

`evaluate_idea(idea_text, problems, constraints, tried, language, known_facts)` returns an
`IdeaVerdict`. It replaces the question "does the idea share a word with the noted problems" (the
live rule G8, which rejected every Urdu and Arabic idea) with a question about meaning:

- Both texts are folded (NFKC, tashkeel, Arabic and Urdu letter forms, digits of every script) and
  split into tokens; the Arabic definite article and one-letter prefixes are peeled off.
- Words are mapped to topic CONCEPTS (`idea_relevance_lexicon`: delivery, bookings, collections,
  stock shortage ...) in English, Roman Urdu, Urdu, Arabic and Hindi. "Late orders", "delivery
  delay" and "تأخر التوصيل" are one concept; "double booking" and "overlapping reservations" are one.
- A problem is described by its own words (title, the owner's words, where, impact, an owner-said
  cause) and by its recorded category and sub-type. An idea is LINKED when it shares a concept (or,
  as weaker evidence, a content word) with a problem, in any language mix.

Verdicts (never raises; linear in the capped input):

- VIOLATES_CONSTRAINT: only when the caller's `constraint_gate` says "violates". It wins over
  everything, including relevance. With no gate (or a gate that fails or returns junk) constraint
  compliance is "unknown": it is never "ok" by default.
- UNKNOWN: nothing to judge by (no text, unsupported script, no problem, or no topic recognised).
  UNKNOWN is never LINKED.
- REPEATS_TRIED: the idea repeats a remedy the owner said they already tried.
- LINKED / UNLINKED / GENERIC as above. GENERIC is boilerplate that would fit any business.

The module writes no money, figure or promise: reasons are fixed codes and evidence words are the
idea's own words. The adapter `gate_from_option_gate` shows where the L2-1 gate plugs in.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.modules.pi import idea_relevance_lexicon as lex

# ----- limits (inputs are capped, so time is linear in the capped size) ---------------------------
MAX_IDEA_CHARS = 4000
MAX_PROBLEMS = 20
MAX_FIELD_CHARS = 400
MAX_WORDS_PER_PROBLEM = 12
MAX_TRIED = 20
MAX_TRIED_CHARS = 300
MAX_FACT_CHARS = 600
MAX_NGRAM = 4
MAX_EVIDENCE = 6
LINK_MIN = 2  # points that make a link
STRONG = 4  # points that beat generic wording and an off-topic idea
GENERIC_SPECIFIC = 4  # content words beyond a boilerplate phrase that keep a link

SUPPORTED_LANGUAGES = frozenset({"en", "roman_ur", "ur", "ar", "hi"})


class IdeaKind(StrEnum):
    LINKED = "linked"
    UNLINKED = "unlinked"
    VIOLATES_CONSTRAINT = "violates_constraint"
    UNKNOWN = "unknown"
    REPEATS_TRIED = "repeats_tried"
    GENERIC = "generic"


@dataclass(frozen=True, slots=True)
class IdeaVerdict:
    kind: IdeaKind
    reason: (
        str  # a fixed code, e.g. "concept_match", "no_topic_recognised", "constraint_gate:budget"
    )
    linked_problem_ids: tuple[str, ...] = ()
    evidence_words: tuple[str, ...] = ()  # the idea's own words that carry the verdict
    constraint_status: str = "unknown"  # "ok" | "violated" | "unknown"; "ok" only from a gate
    detail: str = ""  # the gate's own text for a violation (capped); otherwise ""
    concepts: tuple[str, ...] = ()  # topic concepts found in the idea
    score: int = 0  # the best problem's link points


# ----- the constraint gate (L2-1's gate_options plugs in through `gate_from_option_gate`) ---------


class GateVerdict(Protocol):
    @property
    def status(self) -> str: ...  # "ok" | "violates" | "unknown"


ConstraintGate = Callable[[str, Any, str | None], GateVerdict | None]


def gate_from_option_gate(
    gate_options: Callable[..., Any], to_requirements: Callable[[Any], Any]
) -> ConstraintGate:
    """Adapt `option_gate.gate_options(options, requirements, language)` (branch pi/l2-hard-gate):
    `to_requirements(constraints)` builds its `Requirements` from the problem's stored constraints.
    The adapter reads only `accepted`, `rejected`, `unknown` and each item's `.verdict`; it imports
    nothing from that module."""

    def gate(idea: str, constraints: Any, language: str | None) -> GateVerdict | None:
        result = gate_options([idea], to_requirements(constraints), language)
        for bucket in (result.rejected, result.unknown, result.accepted):
            for item in bucket:
                verdict: GateVerdict = item.verdict
                return verdict
        return None

    return gate


# ----- normalisation --------------------------------------------------------------------------------

_FOLD = str.maketrans(
    {
        "ي": "ی", "ى": "ی", "ې": "ی", "ێ": "ی", "ے": "ی", "ۓ": "ی", "ئ": "ی",
        "ك": "ک", "ڪ": "ک",
        "ة": "ہ", "ه": "ہ", "ھ": "ہ", "ۃ": "ہ", "ۂ": "ہ", "ە": "ہ",
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ؤ": "و",
        "ں": "ن",
        "ء": None, "ـ": None,
        "ँ": "ं",
    }
)  # fmt: skip
_DROP = frozenset(
    chr(c)
    for c in (
        0x27,
        0x2019,
        0x2BC,
        0x60,
        0x200B,
        0x200C,
        0x200D,
        0x200E,
        0x200F,
        0x202A,
        0x202B,
        0x202C,
        0x202D,
        0x202E,
        0x2066,
        0x2067,
        0x2068,
        0x2069,
        0xFEFF,
        0xAD,
        0x93C,
    )
)


def _is_arabic_mark(code: int) -> bool:
    return (
        0x0610 <= code <= 0x061A
        or 0x064B <= code <= 0x065F
        or code == 0x0670
        or 0x06D6 <= code <= 0x06DC
        or 0x06DF <= code <= 0x06E8
        or 0x06EA <= code <= 0x06ED
    )


def normalize_text(text: Any) -> str:
    """Folded, lower-case text of letters, digits and single spaces: NFKC, no tashkeel or tatweel,
    Arabic and Urdu letter forms folded together, digits of every script as ASCII, punctuation and
    control characters as spaces. Anything that is not a string is the empty string."""
    if not isinstance(text, str) or not text:
        return ""
    out: list[str] = []
    for ch in unicodedata.normalize("NFKC", text[: MAX_IDEA_CHARS * 2]).lower():
        if ch in _DROP:
            continue
        code = ord(ch)
        if code < 128:
            out.append(ch if ch.isalnum() else " ")
            continue
        cat = unicodedata.category(ch)
        if cat == "Nd":
            out.append(str(unicodedata.decimal(ch, 0)))
        elif cat == "Mn" and (_is_arabic_mark(code) or 0x0300 <= code <= 0x036F):
            continue
        elif cat[0] in "LN":
            if code < 0x250 or 0x1E00 <= code <= 0x1EFF:  # Latin with accents: drop the accents
                base = unicodedata.normalize("NFD", ch)[0]
                out.append(base if base.isalnum() else " ")
            else:
                out.append(ch.translate(_FOLD) if ch in _FOLD_KEYS else ch)
        elif cat[0] == "M":
            out.append(ch.translate(_FOLD) if ch in _FOLD_KEYS else ch)
        else:
            out.append(" ")
    return " ".join("".join(out).split())


_FOLD_KEYS = frozenset(chr(k) for k in _FOLD)


def _script_of(ch: str) -> str:
    code = ord(ch)
    if code < 0x250 or 0x1E00 <= code <= 0x1EFF:
        return "latin"
    if (
        0x0600 <= code <= 0x06FF
        or 0x0750 <= code <= 0x077F
        or 0xFB50 <= code <= 0xFDFF
        or 0xFE70 <= code <= 0xFEFF
    ):
        return "arabic"
    if 0x0900 <= code <= 0x097F:
        return "devanagari"
    return "other"


def _is_arabic_token(tok: str) -> bool:
    return bool(tok) and _script_of(tok[0]) == "arabic"


_ARABIC_PREFIXES = "وبلفک"


def _core(tok: str) -> str:
    """The token with the Arabic definite article and a one-letter prefix peeled off (Arabic script
    only; at least three letters stay). Latin and Devanagari tokens are returned as they are."""
    if not _is_arabic_token(tok):
        return tok
    s = tok
    for _ in range(3):
        if len(s) > 4 and s[:2] == "ال":
            s = s[2:]
        elif len(s) > 4 and s[0] in _ARABIC_PREFIXES:
            s = s[1:]
        else:
            break
    return s


_LATIN_SUFFIXES = ("ing", "ed", "es", "s", "ly")
_ARABIC_SUFFIXES = ("ات", "ون", "ین", "یں", "وں", "ها", "ہا")
_DEVA_SUFFIXES = ("ों", "ें", "ाएं", "ाओं", "ियां", "ियाँ")


def _stem(core: str) -> str:
    """A light stem used only for comparing a word of the idea with a word of the problem."""
    if not core:
        return core
    if _is_arabic_token(core):
        for suf in _ARABIC_SUFFIXES:
            if core.endswith(suf) and len(core) - len(suf) >= 3:
                return core[: -len(suf)]
        return core
    if _script_of(core[0]) == "devanagari":
        for suf in _DEVA_SUFFIXES:
            if core.endswith(suf) and len(core) - len(suf) >= 2:
                return core[: -len(suf)]
        return core
    for suf in _LATIN_SUFFIXES:
        if core.endswith(suf) and len(core) - len(suf) >= 4:
            return core[: -len(suf)]
    return core


# ----- the lexicon index ------------------------------------------------------------------------------


def _split_terms(raw: str) -> list[str]:
    """Split on `|` outside parentheses and brackets."""
    parts: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in raw:
        if ch in "([":
            depth += 1
        elif ch in ")]" and depth:
            depth -= 1
        if ch == "|" and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _expand(term: str, limit: int = 64) -> list[str]:
    """Expand the tiny pattern syntax of the lexicon: `(a|b)`, `(a )?`, `[ae]`, and `x?` for an
    optional single character. At most `limit` strings; a longer expansion is cut off."""
    results = [""]
    i = 0
    n = len(term)
    while i < n:
        ch = term[i]
        if ch == "(":
            j = term.index(")", i)
            alts = term[i + 1 : j].split("|")
            i = j + 1
            if i < n and term[i] == "?":
                alts.append("")
                i += 1
            results = [r + a for r in results for a in alts][:limit]
        elif ch == "[":
            j = term.index("]", i)
            opts = list(term[i + 1 : j])
            i = j + 1
            if i < n and term[i] == "?":
                opts.append("")
                i += 1
            results = [r + o for r in results for o in opts][:limit]
        elif i + 1 < n and term[i + 1] == "?":
            results = [r + c for r in results for c in (ch, "")][:limit]
            i += 2
        else:
            results = [r + ch for r in results]
            i += 1
    return results


def _term_tokens(term: str) -> tuple[bool, tuple[str, ...]]:
    star = term.rstrip().endswith("*")
    norm = normalize_text(term.replace("*", " "))
    toks = tuple(_core(t) for t in norm.split())
    return star, toks


class _Index:
    """Terms of 1 to MAX_NGRAM words. Each term is stored under its words as written and under their
    `_core` forms, and a text is looked up the same two ways, so an Arabic prefix is neither required
    nor a reason to miss. A trailing `*` makes the last word a prefix."""

    def __init__(self, concepts: Sequence[lex.Concept]) -> None:
        self.keys = [c.key for c in concepts]
        self.weak = [c.weak for c in concepts]
        self.context = [c.context for c in concepts]
        self.exact: dict[tuple[str, ...], list[int]] = {}
        self.prefix: dict[
            tuple[str, ...], dict[str, list[int]]
        ] = {}  # leading words -> prefix -> ids
        self.max_lead = 0
        for idx, concept in enumerate(concepts):
            for raw in _split_terms(concept.terms):
                for term in _expand(raw):
                    star = term.rstrip().endswith("*")
                    norm = normalize_text(term.replace("*", " "))
                    words = tuple(norm.split())
                    if not words or len(words) > MAX_NGRAM:
                        continue
                    for toks in {words, tuple(_core(w) for w in words)}:
                        if star and len(toks[-1]) >= (
                            2 if len(toks) > 1 else 4 if toks[-1].isascii() else 3
                        ):
                            self.prefix.setdefault(toks[:-1], {}).setdefault(toks[-1], []).append(
                                idx
                            )
                            self.max_lead = max(self.max_lead, len(toks) - 1)
                        else:
                            self.exact.setdefault(toks, []).append(idx)
        self.prefix_lens = sorted({len(p) for d in self.prefix.values() for p in d})

    def scan(self, words: Sequence[str]) -> list[tuple[int, str]]:
        """(concept index, surface) for every match in the text (given as its words)."""
        hits: list[tuple[int, str]] = []
        cores = [_core(w) for w in words]
        for seq in (words,) if cores == list(words) else (words, cores):
            n = len(seq)
            for i in range(n):
                for length in range(1, MAX_NGRAM + 1):
                    if i + length > n:
                        break
                    key = tuple(seq[i : i + length])
                    for idx in self.exact.get(key, ()):
                        hits.append((idx, " ".join(key)))
                for lead in range(0, self.max_lead + 1):
                    if i + lead >= n:
                        break
                    table = self.prefix.get(tuple(seq[i : i + lead]))
                    if not table:
                        continue
                    last = seq[i + lead]
                    for plen in self.prefix_lens:
                        if len(last) >= plen:
                            for idx in table.get(last[:plen], ()):
                                hits.append((idx, " ".join(seq[i : i + lead + 1])))
        return hits


_CONCEPTS = lex.CONCEPTS
_OFF = lex.OFF_TOPIC
_MAIN = _Index(_CONCEPTS)
_OFF_INDEX = _Index(_OFF)
_GENERIC = _Index([lex.Concept("generic", (), (), lex.GENERIC_PHRASES)])
_REMEDY_KEYS = list(lex.REMEDIES)
_REMEDY = _Index([lex.Concept(k, (), (), v) for k, v in lex.REMEDIES.items()])

_STOP = frozenset(normalize_text(lex.STOPWORDS + " tried try trying kiya kia").split())
_WEAK = frozenset(normalize_text(lex.WEAK_TOKENS).split())

_FAMILY_OF: dict[int, str] = {
    i: lex.FAMILIES[c.key] for i, c in enumerate(_CONCEPTS) if c.key in lex.FAMILIES
}
_TAXO_CAT: dict[str, frozenset[int]] = {}
_TAXO_SUB: dict[str, frozenset[int]] = {}


def _build_taxo() -> None:
    cats: dict[str, set[int]] = {}
    subs: dict[str, set[int]] = {}
    for idx, concept in enumerate(_CONCEPTS):
        for cat in concept.cats:
            cats.setdefault(cat, set()).add(idx)
        for sub in concept.subs:
            subs.setdefault(sub, set()).add(idx)
    _TAXO_CAT.update({k: frozenset(v) for k, v in cats.items()})
    _TAXO_SUB.update({k: frozenset(v) for k, v in subs.items()})


_build_taxo()


# ----- reading the inputs defensively -------------------------------------------------------------------


def _get(obj: Any, name: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name)
    try:
        return getattr(obj, name, None)
    except Exception:  # a property that raises
        return None


def _strings(value: Any, depth: int = 0) -> list[str]:
    """Every string in a value (str, list, dict of such), capped; other types are ignored."""
    if isinstance(value, str):
        return [value[:MAX_FIELD_CHARS]]
    if depth > 2:
        return []
    out: list[str] = []
    if isinstance(value, Mapping):
        for v in list(value.values())[:MAX_WORDS_PER_PROBLEM]:
            out += _strings(v, depth + 1)
    elif isinstance(value, (list, tuple)):
        for v in list(value)[:MAX_WORDS_PER_PROBLEM]:
            out += _strings(v, depth + 1)
    return out


_OWNER_CAUSE = ("owner_said", "confirmed")


def _problem_texts(problem: Any) -> list[str]:
    parts: list[str] = []
    for name in (
        "title",
        "title_local",
        "summary",
        "where",
        "impact",
        "trigger",
        "since",
        "who_notices",
    ):
        parts += _strings(_get(problem, name))
    parts += _strings(_get(problem, "user_words"))
    cause = _get(problem, "cause")
    status = _get(problem, "cause_status")
    text = _get(problem, "cause_text")
    if isinstance(cause, Mapping):
        status = cause.get("status", status)
        text = cause.get("text", text)
    elif isinstance(cause, str):
        text = text or cause
    if status in _OWNER_CAUSE and isinstance(text, str):  # a guessed cause links nothing
        parts.append(text[:MAX_FIELD_CHARS])
    return parts


def _clean_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


@dataclass(frozen=True, slots=True)
class _ProblemProfile:
    pid: str
    text_concepts: frozenset[int]
    text_families: frozenset[str]
    taxo_concepts: frozenset[int]
    stems: frozenset[str]


def _tokens(text: Any) -> list[str]:
    return normalize_text(text).split()


def _content_stems(words: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for word in words:
        if word in _STOP or word in _WEAK or word.isdigit():
            continue
        tok = _core(word)
        if tok in _STOP or tok in _WEAK:
            continue
        if len(tok) < (4 if tok.isascii() else 3):
            continue
        stem = _stem(tok)
        if stem in _STOP or stem in _WEAK:
            continue
        out.add(stem)
    return out


def _profile(problem: Any, index: int) -> _ProblemProfile | None:
    cores: list[str] = []
    for text in _problem_texts(problem):
        cores += _tokens(text)
    concepts = {i for i, _ in _MAIN.scan(cores)}
    category = _clean_str(_get(problem, "category")).strip()
    subtype = _clean_str(_get(problem, "subtype")).strip()
    taxo = _TAXO_SUB.get(subtype) or _TAXO_CAT.get(category) or frozenset()
    if not cores and not taxo:
        return None
    raw_id = _get(problem, "id")
    if raw_id is None:
        raw_id = _get(problem, "ref")
    if raw_id is None:
        raw_id = _get(problem, "number")
    pid = str(raw_id)[:40] if raw_id is not None else f"p{index + 1}"
    families = frozenset(_FAMILY_OF[i] for i in concepts if i in _FAMILY_OF)
    return _ProblemProfile(
        pid, frozenset(concepts), families, frozenset(taxo), frozenset(_content_stems(cores))
    )


def _profiles(problems: Any) -> list[_ProblemProfile]:
    if isinstance(problems, (str, bytes, Mapping)) or problems is None:
        # one record passed alone is accepted; anything else is no problems
        items: list[Any] = (
            [problems]
            if isinstance(problems, Mapping) and ("title" in problems or "user_words" in problems)
            else []
        )
    else:
        try:
            items = list(problems)[:MAX_PROBLEMS]
        except TypeError:
            items = []
    out: list[_ProblemProfile] = []
    for i, item in enumerate(items[:MAX_PROBLEMS]):
        if item is None or isinstance(item, (str, bytes, int, float)):
            continue
        prof = _profile(item, i)
        if prof is not None:
            out.append(prof)
    return out


# ----- the gate -------------------------------------------------------------------------------------------


def _run_gate(
    gate: ConstraintGate | None, idea: str, constraints: Any, language: str | None
) -> tuple[str, str, str]:
    """(constraint_status, rule, detail). Anything but a clear "ok" or "violates" is "unknown"."""
    if gate is None:
        return "unknown", "", ""
    try:
        result = gate(idea, constraints, language)
    except Exception:
        return "unknown", "", ""
    if result is None:
        return "unknown", "", ""
    status = (
        result.get("status") if isinstance(result, Mapping) else getattr(result, "status", None)
    )
    if status == "ok":
        return "ok", "", ""
    if status in ("violates", "violated"):
        rule = _get(result, "rule")
        reason = _get(result, "reason")
        rule_s = re.sub(r"[^a-z0-9_]", "", str(rule).lower())[:40] if isinstance(rule, str) else ""
        return "violated", rule_s, reason[:200] if isinstance(reason, str) else ""
    return "unknown", "", ""


# ----- tried -----------------------------------------------------------------------------------------------


def _tried_texts(tried: Any) -> list[str]:
    if isinstance(tried, (str, bytes)):
        items: list[Any] = [tried] if isinstance(tried, str) else []
    elif isinstance(tried, Mapping) or tried is None:
        items = []
    else:
        try:
            items = list(tried)[:MAX_TRIED]
        except TypeError:
            items = []
    out: list[str] = []
    for item in items[:MAX_TRIED]:
        text = item if isinstance(item, str) else _get(item, "what") if item is not None else None
        if isinstance(text, str) and text.strip():
            out.append(text[:MAX_TRIED_CHARS])
    return out


def _repeats_tried(
    idea_cores: list[str], idea_stems: set[str], tried: Any
) -> tuple[str, str] | None:
    """(reason, evidence) when the idea repeats something the owner already tried."""
    idea_rem = {_REMEDY_KEYS[i]: s for i, s in _REMEDY.scan(idea_cores)}
    for text in _tried_texts(tried):
        cores = _tokens(text)
        rem = {_REMEDY_KEYS[i] for i, _ in _REMEDY.scan(cores)}
        shared_rem = rem & set(idea_rem)
        if shared_rem:
            key = sorted(shared_rem)[0]
            return f"tried_remedy:{key}", idea_rem[key]
        stems = _content_stems(cores)
        common = stems & idea_stems
        if len(common) >= 2 and len(common) / max(len(stems), 1) >= 0.6:
            return "tried_words", sorted(common)[0]
    return None


# ----- the verdict -----------------------------------------------------------------------------------------


def _norm_language(language: Any) -> str:
    if not isinstance(language, str):
        return ""
    low = language.strip().lower().replace("-", "_")
    short = {"urdu": "ur", "arabic": "ar", "hindi": "hi", "english": "en", "roman": "roman_ur"}.get(
        low, low
    )
    if short.startswith("en_"):
        short = "en"
    return short[:12]


def _evidence(surfaces: Iterable[str]) -> tuple[str, ...]:
    seen: list[str] = []
    for s in surfaces:
        if s and s not in seen:
            seen.append(s)
        if len(seen) >= MAX_EVIDENCE:
            break
    return tuple(seen)


def _facts_concepts(known_facts: Any) -> set[int]:
    cores: list[str] = []
    for text in _strings(known_facts)[:MAX_WORDS_PER_PROBLEM]:
        cores += _tokens(text[:MAX_FACT_CHARS])
    return {i for i, _ in _MAIN.scan(cores)}


def _analyse(
    idea: str,
    problems: Any,
    tried: Any,
    known_facts: Any,
) -> IdeaVerdict:
    norm = normalize_text(idea)
    letters = Counter(_script_of(ch) for ch in norm if ch.isalpha())
    total = sum(letters.values())
    if total == 0:
        return IdeaVerdict(IdeaKind.UNKNOWN, "no_text")
    if letters["other"] * 2 > total:
        return IdeaVerdict(IdeaKind.UNKNOWN, "unsupported_script")

    cores = norm.split()
    hits = _MAIN.scan(cores)
    idea_concepts: dict[int, str] = {}
    for idx, surface in hits:
        idea_concepts.setdefault(idx, surface)
    off_hits = _OFF_INDEX.scan(cores)
    generic_hits = _GENERIC.scan(cores)
    stems = _content_stems(cores)
    names = tuple(sorted(_MAIN.keys[i] for i in idea_concepts))

    profiles = _profiles(problems)
    if not profiles:
        return IdeaVerdict(IdeaKind.UNKNOWN, "no_problem", concepts=names)

    repeat = _repeats_tried(cores, stems, tried)
    best_score = 0
    best_evidence: list[str] = []
    linked: list[tuple[int, str]] = []
    for prof in profiles:
        score = 0
        evidence: list[str] = []
        text_hit = False
        for idx, surface in idea_concepts.items():
            weak = _MAIN.weak[idx] or _MAIN.context[idx]  # a tool or a setting word: one point
            if idx in prof.text_concepts:
                score += 1 if weak else 3
                text_hit = text_hit or not weak
                evidence.append(surface)
            elif idx in prof.taxo_concepts and not weak:
                score += 2
                evidence.append(surface)
            elif not weak and _FAMILY_OF.get(idx) in prof.text_families:
                score += 2  # a neighbouring concept of the same family
                evidence.append(surface)
        said = {w for e in evidence for w in e.split()} | {
            _stem(_core(w)) for e in evidence for w in e.split()
        }
        shared = sorted(
            (stems & prof.stems) - said
        )  # a word a concept already explains counts once
        score += min(len(shared), 2) * 2
        evidence += shared[:2]
        if off_hits and score < STRONG:
            score = 0  # a decor, merchandise or contest idea needs real evidence to count
        if score >= LINK_MIN:
            linked.append((score, prof.pid))
        if score > best_score:
            best_score, best_evidence = score, evidence
    linked.sort(key=lambda t: -t[0])
    ids = tuple(pid for _, pid in linked)

    if repeat is not None:
        return IdeaVerdict(
            IdeaKind.REPEATS_TRIED,
            repeat[0],
            ids,
            _evidence([repeat[1]]),
            concepts=names,
            score=best_score,
        )
    if generic_hits and best_score < STRONG:
        said = {_stem(_core(w)) for _, phrase in generic_hits for w in phrase.split()}
        specific = len(stems - said)  # a real sentence beyond the boilerplate keeps its link
        if not (best_score >= LINK_MIN and specific >= GENERIC_SPECIFIC):
            return IdeaVerdict(
                IdeaKind.GENERIC,
                "boilerplate_phrase",
                (),
                _evidence(s for _, s in generic_hits),
                concepts=names,
            )
    if best_score >= LINK_MIN:
        return IdeaVerdict(
            IdeaKind.LINKED,
            "shares_topic_with_problem",
            ids,
            _evidence(best_evidence),
            concepts=names,
            score=best_score,
        )
    if (
        not idea_concepts
        and not off_hits
        and len(stems) <= 1
        and sum(w in _STOP or w in _WEAK for w in cores) >= 2
    ):
        return IdeaVerdict(IdeaKind.GENERIC, "too_little_to_tell_apart", concepts=names)
    if idea_concepts or off_hits:
        topics = _evidence([s for s in idea_concepts.values()] + [s for _, s in off_hits])
        facts = _facts_concepts(known_facts) if known_facts else set()
        if idea_concepts and set(idea_concepts) <= facts:
            return IdeaVerdict(
                IdeaKind.UNLINKED, "business_context_only", (), topics, concepts=names
            )
        return IdeaVerdict(IdeaKind.UNLINKED, "other_topic", (), topics, concepts=names)
    return IdeaVerdict(IdeaKind.UNKNOWN, "no_topic_recognised")


def evaluate_idea(
    idea_text: str,
    problems: Sequence[Any] | None,
    constraints: Any = None,
    tried: Any = None,
    language: str | None = None,
    known_facts: Any = None,
    *,
    constraint_gate: ConstraintGate | None = None,
) -> IdeaVerdict:
    """Judge one candidate idea against the noted problems. Never raises.

    problems: records (mappings or objects) with title, title_local, user_words, category, subtype,
      where, since, impact, summary, and cause (`{"text", "status"}`, or `cause_text` and
      `cause_status`); a guessed (pi_inferred) cause is ignored.
    constraints: the stored constraints (`{"budget", "staff", "deadline", "cannot_change": [...]}` of
      problem_fields.py); passed to `constraint_gate` and read by nothing else. Without a gate every
      verdict says constraint_status "unknown".
    tried: `[{"what", "outcome", "msg"}]` (problem_fields.py) or plain strings.
    constraint_gate: `(idea, constraints, language) -> object with .status`; "violates" wins over
      every other verdict, "ok" sets constraint_status "ok", anything else is "unknown".
    known_facts: confirmed facts about the business (any mapping or list of text). They only explain
      an UNLINKED idea ("business_context_only"); they never link an idea.
    """
    text = idea_text[:MAX_IDEA_CHARS] if isinstance(idea_text, str) else ""
    lang = _norm_language(language)
    status, rule, detail = _run_gate(constraint_gate, text, constraints, lang or None)
    try:
        verdict = _analyse(text, problems, tried, known_facts)
    except Exception:
        verdict = IdeaVerdict(IdeaKind.UNKNOWN, "internal_error")
    if status == "violated":
        return IdeaVerdict(
            IdeaKind.VIOLATES_CONSTRAINT,
            f"constraint_gate:{rule}" if rule else "constraint_gate",
            verdict.linked_problem_ids,
            verdict.evidence_words,
            "violated",
            detail,
            verdict.concepts,
            verdict.score,
        )
    return IdeaVerdict(
        verdict.kind,
        verdict.reason,
        verdict.linked_problem_ids,
        verdict.evidence_words,
        status,
        "",
        verdict.concepts,
        verdict.score,
    )
