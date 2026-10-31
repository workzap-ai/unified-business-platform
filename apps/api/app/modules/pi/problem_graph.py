"""PS-7: the problem graph and root-cause layer model. Pure functions: no database, no model call.

Input: noted problem records, the owner's own messages and the stored requirements. Output:

1. a LAYER for every problem and every cause or consequence statement (symptom, immediate problem,
   operational problem, root-cause candidate, contributing factor, business consequence,
   unverified), each with a status (owner_said, confirmed, pi_inferred) and the evidence words;
2. a RELATIONSHIP GRAPH between problems. An edge exists only with an evidence basis:
   owner_stated (the owner said A leads to B), shared_cause (the same stated cause),
   shared_resource_or_process (the same courier, staff, system... named in both) and
   category_family (same taxonomy family, weak). Every edge carries kind, evidence, strength and is
   flagged hypothesis or not; none is ever created without evidence (platform spec v1.6, 4.2 and
   4.3: "Links must have evidence", "Extraction is checked");
3. COVERAGE: which problems an option addresses directly and which it may reach through a shared
   cause (always a hypothesis, never a promise: spec 3.6);
4. HYPOTHESES for a problem from the taxonomy and the industry packs: possible causes to CHECK,
   all `pi_inferred`, each with what to check and what is already known for and against (spec 3.5:
   "a hypothesis becomes confirmed only when the owner confirms it");
5. LEARN FIRST: the unconfirmed causes ranked by how many problems each would explain (a count,
   never a probability);
6. PRIORITY from the owner's own stated frequency, money and count only; ties and unknowns are
   reported as "cannot rank yet".

Statuses follow `problem_fields` (L2-2): `owner_said` needs the owner's own words (every usable
evidence word occurs as a whole word in the owner's own message); a model-written record never
proves it; `pi_inferred` never becomes `owner_said` or `confirmed` here; `confirmed` comes only
from a stored `confirmed` cause or from the caller's `confirmed_links`.

Never raises. Every input is capped (MAX_*), every loop is linear in the capped input except the
pair loops over at most MAX_PROBLEMS problems, which stop at MAX_EDGES_PER_KIND.
Not reviewed by a native speaker of Urdu or Arabic. Scripted tests prove the wiring and the
rules, not real-world reasoning.
"""

import bisect
import dataclasses
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.modules.pi import problem_fields as pf
from app.modules.pi import problem_graph_lexicon as lx
from app.modules.pi import taxonomy

MAX_PROBLEMS = 60
MAX_MESSAGES = 100
MAX_MESSAGE_CHARS = 2000
MAX_FIELD_CHARS = 600
MAX_SENTENCE_CHARS = 400
MAX_CLAIMS = 200
MAX_EDGES_PER_KIND = 300
MAX_HYPOTHESES = 8
MAX_EVIDENCE = 3
MAX_PACK_HYPOTHESES = 2
MAX_QUOTE = 160

OWNER_SAID = pf.OWNER_SAID
CONFIRMED = pf.CONFIRMED
PI_INFERRED = pf.PI_INFERRED
OWNER_STATUSES = pf.OWNER_STATUSES


class Layer(StrEnum):
    SYMPTOM = "symptom"
    IMMEDIATE_PROBLEM = "immediate_problem"
    OPERATIONAL_PROBLEM = "operational_problem"
    ROOT_CAUSE_CANDIDATE = "root_cause_candidate"
    CONTRIBUTING_FACTOR = "contributing_factor"
    BUSINESS_CONSEQUENCE = "business_consequence"
    UNVERIFIED = "unverified"


class EdgeKind(StrEnum):
    OWNER_STATED = "owner_stated"
    SHARED_CAUSE = "shared_cause"
    SHARED_RESOURCE = "shared_resource_or_process"
    CATEGORY_FAMILY = "category_family"


STRENGTH_RANK = {"strong": 3, "medium": 2, "weak": 1}


# ---------------------------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Evidence:
    text: str
    status: str  # owner_said when quoted from the owner's own message, else pi_inferred
    source: str  # owner_message | problem_record | tried


@dataclass(frozen=True, slots=True)
class Statement:
    id: str
    problem_id: str | None
    layer: Layer
    text: str
    status: str
    evidence_words: tuple[str, ...]
    reason: str
    hedged: bool = False
    quote: str = ""


@dataclass(frozen=True, slots=True)
class ProblemNode:
    id: str
    title: str
    layer: Layer
    status: str
    evidence_words: tuple[str, ...]
    reason: str
    category: str
    subtype: str
    category_guessed: bool = False


@dataclass(frozen=True, slots=True)
class Edge:
    id: str
    kind: EdgeKind
    from_id: str
    to_id: str
    directed: bool
    evidence_status: str
    hypothesis: bool
    confirmed: bool
    strength: str
    strength_rank: int
    evidence: tuple[str, ...]
    hedged: bool = False


@dataclass(frozen=True, slots=True)
class Hypothesis:
    key: str
    text: str
    shown_text: str
    source: str  # taxonomy | pack
    source_ref: str
    status: str
    what_to_check: str
    supports: tuple[Evidence, ...]
    contradicts: tuple[Evidence, ...]
    language: str
    text_language: str


@dataclass(frozen=True, slots=True)
class LearnItem:
    key: str
    text: str
    status: str  # owner_said (ask to confirm) or pi_inferred (ask to check)
    explains: tuple[str, ...]
    count: int
    supports: int
    what_to_check: str
    tied_with: tuple[str, ...] = ()
    ruled_against: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Ranked:
    problem_id: str
    level: int
    basis: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PriorityResult:
    levels: tuple[tuple[str, ...], ...]
    ranked: tuple[Ranked, ...]
    cannot_rank: tuple[str, ...]
    ordered_pairs: tuple[tuple[str, str, str], ...]  # (higher, lower, why)
    complete: bool
    note: str


@dataclass(frozen=True, slots=True)
class CoveredVia:
    problem_id: str
    via_problem_id: str
    via_kind: str
    evidence: tuple[str, ...]
    hypothesis: bool
    strength: str


@dataclass(frozen=True, slots=True)
class Coverage:
    direct: tuple[str, ...]
    through_shared_cause: tuple[CoveredVia, ...]
    unknown_ids: tuple[str, ...]
    not_covered: tuple[str, ...]
    note: str


@dataclass(frozen=True, slots=True)
class ProblemGraph:
    language: str
    problems: tuple[ProblemNode, ...] = ()
    statements: tuple[Statement, ...] = ()
    edges: tuple[Edge, ...] = ()
    hypotheses: tuple[tuple[str, tuple[Hypothesis, ...]], ...] = ()
    learn_first: tuple[LearnItem, ...] = ()
    priority: PriorityResult | None = None
    warnings: tuple[str, ...] = ()
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        out = _dict(self)
        out["hypotheses"] = {pid: _dict(hs) for pid, hs in self.hypotheses}
        return out  # type: ignore[no-any-return]

    def hypotheses_of(self, problem_id: str) -> tuple[Hypothesis, ...]:
        return next((hs for pid, hs in self.hypotheses if pid == problem_id), ())


def _dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, StrEnum):
        return obj.value
    if isinstance(obj, (tuple, list)):
        return [_dict(x) for x in obj]
    if isinstance(obj, Mapping):
        return {str(k): _dict(v) for k, v in obj.items()}
    return obj


# ---------------------------------------------------------------------------------------------
# Folding: one lower-case form for Latin, Urdu and Arabic, with a map back to the original text so
# a quote is always the owner's own characters.
# ---------------------------------------------------------------------------------------------
_MAP = {
    "ي": "ی", "ى": "ی", "ې": "ی", "ئ": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "ہ": "ه", "ھ": "ه",
    "ۃ": "ه", "ە": "ه", "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ؤ": "و", "ک": "ک", "گ": "گ",
    "،": ",", "؟": "?", "۔": ".", "؛": ";", "‌": " ", "‍": " ", "‏": " ", "‎": " ",
    "’": "'", "‘": "'", "´": "'",
}  # fmt: skip


def fold(text: Any, cap: int = MAX_MESSAGE_CHARS) -> tuple[str, list[int]]:
    """(folded text, index in the original for each folded character). Never raises."""
    try:
        raw = str(text or "")[:cap]
    except Exception:  # noqa: BLE001
        return "", []
    out: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(raw):
        if ch == "ـ" or unicodedata.category(ch) == "Mn":
            continue
        for c in unicodedata.normalize("NFKC", ch).lower():
            if unicodedata.category(c) == "Mn":
                continue
            if c.isdigit() and not c.isascii():
                try:
                    c = str(unicodedata.digit(c))
                except ValueError:
                    pass
            out.append(_MAP.get(c, c))
            idx.append(i)
    return "".join(out), idx


def _f(text: str) -> str:
    return fold(text, 10_000)[0]


def _marker_re(markers: Iterable[str]) -> re.Pattern[str]:
    parts = sorted({_f(m).strip() for m in markers if _f(m).strip()}, key=len, reverse=True)
    body = "|".join(r"\s+".join(re.escape(w) for w in p.split()) for p in parts)
    return re.compile(rf"(?<!\w)(?:{body})(?!\w)")


_FOLLOWS = _marker_re(lx.FOLLOWS)
_PRECEDES = _marker_re(lx.PRECEDES)
_CONN = _marker_re((*lx.FOLLOWS, *lx.PRECEDES))
_FOLLOW_SET = {_f(m).strip() for m in lx.FOLLOWS}
_ISLIYE = {
    _f(m).strip()
    for m in (
        "is liye",
        "isliye",
        "isi liye",
        "isiliye",
        "is lie",
        "isi lie",
        "اس لیے",
        "اس لئے",
        "اسی لیے",
        "اسی لئے",
    )
}
_SO = re.compile(r"(?:^|,)\s*so(?!\w)")
_HEDGE = _marker_re(lx.HEDGES)
_PARTIAL = _marker_re(lx.PARTIAL)
_NEG = {_f(w) for w in lx.NEGATIONS}
_COND = _marker_re(lx.CONDITIONALS)
_QWORD = _marker_re(lx.QUESTION_WORDS)
_NOT_HELPED = _marker_re(lx.NOT_HELPED)
_CONSEQ = _marker_re(lx.CONSEQUENCE)
_SYMPTOM = _marker_re(lx.SYMPTOM)
_KE = re.compile(r"^((?:\S+\s+){0,5}?)(ke|kay|کہ|که)\s+(\S.*)$")
_STOP = {_f(w) for w in lx.STOP}
_GENERIC = {_f(w) for w in lx.GENERIC}
_RES_RE = {k: _marker_re(v) for k, v in lx.RESOURCES.items()}
_CAUSE_RE = {
    k: _marker_re(v["triggers"])  # type: ignore[arg-type]
    for k, v in lx.CAUSES.items()
}
_WORD = re.compile(r"\w+")
_SENT_END = re.compile(r"[.!?]+(?=\s|$)|\n+")
_AR_PREFIX = ("وال", "بال", "لل", "ال")


def _stem(tok: str) -> str:
    if any("؀" <= c <= "ۿ" for c in tok):
        for p in _AR_PREFIX:
            if tok.startswith(p) and len(tok) - len(p) >= 3:
                tok = tok[len(p) :]
                break
        else:
            if tok.startswith("و") and len(tok) > 4:
                tok = tok[1:]
    if len(tok) > 5:
        return tok[:5]
    if len(tok) > 3 and tok.endswith("s") and tok.isascii():
        return tok[:-1]
    return tok


def _stems(folded: str) -> list[str]:
    out = []
    for t in _WORD.findall(folded):
        if t in _STOP or t in _GENERIC or t.isdigit():
            continue
        if len(t) < 3 and t.isascii():
            continue
        if len(t) < 2:
            continue
        out.append(_stem(t))
    return out


def _flat(x: Any, depth: int = 0) -> str:
    """Any record value as one capped string (dict values, list items, numbers)."""
    if x is None or depth > 3:
        return ""
    if isinstance(x, str):
        return x[:MAX_FIELD_CHARS]
    if isinstance(x, bool):
        return ""
    if isinstance(x, (int, float)):
        return str(x)
    if isinstance(x, Mapping):
        return " ".join(_flat(v, depth + 1) for v in list(x.values())[:12])[:MAX_FIELD_CHARS]
    if isinstance(x, (list, tuple)):
        return " ".join(_flat(v, depth + 1) for v in list(x)[:12])[:MAX_FIELD_CHARS]
    return ""


def _lang(language: Any) -> str:
    return lx.ALIASES.get(str(language or "en").strip().lower().replace(" ", "_"), "en")


def _clip(text: str, n: int = MAX_QUOTE) -> str:
    return " ".join(str(text).split())[:n].strip(" ,;")


# ---------------------------------------------------------------------------------------------
# Corpus: the owner's messages as sentences, folded, with cause-word hits indexed once.
# ---------------------------------------------------------------------------------------------
@dataclass
class _Sentence:
    folded: str
    orig: str
    msg: int
    start: int  # offset in the message's folded text
    stems: list[str] = field(default_factory=list)


@dataclass
class _Msg:
    orig: str
    folded: str
    idx: list[int]


@dataclass
class _Corpus:
    raw: str = ""
    msgs: list[_Msg] = field(default_factory=list)
    sents: list[_Sentence] = field(default_factory=list)
    by_stem: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    hits: dict[str, list[tuple[int, int, bool]]] = field(
        default_factory=dict
    )  # key -> (sent, pos, negated)


def _messages(owner_messages: Any) -> list[str]:
    out: list[str] = []
    if isinstance(owner_messages, str):
        owner_messages = [owner_messages]
    if not isinstance(owner_messages, Iterable) or isinstance(owner_messages, Mapping):
        return out
    for m in owner_messages:
        if isinstance(m, Mapping):
            m = m.get("text") or m.get("content") or ""
        if isinstance(m, str) and m.strip():
            out.append(m[:MAX_MESSAGE_CHARS])
        if len(out) >= MAX_MESSAGES:
            break
    return out


def _negated_before(folded: str, pos: int) -> bool:
    before = _WORD.findall(folded[max(0, pos - 40) : pos])[-3:]
    return any(t in _NEG for t in before)


def _build_corpus(messages: list[str], with_hits: bool = True) -> _Corpus:
    c = _Corpus(raw="\n".join(messages))
    for mi, text in enumerate(messages):
        folded, idx = fold(text)
        c.msgs.append(_Msg(text, folded, idx))
        start = 0
        spans = []
        for m in _SENT_END.finditer(folded):
            spans.append((start, m.end()))
            start = m.end()
        spans.append((start, len(folded)))
        for s, e in spans:
            seg = folded[s:e].strip()
            if not seg:
                continue
            lead = len(folded[s:e]) - len(folded[s:e].lstrip())
            s2 = s + lead
            e2 = min(e, s2 + MAX_SENTENCE_CHARS)
            sent = _Sentence(folded[s2:e2], "", mi, s2)
            sent.stems = _stems(sent.folded)
            sent.orig = _orig(c.msgs[mi], s2, e2)
            si = len(c.sents)
            c.sents.append(sent)
            for st in set(sent.stems):
                c.by_stem[st].append(si)
    if with_hits and c.sents:
        starts = [(s.msg, s.start) for s in c.sents]
        for key, rx in _CAUSE_RE.items():
            found = []
            for mi, msg in enumerate(c.msgs):
                for hit in rx.finditer(msg.folded):
                    k = bisect.bisect_right(starts, (mi, hit.start())) - 1
                    if k >= 0 and c.sents[k].msg == mi:
                        found.append((k, hit.start(), _negated_before(msg.folded, hit.start())))
                    if len(found) >= 50:
                        break
            if found:
                c.hits[key] = found
    return c


def _orig(msg: _Msg, s: int, e: int) -> str:
    if not msg.idx or s >= len(msg.idx) or e <= s:
        return ""
    return msg.orig[msg.idx[s] : msg.idx[min(e, len(msg.idx)) - 1] + 1]


# ---------------------------------------------------------------------------------------------
# Problem records
# ---------------------------------------------------------------------------------------------
@dataclass
class _Cause:
    text: str
    status: str
    words: tuple[str, ...]
    hedged: bool = False
    partial: bool = False
    source: str = "record"
    quote: str = ""


@dataclass
class _Prob:
    id: str
    i: int
    title: str
    words: list[str]
    category: str
    subtype: str
    guessed: bool
    industry: str
    text_f: str
    stems: set[str]
    resources: dict[str, bool]  # key -> owner_said
    causes: list[_Cause]
    status: str
    rec_status: str
    raw: Mapping[str, Any]
    tried: list[tuple[str, str]] = field(default_factory=list)


def guess_category(text: str) -> str:
    """A taxonomy category guessed from words (a hint only, never stored as the owner's)."""
    f = _f(text)
    toks = set(_WORD.findall(f))
    best: dict[str, int] = {}
    for cat, words in lx.CATEGORY_WORDS.items():
        n = 0
        for w in words:
            wf = _f(w)
            if (" " in wf and wf in f) or wf in toks or _stem(wf) in {_stem(t) for t in toks}:
                n += 1
        if n:
            best[cat] = n
    if not best:
        return taxonomy.OTHER
    top = max(best.values())
    winners = [c for c, n in best.items() if n == top]
    return winners[0] if len(winners) == 1 else taxonomy.OTHER


def _cause_status(cause: Mapping[str, Any], corpus_raw: str) -> str:
    status = str(cause.get("status") or "")
    if status not in OWNER_STATUSES:
        return PI_INFERRED
    ev = cause.get("evidence") or {}
    words = [str(w) for w in (ev.get("words") if isinstance(ev, Mapping) else None) or []]
    if not pf.usable_words(words):
        return PI_INFERRED
    if corpus_raw and not pf.said_by_owner(words, corpus_raw):
        return PI_INFERRED
    return status


def _req_causes(requirements: Any) -> tuple[dict[str, Any], dict[str, list[tuple[str, str]]]]:
    causes: dict[str, Any] = {}
    tried: dict[str, list[tuple[str, str]]] = {}
    probs = getattr(requirements, "problems", None)
    if probs is None and isinstance(requirements, Mapping):
        probs = requirements.get("problems")
    for r in list(probs or [])[:MAX_PROBLEMS]:
        try:
            pid = str(
                getattr(r, "problem_id", None)
                or (r.get("problem_id") if isinstance(r, Mapping) else "")
                or ""
            )
            num = str(getattr(r, "number", "") or "")
            cause = getattr(r, "cause", None)
            if cause is not None and not isinstance(cause, Mapping):
                cause = {
                    "text": cause.text,
                    "status": cause.status,
                    "evidence": {
                        "words": list(cause.evidence_words),
                        "msgs": list(cause.evidence_msgs),
                    },
                }
            elif isinstance(r, Mapping):
                cause = r.get("cause")
            tr = [(str(t.what), str(t.outcome)) for t in (getattr(r, "tried", None) or ())]
            for key in (pid, num):
                if key and key != "0":
                    if cause:
                        causes[key] = cause
                    if tr:
                        tried[key] = tr
        except Exception:  # noqa: BLE001
            continue
    return causes, tried


def _resource_hits(text_f: str) -> list[tuple[str, str]]:
    out = []
    for key, rx in _RES_RE.items():
        m = rx.search(text_f)
        if m:
            out.append((key, m.group(0)))
    return out


def _prepare(
    problems: Any, corpus: _Corpus, requirements: Any, warnings: list[str]
) -> tuple[list[_Prob], bool]:
    plist = (
        list(problems)
        if isinstance(problems, Iterable) and not isinstance(problems, (str, Mapping))
        else []
    )
    truncated = len(plist) > MAX_PROBLEMS
    if truncated:
        warnings.append(f"problems_truncated:{len(plist)}")
    req_causes, req_tried = _req_causes(requirements)
    out: list[_Prob] = []
    seen: set[str] = set()
    for raw in plist[:MAX_PROBLEMS]:
        if not isinstance(raw, Mapping):
            continue
        rec_status = str(raw.get("status") or "")
        if rec_status in ("merged", "split", "withdrawn"):
            continue
        i = len(out)
        pid = str(raw.get("id") or raw.get("number") or f"p{i + 1}")
        while pid in seen:
            pid += "_"
        seen.add(pid)
        title = _clip(_flat(raw.get("title")), 120)
        words = (
            [_clip(_flat(w), 120) for w in (raw.get("user_words") or [])[:6]]
            if isinstance(raw.get("user_words"), (list, tuple))
            else []
        )
        words = [w for w in words if w]
        where = _flat(raw.get("where") or raw.get("scope"))
        extra = " ".join(
            _flat(raw.get(k))
            for k in (
                "summary",
                "systems_mentioned",
                "who_notices",
                "trigger",
                "current_workaround",
            )
        )
        category = str(raw.get("category") or "")
        guessed = False
        if category not in taxonomy.BY_KEY or category == taxonomy.OTHER:
            g = guess_category(" ".join([title, *words]))
            category, guessed = g, g != taxonomy.OTHER
        subtype = str(raw.get("subtype") or "")[:60]
        text_f = _f(" ".join([title, *words, where, extra]))
        own = _f(" ".join([title, *words, where]))
        causes: list[_Cause] = []
        rc = raw.get("cause") if isinstance(raw.get("cause"), Mapping) else None
        rc = rc or req_causes.get(pid) or req_causes.get(str(raw.get("number") or "x"))
        if isinstance(rc, Mapping) and _flat(rc.get("text")).strip():
            ev = rc.get("evidence") or {}
            ws = tuple(
                str(w) for w in (ev.get("words") if isinstance(ev, Mapping) else None) or ()
            )[:3]
            causes.append(
                _Cause(_clip(_flat(rc.get("text")), 300), _cause_status(rc, corpus.raw), ws)
            )
        elif raw.get("person_believes_cause"):
            # a note's "person_believes_cause" is model-written: never proof of owner_said
            causes.append(
                _Cause(_clip(_flat(raw.get("person_believes_cause")), 300), PI_INFERRED, ())
            )
        res: dict[str, bool] = {}
        for key, hit in _resource_hits(text_f):
            owner = bool(corpus.raw) and any(
                _marker_re([hit]).search(_f(w)) and pf.said_by_owner([hit.split()[0]], corpus.raw)
                for w in words
            )
            res[key] = owner
        status = PI_INFERRED
        if rec_status in ("confirmed", "corrected"):
            status = CONFIRMED  # the owner said yes to this NOTE (not to any link or cause)
        elif corpus.raw and any(pf.said_by_owner([w], corpus.raw) for w in _usable_phrases(words)):
            status = OWNER_SAID
        tried = list(req_tried.get(pid, ()))
        for t in raw.get("tried") or []:
            if isinstance(t, Mapping):
                tried.append((_flat(t.get("what")), _flat(t.get("outcome"))))
        out.append(
            _Prob(
                pid,
                i,
                title,
                words,
                category,
                subtype,
                guessed,
                str(raw.get("industry") or ""),
                text_f,
                set(_stems(own)),
                res,
                causes,
                status,
                rec_status,
                raw,
                tried,
            )
        )
    return out, truncated


def _usable_phrases(words: list[str]) -> list[str]:
    """Each user word as a short phrase the owner-proof check can test (first usable token)."""
    out = []
    for w in words:
        toks = [t for t in _WORD.findall(w.casefold()) if len(t) >= pf.MIN_WORD and t not in _STOP]
        if toks:
            out.append(toks[0])
    return out


# ---------------------------------------------------------------------------------------------
# Layers
# ---------------------------------------------------------------------------------------------
def _hits(rx: re.Pattern[str], folded: str, n: int = 3) -> list[str]:
    out = []
    for m in rx.finditer(folded):
        out.append(m.group(0))
        if len(out) >= n:
            break
    return out


def _classify(p: _Prob, corpus: _Corpus) -> tuple[Layer, str, tuple[str, ...]]:
    own = _f(" ".join([p.title, *p.words]))
    if not own.strip():
        return Layer.UNVERIFIED, "no_text", ()
    if corpus.raw and p.rec_status not in ("confirmed", "corrected") and p.status == PI_INFERRED:
        cstems = {s for sent in corpus.sents for s in sent.stems}
        if not (p.stems & cstems):
            return Layer.UNVERIFIED, "not_in_owner_words", ()
    conseq = _hits(_CONSEQ, own)
    if p.subtype in lx.CONSEQUENCE_SUBTYPES:
        return Layer.BUSINESS_CONSEQUENCE, "subtype", (p.subtype,)
    if conseq:
        return Layer.BUSINESS_CONSEQUENCE, "consequence_words", tuple(conseq)
    if p.subtype in lx.OPERATIONAL_SUBTYPES or (
        p.category in lx.OPERATIONAL_CATEGORIES and not p.guessed
    ):
        return Layer.OPERATIONAL_PROBLEM, "subtype_or_category", (p.subtype or p.category,)
    sym = _hits(_SYMPTOM, own)
    if sym:
        return Layer.SYMPTOM, "symptom_words", tuple(sym)
    return Layer.IMMEDIATE_PROBLEM, "default", ()


# ---------------------------------------------------------------------------------------------
# Claims: "A because B" in the owner's own sentences
# ---------------------------------------------------------------------------------------------
@dataclass
class _Claim:
    cause_f: str
    effect_f: str
    cause_orig: str
    quote: str
    conn: str
    hedged: bool
    partial: bool
    msg: int


def _content(frag: str) -> int:
    return len(_stems(_HEDGE.sub(" ", frag)))


def _claims(c: _Corpus) -> list[_Claim]:
    out: list[_Claim] = []
    prev: _Sentence | None = None
    for s in c.sents:
        prior, prev = prev if (prev and prev.msg == s.msg) else None, s
        f = s.folded
        if "?" in f or len(out) >= MAX_CLAIMS:
            continue
        first = _WORD.findall(f[:30])[:2]
        if first and (
            _QWORD.match(first[0])
            and not (first[0] in ("kyun", "kyon") and len(first) > 1 and first[1] in ("ke", "ki"))
        ):
            continue
        m = _CONN.search(f)
        so = _SO.search(f)
        conn_text = ""
        direction = ""
        if m and (not so or m.start() <= so.start()):
            lo, hi, conn_text = m.start(), m.end(), m.group(0)
            direction = "follows" if conn_text in _FOLLOW_SET else "precedes"
        elif so:
            lo, hi, conn_text, direction = so.start(), so.end(), "so", "precedes"
        else:
            continue
        left, right = f[:lo], f[hi:]
        if _COND.search(left):
            continue
        ltoks = _WORD.findall(left)[-1:]
        rtoks = _WORD.findall(right)[:1]
        if (ltoks and ltoks[0] in _NEG) or (rtoks and rtoks[0] in _NEG):
            continue
        hedged = bool(_HEDGE.search(f))
        partial = bool(_PARTIAL.search(f))
        cause_f = effect_f = ""
        cause_o = ""
        if conn_text in _ISLIYE:
            ke = _KE.match(right.strip())
            if ke and _content(left) >= 1 and _content(ke.group(3)) >= 1:
                effect_f, cause_f = f"{left} {ke.group(1)}", ke.group(3)
        if not cause_f:
            has_left = _content(left) >= 1
            if direction == "follows":
                if has_left:
                    effect_f, cause_f = left, right
                else:
                    head, _, rest = right.partition(",")
                    if _content(rest) >= 1:
                        cause_f, effect_f = head, rest
                    elif prior is not None:
                        cause_f, effect_f = right, prior.folded
            else:
                if has_left:
                    cause_f, effect_f = left, right
                elif prior is not None:
                    cause_f, effect_f = prior.folded, right
        if _content(cause_f) < 1 or _content(effect_f) < 1:
            continue
        cause_o = _clip(cause_f if not s.orig else _slice_orig(s, cause_f), 200)
        out.append(
            _Claim(
                cause_f, effect_f, cause_o, _clip(s.orig or f), conn_text, hedged, partial, s.msg
            )
        )
    return out


def _slice_orig(s: _Sentence, frag_f: str) -> str:
    """The owner's own characters for a fragment of a sentence (fallback: the sentence)."""
    pos = s.folded.find(frag_f.strip())
    if pos < 0 or not s.orig:
        return s.orig
    # sentence folded and orig are not 1:1 after folding, so quote the whole sentence part by ratio
    return s.orig if len(s.folded) != len(s.orig) else s.orig[pos : pos + len(frag_f.strip())]


# ---------------------------------------------------------------------------------------------
# Matching a fragment to a problem
# ---------------------------------------------------------------------------------------------
def _index(probs: list[_Prob]) -> tuple[dict[str, set[int]], int]:
    idx: dict[str, set[int]] = defaultdict(set)
    for p in probs:
        for s in p.stems:
            idx[s].add(p.i)
    return idx, len(probs)


def _match(frag_f: str, idx: dict[str, set[int]], n: int) -> list[int]:
    """The one problem the fragment is about, or [] when none or when two tie."""
    score: dict[int, float] = defaultdict(float)
    for st in set(_stems(frag_f)):
        owners = idx.get(st)
        if not owners or (n >= 3 and len(owners) == n):
            continue
        for i in owners:
            score[i] += 1.0 / len(owners)
    if not score:
        return []
    top = max(score.values())
    best = [i for i, v in score.items() if v >= top - 1e-9]
    return best if len(best) == 1 else []


def _cause_keys(text_f: str) -> set[str]:
    return {k for k, rx in _CAUSE_RE.items() if rx.search(text_f)}


def _same_cause(a: _Cause, b: _Cause) -> bool:
    af, bf = _f(a.text), _f(b.text)
    if not af or not bf:
        return False
    if af == bf:
        return True
    if _cause_keys(af) & _cause_keys(bf):
        return True
    return len(set(_stems(af)) & set(_stems(bf))) >= 2


# ---------------------------------------------------------------------------------------------
# Hypotheses
# ---------------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _pack_index() -> tuple[tuple[str, str, str, str], ...]:
    """(pack key, category, subtype, phrase) from the industry packs, read-only, never raises."""
    out: list[tuple[str, str, str, str]] = []
    try:
        folder = Path(__file__).parent / "packs" / "industry"
        for path in sorted(folder.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            for pr in data.get("problems") or []:
                if isinstance(pr, Mapping) and pr.get("phrase"):
                    out.append(
                        (
                            path.stem,
                            str(pr.get("category") or ""),
                            str(pr.get("subtype") or ""),
                            str(pr["phrase"]),
                        )
                    )
    except Exception:  # noqa: BLE001
        return ()
    return tuple(out)


def _cause_keys_for(category: str, subtype: str) -> tuple[str, ...]:
    return lx.SUBTYPE_CAUSES.get(subtype) or lx.CATEGORY_CAUSES.get(category) or lx.FALLBACK_CAUSES


def _label(key: str, language: str) -> str:
    entry: Any = lx.CAUSES[key]["label"]
    return str(entry[lx.LANGUAGES.index(language)])


def _check(key: str, language: str) -> str:
    entry: Any = lx.CAUSES[key]["check"]
    return str(entry[lx.LANGUAGES.index(language)])


def _unattributed(c: _Corpus, probs: list[_Prob]) -> set[int]:
    """Sentences about none of the problems: a cause word there may be about any of them."""
    allstems: set[str] = set()
    for p in probs:
        allstems |= p.stems
    return {i for i, s in enumerate(c.sents) if not (set(s.stems) & allstems)}


def _hypotheses(
    p: _Prob, c: _Corpus, language: str, unattr: set[int] | None = None
) -> tuple[Hypothesis, ...]:
    owner_keys: set[str] = set()
    for cz in p.causes:
        if cz.status in OWNER_STATUSES:
            owner_keys |= _cause_keys(_f(cz.text))
    rel: set[int] = set(unattr or ())
    for st in p.stems:
        rel.update(c.by_stem.get(st, [])[:200])
        if len(rel) > 400:
            break
    out: list[Hypothesis] = []
    own_text = p.text_f
    for key in _cause_keys_for(p.category, p.subtype)[:MAX_HYPOTHESES]:
        if key in owner_keys:
            continue  # the owner already said it: not a guess any more
        rx = _CAUSE_RE[key]
        sup: list[Evidence] = []
        con: list[Evidence] = []
        for h in c.hits.get(key, ()):
            si, pos, neg = h
            if si not in rel:
                continue
            sent = c.sents[si]
            ev = Evidence(_clip(sent.orig or sent.folded, 100), OWNER_SAID, "owner_message")
            bucket = con if neg else sup
            if ev not in bucket:
                bucket.append(ev)
        m = rx.search(own_text)
        if m:
            sup.append(Evidence(_clip(m.group(0), 100), PI_INFERRED, "problem_record"))
        for what, outcome in p.tried:
            wf = _f(what)
            if rx.search(wf) and (_NOT_HELPED.search(_f(outcome)) or not outcome):
                con.append(Evidence(_clip(what, 100), PI_INFERRED, "tried"))
        text = _label(key, language)
        out.append(
            Hypothesis(
                key,
                text,
                lx.GUESS_PREFIX[language] + text,
                "taxonomy",
                p.subtype if p.subtype in lx.SUBTYPE_CAUSES else p.category,
                PI_INFERRED,
                _check(key, language),
                tuple(sup[:MAX_EVIDENCE]),
                tuple(con[:MAX_EVIDENCE]),
                language,
                language,
            )
        )
    order = {h.key: n for n, h in enumerate(out)}
    out.sort(key=lambda h: (bool(h.contradicts) and not h.supports, -len(h.supports), order[h.key]))
    # pack patterns: related things seen in the same industry (English phrases, labelled as such)
    n_pack = 0
    if p.category != taxonomy.OTHER:
        seen: set[str] = set()
        for pack, cat, sub, phrase in _pack_index():
            if n_pack >= MAX_PACK_HYPOTHESES:
                break
            same_pack = bool(p.industry) and pack == p.industry
            if not (
                (same_pack and cat == p.category)
                or (not p.industry and p.subtype and sub == p.subtype)
            ):
                continue
            if phrase in seen or _f(phrase) in _f(" ".join([p.title, *p.words])):
                continue
            seen.add(phrase)
            n_pack += 1
            out.append(
                Hypothesis(
                    f"pack:{pack}:{n_pack}",
                    phrase,
                    lx.PACK_PREFIX[language] + phrase,
                    "pack",
                    pack,
                    PI_INFERRED,
                    lx.PACK_CHECK[language],
                    (),
                    (),
                    language,
                    "en",
                )
            )
    return tuple(out)


def hypotheses_for(
    problem: Mapping[str, Any], facts: Mapping[str, Any] | None, language: str = "en"
) -> tuple[Hypothesis, ...]:
    """Possible causes to CHECK for one problem record. All `pi_inferred`; never raises.

    `facts` may carry `owner_messages` (the owner's own words), `tried` ([{what, outcome}]) and
    `cause` ({text, status, evidence}). A cause the owner already said is not offered again."""
    try:
        lang = _lang(language)
        facts = facts if isinstance(facts, Mapping) else {}
        corpus = _build_corpus(_messages(facts.get("owner_messages") or facts.get("owner_text")))
        rec = dict(problem) if isinstance(problem, Mapping) else {}
        if facts.get("cause") and not rec.get("cause"):
            rec["cause"] = facts["cause"]
        if facts.get("tried") and not rec.get("tried"):
            rec["tried"] = facts["tried"]
        probs, _ = _prepare([rec], corpus, None, [])
        return _hypotheses(probs[0], corpus, lang, _unattributed(corpus, probs)) if probs else ()
    except Exception:  # noqa: BLE001
        return ()


# ---------------------------------------------------------------------------------------------
# Priority (owner-stated frequency, money and count only)
# ---------------------------------------------------------------------------------------------
_FREQ_RANK = {"daily": 5, "weekly": 4, "monthly": 3, "seasonal": 2, "once": 1}
_MULT = {
    _f(k): v
    for k, v in {
        "k": 1e3,
        "thousand": 1e3,
        "hazar": 1e3,
        "hazaar": 1e3,
        "ہزار": 1e3,
        "الف": 1e3,
        "ألف": 1e3,
        "آلاف": 1e3,
        "lakh": 1e5,
        "lakhs": 1e5,
        "lac": 1e5,
        "لاکھ": 1e5,
        "crore": 1e7,
        "کروڑ": 1e7,
        "million": 1e6,
        "مليون": 1e6,
    }.items()
}
_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s*(\w+)?")
_PERIOD = {
    "month": _marker_re(
        [
            "month",
            "monthly",
            "mahina",
            "maheena",
            "mahine",
            "mahinay",
            "ماہ",
            "مہینہ",
            "مہینے",
            "شهر",
            "شهريا",
        ]
    ),
    "week": _marker_re(["week", "weekly", "hafta", "hafte", "ہفتہ", "ہفتے", "اسبوع", "اسبوعيا"]),
    "day": _marker_re(
        ["day", "daily", "din", "roz", "rozana", "دن", "روز", "روزانہ", "يوم", "يوميا"]
    ),
    "year": _marker_re(["year", "yearly", "saal", "سال", "سنة", "سنويا"]),
}
_CURRENCY = {
    _f(w)
    for w in (
        "rs pkr usd aed sar rupay rupee rupees rupye dollar dollars dirham riyal "
        "روپے روپیہ روپیے ریال درہم دولار ريال درهم"
    ).split()
}


def _figures(text: str, owner_f: str | None) -> list[tuple[float, str]]:
    out = []
    for m in _NUM.finditer(_f(text)):
        raw = m.group(1).replace(",", "")
        try:
            val = float(raw + ("." + m.group(2) if m.group(2) else ""))
        except ValueError:
            continue
        word = m.group(3) or ""
        if word in _MULT:
            val *= _MULT[word]
            word = ""
        if owner_f is not None and raw not in owner_f.replace(",", ""):
            continue  # a figure the owner never wrote is not theirs
        out.append((val, word))
    return out


def _dims(raw: Mapping[str, Any], owner_f: str | None) -> dict[str, Any]:
    d: dict[str, Any] = {}
    freq = raw.get("frequency")
    norm = ""
    if isinstance(freq, Mapping):
        norm = str(freq.get("normalised") or "")
    elif isinstance(freq, str):
        norm = freq
    if norm in _FREQ_RANK:
        d["frequency"] = _FREQ_RANK[norm]
    impact = raw.get("impact")
    imp = impact if isinstance(impact, Mapping) else {}
    money = imp.get("money_value")
    mtext = (
        _flat(imp.get("money_text")) if imp else (_flat(impact) if isinstance(impact, str) else "")
    )
    amount: float | None = None
    if isinstance(money, (int, float)) and not isinstance(money, bool) and money > 0:
        amount = float(money)
    else:
        figs = _figures(mtext, owner_f)
        if figs:
            amount = figs[0][0]
    if amount is not None:
        per = next((k for k, rx in _PERIOD.items() if rx.search(_f(mtext + " " + _flat(freq)))), "")
        d["money"] = (amount, per)
    scope = raw.get("scope")
    of_total = (
        _flat(scope.get("of_total")) if isinstance(scope, Mapping) else _flat(raw.get("of_total"))
    )
    for src in (
        of_total,
        *(
            _flat(w)
            for w in (raw.get("user_words") or [])[:4]
            if isinstance(raw.get("user_words"), (list, tuple))
        ),
    ):
        for val, word in _figures(src, owner_f):
            if word and word not in _CURRENCY and word not in _STOP:
                d["count"] = (val, _stem(word))
                break
        if "count" in d:
            break
    return d


def _compare(a: dict[str, Any], b: dict[str, Any]) -> tuple[str, str]:
    """('gt'|'lt'|'eq'|'inc', why). Only dimensions both stated and comparable count."""
    gt = lt = common = 0
    why: list[str] = []
    for k in ("frequency", "money", "count"):
        if k not in a or k not in b:
            continue
        x, y = a[k], b[k]
        if k == "money":
            if x[1] != y[1]:
                continue
            x, y = x[0], y[0]
        elif k == "count":
            if x[1] != y[1]:
                continue
            x, y = x[0], y[0]
        common += 1
        if x > y:
            gt += 1
            why.append(k)
        elif x < y:
            lt += 1
    if not common:
        return "inc", "no_common_stated_dimension"
    if gt and lt:
        return "inc", "conflicting_dimensions"
    if gt:
        return "gt", ",".join(why)
    if lt:
        return "lt", ""
    return "eq", "equal_on_common_dimensions"


def priority_order(problems: Any, owner_messages: Any = None) -> PriorityResult:
    """Order problems by what the owner stated (frequency, money with its period, a count with its
    unit). A problem is placed above another only when it is at least as high on every dimension
    both stated and higher on one. Everything else is level-equal or in `cannot_rank`."""
    try:
        msgs = _messages(owner_messages)
        owner_f = _f("\n".join(msgs)) if msgs else None
        plist = [
            p
            for p in (
                problems
                if isinstance(problems, Iterable) and not isinstance(problems, (str, Mapping))
                else []
            )
            if isinstance(p, Mapping)
        ][:MAX_PROBLEMS]
        ids = [str(p.get("id") or p.get("number") or f"p{i + 1}") for i, p in enumerate(plist)]
        dims = [_dims(p, owner_f) for p in plist]
        stated = [i for i, d in enumerate(dims) if d]
        cannot = tuple(ids[i] for i in range(len(plist)) if not dims[i])
        above: dict[int, set[int]] = defaultdict(set)  # i -> those that outrank i
        pairs: list[tuple[str, str, str]] = []
        for x in stated:
            for y in stated:
                if x < y:
                    r, why = _compare(dims[x], dims[y])
                    if r == "gt":
                        above[y].add(x)
                        pairs.append((ids[x], ids[y], why))
                    elif r == "lt":
                        above[x].add(y)
                        pairs.append((ids[y], ids[x], why))
        level: dict[int, int] = {}

        def lv(i: int, depth: int = 0) -> int:
            if i in level:
                return level[i]
            level[i] = (
                1 + max((lv(j, depth + 1) for j in above[i]), default=0) if depth < 200 else 1
            )
            return level[i]

        for i in stated:
            lv(i)
        groups: dict[int, list[str]] = defaultdict(list)
        for i in stated:
            groups[level[i]].append(ids[i])
        levels = tuple(tuple(groups[k]) for k in sorted(groups))
        ranked = tuple(
            Ranked(ids[i], level[i], tuple(sorted(dims[i])))
            for i in sorted(stated, key=lambda j: (level[j], j))
        )
        complete = not cannot and all(len(g) == 1 for g in levels)
        note = (
            "ordered from the owner's stated figures only"
            if complete
            else "cannot rank yet: some problems are tied, not comparable or have no stated figure"
        )
        return PriorityResult(levels, ranked, cannot, tuple(pairs), complete, note)
    except Exception:  # noqa: BLE001
        return PriorityResult((), (), (), (), False, "cannot rank yet: input not readable")


# ---------------------------------------------------------------------------------------------
# The graph
# ---------------------------------------------------------------------------------------------
def build_problem_graph(
    problems: Any,
    owner_messages: Any = None,
    requirements: Any = None,
    language: str = "en",
    *,
    confirmed_links: Iterable[tuple[str, str]] | None = None,
) -> ProblemGraph:
    """The layered, evidence-only problem graph. Never raises (an unreadable input gives an empty
    graph with a warning). `confirmed_links` are (id, id) pairs the owner said yes to."""
    lang = _lang(language)
    try:
        return _build(problems, owner_messages, requirements, lang, confirmed_links)
    except Exception as exc:  # noqa: BLE001
        return ProblemGraph(language=lang, warnings=(f"unreadable_input:{type(exc).__name__}",))


def _status_edge(statuses: Sequence[str]) -> str:
    if any(s == PI_INFERRED for s in statuses):
        return PI_INFERRED
    return CONFIRMED if all(s == CONFIRMED for s in statuses) else OWNER_SAID


def _build(
    problems: Any, owner_messages: Any, requirements: Any, lang: str, confirmed_links: Any
) -> ProblemGraph:
    warnings: list[str] = []
    msgs = _messages(owner_messages)
    corpus = _build_corpus(msgs)
    probs, truncated = _prepare(problems, corpus, requirements, warnings)
    if not probs:
        return ProblemGraph(language=lang, warnings=tuple(warnings), truncated=truncated)
    idx, n = _index(probs)
    statements: list[Statement] = []
    edges: dict[tuple[str, str, str], Edge] = {}

    def sid() -> str:
        return f"s{len(statements) + 1}"

    def add_edge(
        kind: EdgeKind,
        a: _Prob,
        b: _Prob,
        status: str,
        strength: str,
        evidence: Sequence[str],
        hedged: bool = False,
    ) -> None:
        directed = kind is EdgeKind.OWNER_STATED
        key = (kind.value, a.id, b.id) if directed or a.i < b.i else (kind.value, b.id, a.id)
        if directed and (kind.value, b.id, a.id) in edges:
            return
        if key in edges:
            return
        if sum(1 for k in edges if k[0] == kind.value) >= MAX_EDGES_PER_KIND:
            return
        hypo = status == PI_INFERRED or kind in (EdgeKind.SHARED_RESOURCE, EdgeKind.CATEGORY_FAMILY)
        edges[key] = Edge(
            f"e{len(edges) + 1}",
            kind,
            key[1],
            key[2],
            directed,
            status,
            hypo,
            status == CONFIRMED,
            strength,
            STRENGTH_RANK[strength],
            tuple(_clip(e, 200) for e in evidence[:4]),
            hedged,
        )

    # layers of the problems themselves
    nodes: list[ProblemNode] = []
    for p in probs:
        layer, reason, words = _classify(p, corpus)
        nodes.append(
            ProblemNode(
                p.id, p.title, layer, p.status, words, reason, p.category, p.subtype, p.guessed
            )
        )

    # explicit statements in the owner's own words
    for cl in _claims(corpus):
        cs = _match(cl.cause_f, idx, n)
        es = _match(cl.effect_f, idx, n)
        status = OWNER_SAID
        if es and cs and es[0] != cs[0]:
            add_edge(
                EdgeKind.OWNER_STATED,
                probs[cs[0]],
                probs[es[0]],
                status,
                "medium" if cl.hedged else "strong",
                [cl.quote, f"connective: {cl.conn}"],
                cl.hedged,
            )
        elif es and not cs:
            layer = Layer.CONTRIBUTING_FACTOR if cl.partial else Layer.ROOT_CAUSE_CANDIDATE
            words = tuple(
                _clip(w, 60)
                for w in _WORD.findall(cl.cause_f)
                if w not in _STOP and len(w) >= pf.MIN_WORD
            )[:3]
            probs[es[0]].causes.append(
                _Cause(cl.cause_orig, OWNER_SAID, words, cl.hedged, cl.partial, "claim", cl.quote)
            )
        elif cs and not es and _CONSEQ.search(cl.effect_f):
            statements.append(
                Statement(
                    sid(),
                    probs[cs[0]].id,
                    Layer.BUSINESS_CONSEQUENCE,
                    _clip(cl.quote),
                    OWNER_SAID,
                    tuple(_hits(_CONSEQ, cl.effect_f)),
                    "owner_stated_consequence",
                    cl.hedged,
                    cl.quote,
                )
            )

    # cause statements (stored and claimed) and consequence statements from the record
    for p in probs:
        for cz in p.causes:
            if cz.status in OWNER_STATUSES and cz.source == "record":
                for o in probs:  # the stored cause names another problem: the owner linked them
                    if o.i != p.i:
                        m = _match(_f(cz.text), idx, n)
                        if m and m[0] == o.i:
                            add_edge(
                                EdgeKind.OWNER_STATED,
                                o,
                                p,
                                cz.status,
                                "strong",
                                [cz.text, "stored cause"],
                            )
                        break
            layer = Layer.CONTRIBUTING_FACTOR if cz.partial else Layer.ROOT_CAUSE_CANDIDATE
            statements.append(
                Statement(
                    sid(),
                    p.id,
                    layer,
                    cz.text,
                    cz.status,
                    cz.words,
                    "cause_" + cz.source,
                    cz.hedged,
                    cz.quote,
                )
            )
        impact = p.raw.get("impact")
        itext = _flat(impact.get("money_text")) if isinstance(impact, Mapping) else _flat(impact)
        if itext.strip():
            statements.append(
                Statement(
                    sid(),
                    p.id,
                    Layer.BUSINESS_CONSEQUENCE,
                    _clip(itext),
                    PI_INFERRED
                    if not corpus.raw
                    else (
                        OWNER_SAID
                        if pf.said_by_owner(_usable_phrases([itext]), corpus.raw)
                        else PI_INFERRED
                    ),
                    (),
                    "impact_field",
                )
            )

    # shared stated cause
    by_key: dict[str, list[tuple[_Prob, _Cause]]] = defaultdict(list)
    for p in probs:
        for cz in p.causes:
            for k in _cause_keys(_f(cz.text)) or {
                "~" + " ".join(sorted(set(_stems(_f(cz.text))))[:2])
            }:
                by_key[k].append((p, cz))
    pairs_seen: set[tuple[int, int]] = set()
    cause_pairs = []
    for members in by_key.values():
        for ai in range(len(members)):
            for bi in range(ai + 1, len(members)):
                a, ca = members[ai]
                b, cb = members[bi]
                if (
                    a.i != b.i
                    and (min(a.i, b.i), max(a.i, b.i)) not in pairs_seen
                    and _same_cause(ca, cb)
                ):
                    pairs_seen.add((min(a.i, b.i), max(a.i, b.i)))
                    cause_pairs.append((a, ca, b, cb))
                if len(cause_pairs) >= MAX_EDGES_PER_KIND:
                    break
    for a, ca, b, cb in cause_pairs:
        st = _status_edge([ca.status, cb.status])
        strong = st != PI_INFERRED and not (ca.hedged or cb.hedged)
        add_edge(
            EdgeKind.SHARED_CAUSE,
            a,
            b,
            st,
            "strong" if strong else ("medium" if st != PI_INFERRED else "weak"),
            [ca.text, cb.text],
            ca.hedged or cb.hedged,
        )

    # shared resource or process
    res_members: dict[str, list[_Prob]] = defaultdict(list)
    for p in probs:
        for k in p.resources:
            res_members[k].append(p)
    for k, rmembers in res_members.items():
        for ai in range(len(rmembers)):
            for bi in range(ai + 1, len(rmembers)):
                a, b = rmembers[ai], rmembers[bi]
                both = a.resources[k] and b.resources[k]
                add_edge(
                    EdgeKind.SHARED_RESOURCE,
                    a,
                    b,
                    OWNER_SAID if both else PI_INFERRED,
                    "medium" if both else "weak",
                    [f"both mention: {k}"],
                )
                if (
                    sum(1 for e in edges if e[0] == EdgeKind.SHARED_RESOURCE.value)
                    >= MAX_EDGES_PER_KIND
                ):
                    break

    # category family (weak): only between problems with no stronger edge, never from a guess
    linked = {frozenset((e.from_id, e.to_id)) for e in edges.values()}
    stored = [
        p
        for p in probs
        if not p.guessed and p.category != taxonomy.OTHER and p.category in taxonomy.BY_KEY
    ]
    for ai in range(len(stored)):
        for bi in range(ai + 1, len(stored)):
            a, b = stored[ai], stored[bi]
            if frozenset((a.id, b.id)) in linked:
                continue
            fa, fb = lx.FAMILY_OF.get(a.category), lx.FAMILY_OF.get(b.category)
            if a.category == b.category:
                add_edge(
                    EdgeKind.CATEGORY_FAMILY,
                    a,
                    b,
                    PI_INFERRED,
                    "weak",
                    [f"same category: {a.category}"],
                )
            elif fa and fa == fb:
                add_edge(
                    EdgeKind.CATEGORY_FAMILY,
                    a,
                    b,
                    PI_INFERRED,
                    "weak",
                    [f"same family {fa}: {a.category} and {b.category}"],
                )
            if (
                sum(1 for e in edges if e[0] == EdgeKind.CATEGORY_FAMILY.value)
                >= MAX_EDGES_PER_KIND
            ):
                break

    # the owner said yes to a link
    yes = {frozenset((str(a), str(b))) for a, b in (confirmed_links or ()) if a is not None}
    final: list[Edge] = []
    for e in edges.values():
        if frozenset((e.from_id, e.to_id)) in yes:
            e = dataclasses.replace(e, evidence_status=CONFIRMED, confirmed=True, hypothesis=False)
        final.append(e)

    unattr = _unattributed(corpus, probs)
    hyps = tuple((p.id, _hypotheses(p, corpus, lang, unattr)) for p in probs)
    graph = ProblemGraph(
        lang,
        tuple(nodes),
        tuple(statements),
        tuple(final),
        hyps,
        (),
        priority_order([p.raw for p in probs], msgs),
        tuple(warnings),
        truncated,
    )
    return dataclasses.replace(
        graph, learn_first=learn_first(graph, _statements_by_problem=statements)
    )


# ---------------------------------------------------------------------------------------------
# Coverage and learn-first
# ---------------------------------------------------------------------------------------------
def coverage(
    option_addresses: Iterable[Any], graph: ProblemGraph, *, include_weak: bool = False
) -> Coverage:
    """Problems an option covers directly, and those it MAY reach through a shared or stated
    cause (a hypothesis, never a promise). Never raises."""
    try:
        known = {n.id for n in graph.problems}
        asked = list(dict.fromkeys(str(a) for a in (option_addresses or ()) if a is not None))[
            :MAX_PROBLEMS
        ]
        direct = tuple(a for a in asked if a in known)
        unknown = tuple(a for a in asked if a not in known)
        via: list[CoveredVia] = []
        seen = set(direct)
        kinds = {EdgeKind.SHARED_CAUSE.value, EdgeKind.OWNER_STATED.value}
        if include_weak:
            kinds |= {EdgeKind.SHARED_RESOURCE.value}
        for e in sorted(graph.edges, key=lambda x: (-x.strength_rank, x.id)):
            if e.kind.value not in kinds:
                continue
            for a, b in ((e.from_id, e.to_id), (e.to_id, e.from_id)):
                if e.directed and a != e.from_id:
                    continue  # fixing the effect does not address the cause
                if a in direct and b not in seen:
                    seen.add(b)
                    via.append(CoveredVia(b, a, e.kind.value, e.evidence, True, e.strength))
        covered = seen
        return Coverage(
            direct,
            tuple(via),
            unknown,
            tuple(n.id for n in graph.problems if n.id not in covered),
            "problems reached through a shared cause are possibilities to check, "
            "not promised results",
        )
    except Exception:  # noqa: BLE001
        return Coverage((), (), (), (), "unreadable input")


def learn_first(
    graph: ProblemGraph, *, _statements_by_problem: Sequence[Statement] | None = None
) -> tuple[LearnItem, ...]:
    """Unconfirmed causes ranked by how many problems each would explain (a count, no
    probability). A cause the owner said but did not confirm is listed as `owner_said` (ask to
    confirm); a pi guess as `pi_inferred` (ask to check). A problem where the guess is contradicted
    is not counted but listed in `ruled_against`."""
    try:
        explains: dict[str, set[str]] = defaultdict(set)
        sup: dict[str, int] = defaultdict(int)
        against: dict[str, set[str]] = defaultdict(set)
        text: dict[str, str] = {}
        check: dict[str, str] = {}
        status: dict[str, str] = {}
        lang = graph.language if graph.language in lx.LANGUAGES else "en"
        for pid, hs in graph.hypotheses:
            for h in hs:
                if h.source != "taxonomy":
                    continue
                if h.contradicts and not h.supports:
                    against[h.key].add(pid)
                    text.setdefault(h.key, h.text)
                    check.setdefault(h.key, h.what_to_check)
                    status.setdefault(h.key, PI_INFERRED)
                    continue
                explains[h.key].add(pid)
                sup[h.key] += len(h.supports)
                text.setdefault(h.key, h.text)
                check.setdefault(h.key, h.what_to_check)
                status.setdefault(h.key, PI_INFERRED)
        stmts = _statements_by_problem if _statements_by_problem is not None else graph.statements
        for s in stmts:
            if (
                s.layer not in (Layer.ROOT_CAUSE_CANDIDATE, Layer.CONTRIBUTING_FACTOR)
                or s.status == CONFIRMED
                or not s.problem_id
            ):
                continue
            keys = _cause_keys(_f(s.text))
            key = (
                sorted(keys)[0]
                if keys
                else "owner:" + " ".join(sorted(set(_stems(_f(s.text))))[:3])
            )
            explains[key].add(s.problem_id)
            if s.status == OWNER_SAID:
                status[key] = OWNER_SAID
            else:
                status.setdefault(key, PI_INFERRED)
            sup[key] += 1
            text.setdefault(key, _label(key, lang) if key in lx.CAUSES else s.text)
            if key in lx.CAUSES:
                check.setdefault(key, _check(key, lang))
            else:
                check.setdefault(key, lx.PACK_CHECK[lang])
        items = [(k, sorted(v)) for k, v in explains.items() if v]
        items.sort(key=lambda kv: (-len(kv[1]), -sup[kv[0]], kv[0]))
        out: list[LearnItem] = []
        for k, ps in items:
            tied = tuple(
                o for o, ops in items if o != k and len(ops) == len(ps) and sup[o] == sup[k]
            )
            out.append(
                LearnItem(
                    k,
                    text[k],
                    status[k],
                    tuple(ps),
                    len(ps),
                    sup[k],
                    check.get(k, ""),
                    tied,
                    tuple(sorted(against.get(k, ()))),
                )
            )
        return tuple(out)
    except Exception:  # noqa: BLE001
        return ()
