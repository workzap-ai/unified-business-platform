"""PS-5: turn the gate's unknown options into ONE useful question at a time. Pure: no database,
no model call, no score, no thresholds of its own for the gate.

The L2-1 gate (`option_gate.gate_options`) never lets an unknown or unenforced limit pass. This
module
does not change that and never calls the gate with other settings. It only

1. explains each unknown option (`explain_unknowns`): the typed reason, whether the owner can fix
it,
   and which missing fact would;
2. ranks the missing facts by how many unknown decisions each would resolve
(`rank_missing_information`);
3. picks one owner-answerable question, worded from fixed linted templates (`choose_question`,
   or `plan_resolution` for the whole picture);
4. reads the owner's answer conservatively into an UPDATE PROPOSAL (`apply_answer`) and lists the
   options the real gate must check again. The proposal never marks anything satisfied: the gate
   decides on re-check, with the owner's limit text in the same form it already reads.

Why most unknowns are not questions: with no limit stored a topic is `ok` (nothing to break), so an
unknown always comes from (a) a stored limit the gate cannot read (vague, no figure, no number of
people), (b) an option the gate cannot read (script, no cost figure, too long) or (c) a verb or
place
the gate does not enforce. Only (a) is something the owner can fix by answering. (b) and (c) are
reported as `redraft_option`, `unenforced` or `unreadable`: the flow says what is unknown and
offers to
learn first. The owner is never asked to price an option.

Uncertainty is kept: "maybe", "I don't know", "dekhte hain", a hedge before a figure, two figures
joined by "or", a date the gate cannot count, or a limit the gate still could not read after the
owner's own words: all give `still_unknown` with a typed reason. A key is asked once; asked again
(reworded with "a rough answer is fine") only after one non-answer; never a third time.

Never raises. Inputs are capped (`MAX_OPTIONS`, `MAX_OPTION_CHARS`, `MAX_MESSAGES`,
`MAX_MESSAGE_CHARS`, `MAX_ANSWER_CHARS`); every loop is linear in the capped input.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.modules.pi import constraint_check as cc
from app.modules.pi import figure_correction as fc
from app.modules.pi import unknown_resolution_lexicon as lx
from app.modules.pi.option_gate import GateResult
from app.modules.pi.requirements_types import Requirements, as_requirements

MAX_OPTIONS = 500
MAX_OPTION_CHARS = 3000
MAX_MESSAGES = 100
MAX_MESSAGE_CHARS = 2000
MAX_ANSWER_CHARS = 2000
MAX_WHY = 3
MAX_WHY_CHARS = 90
MAX_SLOT_CHARS = 40
MAX_PROBLEM_TARGETS = 8

_SURROGATES = re.compile("[\ud800-\udfff]")
_SPACED_NUMBERS = re.compile(r"\d+(?: \d+){2,}")
_SPACE = re.compile(r"\s+")


# --------------------------------------------------------------------------------- vocabulary


class Code(StrEnum):
    """Why one option is unknown, as a typed code (the gate's own words are kept in `reason`)."""

    BUDGET_NO_FIGURE = "budget_no_figure"
    BUDGET_FLOOR_ONLY = "budget_floor_only"
    STAFF_LIMIT_UNREADABLE = "staff_limit_unreadable"
    DEADLINE_UNREADABLE = "deadline_unreadable"
    CURRENCY_MISMATCH = "currency_mismatch"
    PERIOD_MISMATCH = "period_mismatch"
    FIGURE_UNATTRIBUTED = "figure_unattributed"
    LIMIT_VAGUE = "limit_vague"
    VERB_UNENFORCED = "verb_unenforced"
    GENERIC_OBJECT = "generic_object"
    SHARED_PART = "shared_part"
    PLACE_UNKNOWN = "place_unknown"
    OPTION_EXPANDS = "option_expands"
    SIZE_UNIT_UNKNOWN = "size_unit_unknown"
    RENT_MAY_COST = "rent_may_cost"
    OUTCOME_UNAVOIDED = "outcome_unavoided"
    TRIED_UNCLEAR = "tried_unclear"
    TRIED_NO_WORDS = "tried_no_words"
    TRIED_SCRIPT = "tried_script"
    TRIED_OVERLAP = "tried_overlap"
    OPTION_SCRIPT = "option_script"
    OPTION_TOO_LONG = "option_too_long"
    OPTION_EMPTY = "option_empty"
    OPTION_NOT_TEXT = "option_not_text"
    OPTION_NO_COST = "option_no_cost"
    OPTION_NO_COUNT = "option_no_count"
    OPTION_NO_TIMEFRAME = "option_no_timeframe"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    SPACED_OUT = "spaced_out"
    COLUMNS_UNAVAILABLE = "columns_unavailable"
    REQUIREMENTS_UNREADABLE = "requirements_unreadable"
    NO_LIMIT_FOR_TOPIC = "no_limit_for_topic"
    UNRECOGNISED = "unrecognised"


class Resolution(StrEnum):
    ASK_OWNER = "ask_owner"  # one owner answer can fix it
    REDRAFT_OPTION = (
        "redraft_option"  # the option lacks a figure or a count: a new draft, not a question
    )
    UNENFORCED = "unenforced"  # the gate does not enforce this verb or place
    UNREADABLE = "unreadable"  # script, length, empty, database: nothing to ask


# reason text (substring of the gate's verdict reason) -> code; first match wins, most specific
# first
_REASON_CODES: tuple[tuple[str, Code], ...] = (
    ("the budget states only a minimum", Code.BUDGET_FLOOR_ONLY),
    ("no figure in the budget text", Code.BUDGET_NO_FIGURE),
    ("staff limit could not be read", Code.STAFF_LIMIT_UNREADABLE),
    ("the deadline is not a duration", Code.DEADLINE_UNREADABLE),
    ("in another currency", Code.CURRENCY_MISMATCH),
    ("covers another period", Code.PERIOD_MISMATCH),
    ("could not be attributed", Code.FIGURE_UNATTRIBUTED),
    ("the stated limit could not be read", Code.LIMIT_VAGUE),
    ("limit's verb is not known", Code.VERB_UNENFORCED),
    ("limit's verb is not one", Code.VERB_UNENFORCED),
    ("names only a generic object", Code.GENERIC_OBJECT),
    ("shares only part of", Code.SHARED_PART),
    ("names a place this check does not know", Code.PLACE_UNKNOWN),
    ("expands without naming where", Code.OPTION_EXPANDS),
    ("needs space and states no size", Code.SIZE_UNIT_UNKNOWN),
    ("renting may also cost", Code.RENT_MAY_COST),
    ("with no sign that it is avoided", Code.OUTCOME_UNAVOIDED),
    ("how it went is not clear", Code.TRIED_UNCLEAR),
    ("has no words this check can compare", Code.TRIED_NO_WORDS),
    ("a thing the owner tried is not in a script", Code.TRIED_SCRIPT),
    ("overlaps with something that failed", Code.TRIED_OVERLAP),
    ("is not in a script this check can read", Code.OPTION_SCRIPT),
    ("too long to be read", Code.OPTION_TOO_LONG),
    ("the option text is empty", Code.OPTION_EMPTY),
    ("the option is not text", Code.OPTION_NOT_TEXT),
    ("states no cost figure", Code.OPTION_NO_COST),
    ("adds people and names no count", Code.OPTION_NO_COUNT),
    ("count cannot be read", Code.OPTION_NO_COUNT),
    ("states no timeframe", Code.OPTION_NO_TIMEFRAME),
    ("longer than the deadline", Code.DEADLINE_EXCEEDED),
    ("spaced out letter by letter", Code.SPACED_OUT),
    ("could not be read from the database", Code.COLUMNS_UNAVAILABLE),
    ("not in a form this check reads", Code.REQUIREMENTS_UNREADABLE),
    ("could not be read", Code.REQUIREMENTS_UNREADABLE),
)

# code -> (resolution, fact key that would resolve it)
_CODE_FACT: dict[Code, tuple[Resolution, str | None]] = {
    Code.BUDGET_NO_FIGURE: (Resolution.ASK_OWNER, "budget_ceiling"),
    Code.BUDGET_FLOOR_ONLY: (Resolution.ASK_OWNER, "budget_ceiling"),
    Code.STAFF_LIMIT_UNREADABLE: (Resolution.ASK_OWNER, "staff_headcount"),
    Code.DEADLINE_UNREADABLE: (Resolution.ASK_OWNER, "deadline_duration"),
    Code.CURRENCY_MISMATCH: (Resolution.ASK_OWNER, "budget_currency_period"),
    Code.PERIOD_MISMATCH: (Resolution.ASK_OWNER, "budget_currency_period"),
    Code.FIGURE_UNATTRIBUTED: (Resolution.REDRAFT_OPTION, None),
    Code.LIMIT_VAGUE: (Resolution.ASK_OWNER, "cannot_change_detail"),
    Code.VERB_UNENFORCED: (Resolution.ASK_OWNER, "cannot_change_detail"),
    Code.GENERIC_OBJECT: (Resolution.ASK_OWNER, "cannot_change_detail"),
    Code.SHARED_PART: (Resolution.ASK_OWNER, "cannot_change_detail"),
    Code.PLACE_UNKNOWN: (Resolution.UNENFORCED, None),
    Code.OPTION_EXPANDS: (Resolution.REDRAFT_OPTION, None),
    Code.SIZE_UNIT_UNKNOWN: (Resolution.REDRAFT_OPTION, None),
    Code.RENT_MAY_COST: (Resolution.REDRAFT_OPTION, None),
    Code.OUTCOME_UNAVOIDED: (Resolution.REDRAFT_OPTION, None),
    Code.TRIED_UNCLEAR: (Resolution.ASK_OWNER, "tried_outcome"),
    Code.TRIED_NO_WORDS: (Resolution.ASK_OWNER, "tried_detail"),
    Code.TRIED_SCRIPT: (Resolution.UNREADABLE, None),
    Code.TRIED_OVERLAP: (Resolution.REDRAFT_OPTION, None),
    Code.OPTION_SCRIPT: (Resolution.UNREADABLE, None),
    Code.OPTION_TOO_LONG: (Resolution.UNREADABLE, None),
    Code.OPTION_EMPTY: (Resolution.UNREADABLE, None),
    Code.OPTION_NOT_TEXT: (Resolution.UNREADABLE, None),
    Code.OPTION_NO_COST: (Resolution.REDRAFT_OPTION, None),
    Code.OPTION_NO_COUNT: (Resolution.REDRAFT_OPTION, None),
    Code.OPTION_NO_TIMEFRAME: (Resolution.REDRAFT_OPTION, None),
    Code.DEADLINE_EXCEEDED: (Resolution.REDRAFT_OPTION, None),
    Code.SPACED_OUT: (Resolution.UNREADABLE, None),
    Code.COLUMNS_UNAVAILABLE: (Resolution.UNREADABLE, None),
    Code.REQUIREMENTS_UNREADABLE: (Resolution.UNREADABLE, None),
    Code.NO_LIMIT_FOR_TOPIC: (Resolution.UNREADABLE, None),
    Code.UNRECOGNISED: (Resolution.UNREADABLE, None),
}


@dataclass(frozen=True, slots=True)
class FactSpec:
    key: str
    label: str  # the missing fact, in English, for logs and the flow lead
    field: str  # the requirement field an answer fills
    rule: str  # the gate rule it belongs to ("" when none)
    priority: int  # tie-break: lower first


FACTS: dict[str, FactSpec] = {
    f.key: f
    for f in (
        FactSpec("budget_ceiling", "budget ceiling", "budget", cc.RULE_BUDGET, 0),
        FactSpec("staff_headcount", "staff headcount", "staff", cc.RULE_STAFF, 1),
        FactSpec("deadline_duration", "deadline", "deadline", cc.RULE_DEADLINE, 2),
        FactSpec(
            "cannot_change_detail",
            "what cannot be changed",
            "cannot_change",
            cc.RULE_CANNOT_CHANGE,
            3,
        ),
        FactSpec("tried_outcome", "how what was tried went", "tried", cc.RULE_TRIED, 4),
        FactSpec(
            "budget_currency_period", "budget currency and period", "budget", cc.RULE_BUDGET, 5
        ),
        FactSpec("tried_detail", "what was tried", "tried", cc.RULE_TRIED, 6),
        FactSpec("place_allowed", "places the owner can work in", "cannot_change", "", 7),
        FactSpec("tools_resources", "tools and resources available", "", "", 8),
        FactSpec("expected_outcome", "expected outcome", "expected_outcome", "", 9),
    )
}


# ----------------------------------------------------------------------------- small helpers


def _text(value: Any) -> str:
    """Text without lone surrogates; anything that is not text is empty."""
    return _SURROGATES.sub("", value) if isinstance(value, str) else ""


def _clip(value: str, size: int) -> str:
    value = _SPACE.sub(" ", value).strip()
    return value if len(value) <= size else value[: size - 1].rstrip() + "…"


def _lang(language: Any) -> str:
    """One of en, roman_ur, ur, ar. Anything else (Hindi, None, junk) is English."""
    return language if isinstance(language, str) and language in lx.LANGUAGES else "en"


def _norm(text: str) -> str:
    return cc.norm(fc.expand(_text(text)))


def _clean_messages(messages: Any) -> list[str]:
    if isinstance(messages, str):
        messages = [messages]
    if not isinstance(messages, Iterable) or isinstance(messages, (bytes, Mapping)):
        return []
    out: list[str] = []
    for item in messages:
        if len(out) >= MAX_MESSAGES:
            break
        t = _text(item)
        if t.strip():
            out.append(t[:MAX_MESSAGE_CHARS])
    return out


def _has_any(text: str, pattern: str, others: Sequence[str]) -> bool:
    return bool(re.search(pattern, text)) or any(o in text for o in others)


_CUE_REGEX = re.compile(lx.NON_ANSWER_CUES)
_OTHER_REGEX = re.compile(
    "|".join(
        rf"(?<!\w){re.escape(cc.norm(p))}(?!\w)"
        for p in sorted(lx.NON_ANSWER_OTHER, key=len, reverse=True)
    )
)
_HEDGE_REGEX = re.compile(lx.HEDGE_CUES)
_HEDGE_OTHER_REGEX = re.compile(
    "|".join(rf"(?<!\w){re.escape(cc.norm(p))}(?!\w)" for p in lx.HEDGE_OTHER)
)


def is_non_answer(text: Any) -> bool:
    """True when the reply says nothing that could be read as a value: empty, a bare yes or no,
    'maybe', 'I do not know', 'dekhte hain', 'let me think'. A reply with anything else in it is
    not one."""
    try:
        t = _norm(_text(text)[:MAX_ANSWER_CHARS])
        t = "".join(" " if ch != "'" and unicodedata.category(ch)[0] in "PS" else ch for ch in t)
        t = _OTHER_REGEX.sub(" ", _CUE_REGEX.sub(" ", t))
        return not _SPACE.sub("", t)
    except Exception:  # noqa: BLE001 - never raises
        return True


def _hedged(text: str) -> bool:
    t = _norm(text)
    return bool(_HEDGE_REGEX.search(t) or _HEDGE_OTHER_REGEX.search(t))


def _either_or(text: str) -> bool:
    """Two figures joined by "or", or three or more figures separated by spaces (the gate's reader
    would glue "2 3 4" into 234): the owner has not given one value."""
    expanded = fc.expand(_text(text))
    return bool(lx.EITHER_OR.search(_norm(text)) or _SPACED_NUMBERS.search(expanded))


# ----------------------------------------------------------------------- 1. explain unknowns


@dataclass(frozen=True, slots=True)
class UnknownExplanation:
    index: int  # position of the option in `options` (or among the verdicts when not found)
    option: str
    rule: str
    code: Code
    reason: str  # the gate's own words
    evidence: tuple[str, ...]
    resolution: Resolution
    fact: str | None  # the missing-fact key that one owner answer would fill, else None
    problems: tuple[int, ...]  # problem numbers whose stored data is behind it

    @property
    def owner_answerable(self) -> bool:
        return self.resolution is Resolution.ASK_OWNER and self.fact is not None


def classify_reason(reason: Any, rule: Any = "") -> Code:
    """The typed code of one verdict reason. Unrecognised text is `UNRECOGNISED`, never a guess."""
    r = _text(reason).lower()
    for needle, code in _REASON_CODES:
        if needle in r:
            return code
    return Code.UNRECOGNISED


def _is_verdict(v: Any) -> bool:
    return isinstance(v, cc.Verdict)


def _coerce(verdicts: Any, options: Any) -> list[tuple[int, str, cc.Verdict]]:
    """(index, option text, verdict) of every UNKNOWN verdict, from a GateResult, a list of Gated
    or a
        list of verdicts aligned with `options`. Junk items are skipped."""
    opts = options if isinstance(options, (list, tuple)) else []
    out: list[tuple[int, str, cc.Verdict]] = []
    if isinstance(verdicts, GateResult):
        used: set[int] = set()
        for pos, g in enumerate(verdicts.unknown[:MAX_OPTIONS]):
            idx = pos
            for i, o in enumerate(opts[: MAX_OPTIONS * 2]):
                if i not in used and o == g.option:
                    idx = i
                    used.add(i)
                    break
            out.append((idx, _text(g.option), g.verdict))
        return [x for x in out if _is_verdict(x[2]) and x[2].status == "unknown"]
    if isinstance(verdicts, (str, bytes, Mapping)) or not isinstance(verdicts, Iterable):
        return []
    for pos, item in enumerate(verdicts):
        if pos >= MAX_OPTIONS:
            break
        if _is_verdict(item):
            v, text = item, (_text(opts[pos]) if pos < len(opts) else "")
        elif _is_verdict(getattr(item, "verdict", None)):
            v, text = item.verdict, _text(getattr(item, "option", ""))
        else:
            continue
        if v.status == "unknown":
            out.append((pos, text, v))
    return out


def _problem_numbers(reqs: Requirements, fact: str | None) -> tuple[int, ...]:
    """The problems whose stored data the fact is about (secondary score)."""
    if fact is None or not isinstance(reqs, Requirements):
        return ()
    nums: list[int] = []
    for p in reqs.problems[:50]:
        c = p.constraints
        hit = {
            "budget_ceiling": bool(c.budget),
            "budget_currency_period": bool(c.budget),
            "staff_headcount": bool(c.staff),
            "deadline_duration": bool(c.deadline),
            "cannot_change_detail": bool(c.cannot_change),
            "place_allowed": bool(c.cannot_change),
            "tried_outcome": bool(p.tried),
            "tried_detail": bool(p.tried),
        }.get(fact, False)
        if hit:
            nums.append(p.number)
    return tuple(nums)


def explain_unknowns(
    verdicts: Any,
    requirements: Requirements | None = None,
    options: Sequence[str] | None = None,
) -> tuple[UnknownExplanation, ...]:
    """For each UNKNOWN option, the structured reason. Verdicts that are ok or violating are not
    listed. Never raises."""
    try:
        reqs = as_requirements(requirements) if requirements is not None else Requirements()
        if not isinstance(reqs, Requirements):
            reqs = Requirements()
        out: list[UnknownExplanation] = []
        for idx, text, v in _coerce(verdicts, options):
            code = classify_reason(v.reason, v.rule)
            resolution, fact = _CODE_FACT[code]
            out.append(
                UnknownExplanation(
                    index=idx,
                    option=_clip(text, MAX_OPTION_CHARS),
                    rule=_text(v.rule),
                    code=code,
                    reason=_text(v.reason),
                    evidence=tuple(_text(e) for e in v.evidence[:5])
                    if isinstance(v.evidence, tuple)
                    else (),
                    resolution=resolution,
                    fact=fact,
                    problems=_problem_numbers(reqs, fact),
                )
            )
        return tuple(out)
    except Exception:  # noqa: BLE001 - never raises
        return ()


# --------------------------------------------------------------- stored / answered detection


def _ceilings(reqs: Requirements) -> list[cc.Ceiling]:
    out = []
    for limit in reqs.budgets[:50]:
        out.append(cc.parse_ceiling(_text(limit.text)[: cc.LIMIT_CHARS]))
    return out


def _one_off(text: str) -> bool:
    t = _norm(text)
    return bool(lx.ONE_OFF.search(t)) or any(o in t for o in lx.ONE_OFF_OTHER)


def _currency_in(text: str) -> str | None:
    t = _norm(text)
    for sym in ("$", "£", "€"):
        if sym in t:
            return lx.CURRENCIES[sym]
    for w in lx.WORD.findall(t):
        if w in lx.CURRENCIES:
            return lx.CURRENCIES[w]
    for key, cur in lx.CURRENCIES.items():
        if not key.isascii() and key in t:
            return cur
    return None


def _gate_currency(code: str | None) -> str | None:
    """The gate's label: the rupee family (PKR, INR, Rs) is "RS"; the rest keep their code."""
    if not code:
        return None
    return "RS" if code.upper() in {"PKR", "INR", "RS"} else code.upper()


def _period_in(text: str) -> str | None:
    t = _norm(text)
    for w in lx.WORD.findall(t):
        if w in lx.PERIODS:
            return lx.PERIODS[w]
    for key, per in lx.PERIODS.items():
        if not key.isascii() and key in t:
            return per
    return None


def _tried_needing_outcome(reqs: Requirements) -> list[Any]:
    out = []
    for item in reqs.tried[:50]:
        o = cc.norm(_text(item.outcome))
        if not (cc.FAILED.search(o) or cc.SUCCEEDED.search(o)):
            out.append(item)
    return out


def _is_stored(key: str, reqs: Requirements) -> bool:
    """True when the fact is already stored in a form the gate reads: it is never asked again."""
    if key == "budget_ceiling":
        return any(c.value is not None and not c.floor_only for c in _ceilings(reqs))
    if key == "budget_currency_period":
        for limit in reqs.budgets[:50]:
            t = _text(limit.text)[: cc.LIMIT_CHARS]
            c = cc.parse_ceiling(t)
            if c.value is not None and c.currency and (c.period or _one_off(t)):
                return True
        return False
    if key == "staff_headcount":
        return any(
            cc.parse_staff_limit(_text(x.text)[: cc.LIMIT_CHARS]) is not None
            for x in reqs.staff[:50]
        )
    if key == "deadline_duration":
        return any(
            cc.parse_days(_text(x.text)[: cc.LIMIT_CHARS], need_cue=False) is not None
            for x in reqs.deadlines[:50]
        )
    if key == "tried_outcome":
        return bool(reqs.tried) and not _tried_needing_outcome(reqs)
    if key == "tried_detail":
        return any(
            [w for w in cc.words_of(_text(t.what)) if w not in cc.STOPWORDS]
            for t in reqs.tried[:50]
        )
    if key == "place_allowed":
        return any(lex_place(_text(x.text)) for x in reqs.cannot_change[:50])
    if key == "expected_outcome":
        return any(bool(p.expected_outcome) for p in reqs.problems[:50])
    return (
        False  # cannot_change_detail asks for a clearer version of what is stored; tools_resources
    )


def lex_place(text: str) -> tuple[str, ...]:
    from app.modules.pi import constraint_lexicon as lex

    return lex.place_limit(cc.norm(text))


def answered_in_messages(key: str, messages: Any) -> bool:
    """True when an earlier owner message already answers the fact (a figure with its cue). Used to
    avoid asking what was said in chat but not stored. Conservative: facts without a safe reading
    here (what cannot be changed, what was tried, tools) are never reported as answered."""
    try:
        for raw in _clean_messages(messages):
            t = _norm(raw)
            if key == "budget_ceiling":
                if (
                    _has_any(t, lx.BUDGET_CUES, lx.BUDGET_CUES_OTHER)
                    and cc.parse_ceiling(t).value is not None
                ):
                    return True
            elif key == "budget_currency_period":
                if (
                    _has_any(t, lx.BUDGET_CUES, lx.BUDGET_CUES_OTHER)
                    and _currency_in(t)
                    and (_period_in(t) or _one_off(t))
                ):
                    return True
            elif key == "staff_headcount":
                if cc.parse_staff_limit(t) is not None:
                    return True
            elif key == "deadline_duration":
                if (
                    _has_any(t, lx.DEADLINE_CUES, lx.DEADLINE_CUES_OTHER)
                    and cc.parse_days(t, need_cue=True) is not None
                ):
                    return True
        return False
    except Exception:  # noqa: BLE001
        return False


# ----------------------------------------------------------------------- 2. rank the facts


@dataclass(frozen=True, slots=True)
class MissingFact:
    key: str
    label: str
    status: str  # askable, stored, answered_in_chat, exhausted
    options: tuple[int, ...]  # indices of the unknown options it would address
    option_texts: tuple[str, ...]
    problems: tuple[int, ...]
    codes: tuple[str, ...]
    reask: bool = False

    @property
    def n_options(self) -> int:
        return len(self.options)

    @property
    def n_problems(self) -> int:
        return len(self.problems)

    @property
    def askable(self) -> bool:
        return self.status == "askable"


def _asked_counts(asked: Any) -> Counter[str]:
    if isinstance(asked, str):
        asked = [asked]
    if not isinstance(asked, Iterable) or isinstance(asked, (bytes, Mapping)):
        return Counter()
    return Counter(k for k in asked if isinstance(k, str))


def _non_answer_counts(non_answers: Any) -> dict[str, int]:
    if not isinstance(non_answers, Mapping):
        return {}
    return {
        k: v
        for k, v in non_answers.items()
        if isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool)
    }


def rank_missing_information(
    verdicts: Any,
    requirements: Requirements | None = None,
    options: Sequence[str] | None = None,
    *,
    owner_messages: Any = (),
    asked: Any = (),
    non_answers: Mapping[str, int] | None = None,
    include_zero: bool = False,
) -> tuple[MissingFact, ...]:
    """The facts that would address unknown decisions, best first (askable ones before the rest).

    Score: options addressed (more first), then problems behind it (more first), then a fixed
    priority, then the key. A fact stored in the requirements, answered in `owner_messages`, or
    asked
    out (asked once with no non-answer, or twice) is listed with its status and never `askable`.
    `asked` is a collection of keys (a key listed twice was asked twice); `non_answers` maps a key
    to
    the number of replies that gave nothing. Facts addressing no unknown option are left out unless
    `include_zero`. Never raises."""
    try:
        reqs = as_requirements(requirements) if requirements is not None else Requirements()
        if not isinstance(reqs, Requirements):
            reqs = Requirements()
        expl = explain_unknowns(verdicts, reqs, options)
        by_fact: dict[str, list[UnknownExplanation]] = {}
        for e in expl:
            if e.owner_answerable and e.fact is not None:
                by_fact.setdefault(e.fact, []).append(e)
        times = _asked_counts(asked)
        quiet = _non_answer_counts(non_answers)
        rows: list[MissingFact] = []
        for key, spec in FACTS.items():
            items = by_fact.get(key, [])
            if not items and not include_zero:
                continue
            idxs = tuple(sorted({e.index for e in items}))
            seen: set[int] = set()
            texts = []
            for e in sorted(items, key=lambda x: x.index):
                if e.index not in seen:
                    seen.add(e.index)
                    texts.append(e.option)
            problems = _problem_numbers(reqs, key)
            codes = tuple(sorted({e.code.value for e in items}))
            if _is_stored(key, reqs):
                status, reask = "stored", False
            elif answered_in_messages(key, owner_messages):
                status, reask = "answered_in_chat", False
            elif times[key] == 0:
                status, reask = "askable", False
            elif times[key] == 1 and quiet.get(key, 0) >= 1:
                status, reask = "askable", True
            else:
                status, reask = "exhausted", False
            rows.append(
                MissingFact(key, spec.label, status, idxs, tuple(texts), problems, codes, reask)
            )
        rows.sort(
            key=lambda r: (
                r.status != "askable",
                -r.n_options,
                -r.n_problems,
                FACTS[r.key].priority,
                r.key,
            )
        )
        return tuple(rows)
    except Exception:  # noqa: BLE001
        return ()


# ------------------------------------------------------------------- 3. choose one question


@dataclass(frozen=True, slots=True)
class Question:
    key: str
    fact: str  # the missing fact, in English
    field: str  # the requirement field an answer fills
    text: str  # the question, in `language`; one question mark, last sentence
    language: str
    why: tuple[
        str, ...
    ]  # the options it would address, in the owner-facing words they were drafted in
    options: tuple[int, ...]  # indices of the unknown options to check again after an answer
    option_texts: tuple[str, ...]
    problems: tuple[int, ...]
    codes: tuple[str, ...]
    reask: bool = False
    slot: str = ""  # the owner's own words put in the question ("what was tried"), else ""
    target_limits: tuple[str, ...] = ()  # the stored limit texts the answer clarifies
    owner_answerable: bool = True

    @property
    def n_unblocked(self) -> int:
        return len(self.options)


_QMARKS = "?؟"


def safe_slot(value: Any) -> str:
    """The owner's words for a template slot: letters, spaces and apostrophes only, short, and free
    of
        the banned words. Anything else gives '' and the template without the slot is used."""
    t = _SPACE.sub(" ", _text(value)).strip()
    t = re.sub(r"[^\w' ]|\d|_", " ", t, flags=re.UNICODE)
    t = _SPACE.sub(" ", t).strip()
    if not t or len(t) > MAX_SLOT_CHARS:
        return ""
    if _banned_in(t):
        return ""
    return t


def _banned_in(text: str) -> bool:
    low = text.lower()
    words = set(lx.WORD.findall(low))
    return bool(words & lx.BANNED_WORDS) or any(s in low for s in lx.BANNED_SUBSTRINGS)


def lint_question(text: Any, language: Any = "en") -> tuple[str, ...]:
    """What is wrong with a question text (empty tuple: nothing). One question mark, and it ends the
    text; no digit; no price, quote, offer, payment, promise or secret word; British spelling."""
    t = _text(text).strip()
    problems: list[str] = []
    if not t:
        return ("empty",)
    if sum(t.count(q) for q in _QMARKS) != 1:
        problems.append("question_marks")
    if t[-1] not in _QMARKS:
        problems.append("not_last")
    if any(ch.isdigit() for ch in t):
        problems.append("digit")
    if _banned_in(t):
        problems.append("banned_word")
    low = t.lower()
    words = set(lx.WORD.findall(low))
    if words & lx.AMERICAN_SPELLINGS or lx.AMERICAN_ENDING.search(low):
        problems.append("american_spelling")
    return tuple(problems)


def render_question(key: str, language: Any = "en", *, what: str = "", reask: bool = False) -> str:
    """The question text for a key. '' for an unknown key."""
    lang = _lang(language)
    slot = safe_slot(what)
    table = lx.QUESTIONS_WITH_WHAT.get(key) if slot else None
    if table:
        text = table[lang].format(what=slot)
    else:
        text = lx.QUESTIONS.get(key, {}).get(lang, "")
    if not text:
        return ""
    return (lx.REASK_PREFIX[lang] + text) if reask else text


def _why(texts: Sequence[str]) -> tuple[str, ...]:
    return tuple(_clip(t, MAX_WHY_CHARS) for t in texts[:MAX_WHY] if t)


def _target_limits(key: str, reqs: Requirements) -> tuple[str, ...]:
    if key == "budget_ceiling" or key == "budget_currency_period":
        return tuple(_clip(_text(x.text), 200) for x in reqs.budgets[:MAX_PROBLEM_TARGETS])
    if key == "staff_headcount":
        return tuple(_clip(_text(x.text), 200) for x in reqs.staff[:MAX_PROBLEM_TARGETS])
    if key == "deadline_duration":
        return tuple(_clip(_text(x.text), 200) for x in reqs.deadlines[:MAX_PROBLEM_TARGETS])
    if key == "cannot_change_detail":
        return tuple(_clip(_text(x.text), 200) for x in reqs.cannot_change[:MAX_PROBLEM_TARGETS])
    if key == "tried_outcome":
        return tuple(
            _clip(_text(t.what), 200) for t in _tried_needing_outcome(reqs)[:MAX_PROBLEM_TARGETS]
        )
    return ()


def choose_question(
    verdicts: Any,
    requirements: Requirements | None = None,
    options: Sequence[str] | None = None,
    *,
    language: str | None = None,
    owner_messages: Any = (),
    asked: Any = (),
    non_answers: Mapping[str, int] | None = None,
) -> Question | None:
    """ONE question, or None.

    None means: nothing owner-answerable is left (every unknown is the option's, the gate's or a
    script it cannot read, or every askable fact is stored, answered, or asked out). The flow then
    says what is unknown and offers to learn first. A returned question always addresses at least
    one
    unknown option. Never raises."""
    try:
        reqs = as_requirements(requirements) if requirements is not None else Requirements()
        if not isinstance(reqs, Requirements):
            reqs = Requirements()
        ranked = rank_missing_information(
            verdicts,
            reqs,
            options,
            owner_messages=owner_messages,
            asked=asked,
            non_answers=non_answers,
        )
        for fact in ranked:
            if not fact.askable or not fact.options:
                continue
            what = ""
            if fact.key == "tried_outcome":
                pending = _tried_needing_outcome(reqs)
                what = _text(pending[0].what) if pending else ""
            text = render_question(fact.key, language, what=what, reask=fact.reask)
            if not text or lint_question(text, language):
                continue
            slot = safe_slot(what) if text.find('"') >= 0 else ""
            return Question(
                key=fact.key,
                fact=fact.label,
                field=FACTS[fact.key].field,
                text=text,
                language=_lang(language),
                why=_why(fact.option_texts),
                options=fact.options,
                option_texts=fact.option_texts,
                problems=fact.problems,
                codes=fact.codes,
                reask=fact.reask,
                slot=slot,
                target_limits=_target_limits(fact.key, reqs),
            )
        return None
    except Exception:  # noqa: BLE001
        return None


@dataclass(frozen=True, slots=True)
class ResolutionPlan:
    """The whole picture for the flow: the question (or None), every explanation, the ranking, and
    what
        stays unknown whatever the owner says."""

    question: Question | None
    explanations: tuple[UnknownExplanation, ...]
    ranked: tuple[MissingFact, ...]
    counts: Mapping[str, int]  # unknown options per Code value
    unresolvable: int  # unknown options no owner answer can fix
    learn_first: bool  # True when there is no question and something is unknown


def plan_resolution(
    verdicts: Any,
    requirements: Requirements | None = None,
    options: Sequence[str] | None = None,
    *,
    language: str | None = None,
    owner_messages: Any = (),
    asked: Any = (),
    non_answers: Mapping[str, int] | None = None,
) -> ResolutionPlan:
    expl = explain_unknowns(verdicts, requirements, options)
    ranked = rank_missing_information(
        verdicts,
        requirements,
        options,
        owner_messages=owner_messages,
        asked=asked,
        non_answers=non_answers,
    )
    q = choose_question(
        verdicts,
        requirements,
        options,
        language=language,
        owner_messages=owner_messages,
        asked=asked,
        non_answers=non_answers,
    )
    counts = Counter(e.code.value for e in expl)
    return ResolutionPlan(
        question=q,
        explanations=expl,
        ranked=ranked,
        counts=dict(counts),
        unresolvable=sum(not e.owner_answerable for e in expl),
        learn_first=q is None and bool(expl),
    )


# --------------------------------------------------------------------------- 4. apply an answer


class Status(StrEnum):
    FILLED = "filled"  # a value was read: the gate must check the listed options again
    CORRECTION = (
        "correction_candidate"  # the answer contradicts what is stored: ask before replacing
    )
    STILL_UNKNOWN = "still_unknown"  # nothing was read; `reason` says why


@dataclass(frozen=True, slots=True)
class FieldUpdate:
    field: str  # budget, staff, deadline, cannot_change, tried
    problem_number: int | None
    value: (
        str  # the limit text in a form the gate reads (round-tripped through the gate's own reader)
    )
    replaces: str | None  # the stored text it clarifies or contradicts
    parsed: tuple[tuple[str, str], ...]
    is_correction: bool = False


@dataclass(frozen=True, slots=True)
class AnswerProposal:
    status: Status
    key: str
    updates: tuple[FieldUpdate, ...] = ()
    reason: str = ""  # why it is still unknown: non_answer, hedged, ambiguous, no_figure, ...
    recheck_indices: tuple[int, ...] = ()  # the options the real gate must check again
    recheck_options: tuple[str, ...] = ()
    non_answer: bool = False
    satisfied: bool = False  # always False: only the gate can say an option now passes


def _unknown_answer(key: str, reason: str, *, non_answer: bool = False) -> AnswerProposal:
    return AnswerProposal(Status.STILL_UNKNOWN, key, (), reason, (), (), non_answer)


def _targets(q: Question, reqs: Requirements) -> tuple[int | None, ...]:
    nums = q.problems[:MAX_PROBLEM_TARGETS] if isinstance(q.problems, tuple) else ()
    if nums:
        return tuple(nums)
    first = reqs.problems[0].number if reqs.problems else None
    return (first,)


def _stored_for(key: str, reqs: Requirements, number: int | None) -> str | None:
    for p in reqs.problems[:50]:
        if number is not None and p.number != number:
            continue
        c = p.constraints
        if key.startswith("budget") and c.budget:
            return c.budget.text
        if key == "staff_headcount" and c.staff:
            return c.staff.text
        if key == "deadline_duration" and c.deadline:
            return c.deadline.text
    return None


def _read_budget(text: str) -> tuple[str, tuple[tuple[str, str], ...]] | str:
    """(limit text, parsed) or the reason it cannot be read."""
    t = _norm(text)
    amounts = [a for a in cc.parse_amounts(t, assume_money=True) if a.role != "none"]
    ceiling = cc.parse_ceiling(t)
    if ceiling.value is None and not ceiling.floor_only and ceiling.raw != "zero":
        return "no_figure"
    if ceiling.floor_only:
        return "floor_only"
    if (
        ceiling.raw != "zero"
        and len({a.value for a in amounts if not a.in_range}) > 1
        and not any(a.in_range for a in amounts)
    ):
        return "ambiguous"
    parsed = [("value", str(ceiling.value))]
    if ceiling.currency:
        parsed.append(("currency", ceiling.currency))
    if ceiling.period:
        parsed.append(("period", ceiling.period))
    return _clip(_text(text), 300), tuple(parsed)


def _read_staff(text: str) -> tuple[str, tuple[tuple[str, str], ...]] | str:
    raw = _clip(_text(text), 300)
    n = cc.parse_staff_limit(raw)
    if n is None:
        # a bare number answers "how many people": read it as the question asked, then round-trip
        t = _norm(raw)
        if cc._STAFF_FLOOR.search(t):
            return "floor_only"
        nums = re.findall(r"\d+", t)
        words = [
            w for w in lx.WORD.findall(t) if w in cc.SMALL_NUMBER_WORDS and w not in {"do", "teen"}
        ]
        rest = [
            w
            for w in lx.WORD.findall(t)
            if w not in cc.SMALL_NUMBER_WORDS and w not in lx.STAFF_FILLER
        ]
        if len(nums) + len(words) != 1:
            return "no_number" if not (nums or words) else "ambiguous"
        if rest:
            return "unreadable"
        n_val = int(nums[0]) if nums else cc.SMALL_NUMBER_WORDS[words[0]]
        composed = f"only {min(n_val, 10**6)} people"
        if cc.parse_staff_limit(composed) is None:
            return "unreadable"
        return composed, (("max_people", str(min(n_val, 10**6))),)
    t = _norm(raw)
    figures = {int(x) for x in re.findall(r"\d+", t)}
    if len(figures) > 1:
        return "ambiguous"
    return raw, (("max_people", str(n)),)


def _read_deadline(text: str) -> tuple[str, tuple[tuple[str, str], ...]] | str:
    raw = _clip(_text(text), 300)
    days = cc.parse_days(raw, need_cue=False)
    if days is None:
        return "needs_calendar"
    return raw, (("days", f"{days:g}"),)


def _read_cannot_change(text: str) -> tuple[str, tuple[tuple[str, str], ...]] | str:
    raw = _clip(_text(text), 300)
    if not cc.mostly_latin(raw):
        return "script_unreadable"
    clauses = cc.limit_clauses(raw) or [raw]
    kinds = [cc.parse_limit(c).kind for c in clauses]
    good = [k for k in kinds if k not in {"unreadable", "unknown_verb"}]
    if not good:
        return "too_vague" if "unreadable" in kinds else "not_enforced"
    return raw, tuple(("kind", k) for k in sorted(set(good)))


def _read_tried(text: str) -> tuple[str, tuple[tuple[str, str], ...]] | str:
    raw = _clip(_text(text), 300)
    o = cc.norm(raw)
    failed = bool(cc.FAILED.search(o))
    worked = bool(cc.SUCCEEDED.search(o))
    if failed == worked:
        return "ambiguous" if failed else "no_outcome"
    return raw, (("outcome", "failed" if failed else "worked"),)


def _read_place(text: str) -> tuple[str, tuple[tuple[str, str], ...]] | str:
    raw = _clip(_text(text), 300)
    if not cc.mostly_latin(raw):
        return "script_unreadable"
    composed = raw if cc.parse_limit(raw).kind == "location" else f"only in {raw}"
    lim = cc.parse_limit(composed)
    if lim.kind != "location" or not lim.objects:
        return "unknown_place"
    return composed, tuple(("place", p) for p in lim.objects[:5])


def _read_currency_period(
    text: str, stored: str | None
) -> tuple[str, tuple[tuple[str, str], ...]] | str:
    cur, per = _gate_currency(_currency_in(text)), _period_in(text)
    one_off = _one_off(text)
    if cur is None and per is None and not one_off:
        return "no_currency_or_period"
    if per and one_off:
        return "ambiguous"
    base = cc.parse_ceiling(_text(stored)[: cc.LIMIT_CHARS]) if stored else None
    if base is None or base.value is None:
        return "no_stored_budget"
    use_cur = cur or _gate_currency(base.currency)
    use_per = per or base.period
    if not use_cur:
        return "no_currency"
    if not use_per and not one_off:
        return "no_period"
    figure = (
        f"{base.value:f}".rstrip("0").rstrip(".") if "." in f"{base.value:f}" else f"{base.value:f}"
    )
    composed = f"{figure} {use_cur}" + (f" per {use_per}" if use_per else " in total")
    ceiling = cc.parse_ceiling(composed)
    if ceiling.value != base.value or _gate_currency(ceiling.currency) != use_cur:
        return "unreadable"
    if use_per and ceiling.period != use_per:
        return "unreadable"
    parsed = [("currency", use_cur), ("period", use_per if use_per else "one_off")]
    return composed, tuple(parsed)


def apply_answer(
    requirements: Requirements | None,
    question: Question | None,
    owner_text: Any,
    language: str | None = None,
) -> AnswerProposal:
    """Read the owner's answer to `question` into an update proposal. Conservative: a non-answer, a
    hedge, two values, or a value the gate's own readers cannot read gives `still_unknown` with a
    reason, never a guess. A value that contradicts a stored one is a `correction_candidate`, never
    a
    silent overwrite. The proposal never marks anything satisfied: it lists the options the gate
    must
    check again and nothing else. Never raises."""
    key = getattr(question, "key", "") if isinstance(question, Question) else ""
    try:
        if not isinstance(question, Question) or key not in FACTS:
            return _unknown_answer(key, "bad_question")
        reqs = as_requirements(requirements) if requirements is not None else Requirements()
        if not isinstance(reqs, Requirements):
            return _unknown_answer(key, "bad_requirements")
        if not isinstance(owner_text, str):
            return _unknown_answer(key, "not_text", non_answer=True)
        if len(owner_text) > MAX_ANSWER_CHARS:
            return _unknown_answer(key, "too_long")
        text = _text(owner_text).strip()
        if is_non_answer(text):
            return _unknown_answer(key, "non_answer", non_answer=True)
        if _hedged(text):
            return _unknown_answer(key, "hedged")
        if key in {"budget_ceiling", "staff_headcount", "deadline_duration"} and _either_or(text):
            return _unknown_answer(key, "ambiguous")
        targets = _targets(question, reqs)
        if key == "budget_ceiling":
            read = _read_budget(text)
        elif key == "staff_headcount":
            read = _read_staff(text)
        elif key == "deadline_duration":
            read = _read_deadline(text)
        elif key == "cannot_change_detail":
            read = _read_cannot_change(text)
        elif key == "tried_outcome":
            read = _read_tried(text)
        elif key == "place_allowed":
            read = _read_place(text)
        elif key == "budget_currency_period":
            read = _read_currency_period(
                text, _stored_for(key, reqs, targets[0] if targets else None)
            )
        else:
            return _unknown_answer(key, "not_enforced_by_gate")
        if isinstance(read, str):
            return _unknown_answer(key, read)
        value, parsed = read
        spec = FACTS[key]
        updates: list[FieldUpdate] = []
        contradiction = False
        if key == "cannot_change_detail":
            for limit_text in question.target_limits[:MAX_PROBLEM_TARGETS] or (None,):
                updates.append(FieldUpdate(spec.field, None, value, limit_text, parsed))
        elif key == "tried_outcome":
            for what in question.target_limits[:MAX_PROBLEM_TARGETS][:1] or (None,):
                updates.append(FieldUpdate(spec.field, None, value, what, parsed))
        elif key == "place_allowed":
            updates.append(FieldUpdate(spec.field, None, value, None, parsed))
        else:
            for number in targets:
                stored = _stored_for(key, reqs, number)
                is_corr = _contradicts(key, stored, value, parsed)
                contradiction = contradiction or is_corr
                updates.append(FieldUpdate(spec.field, number, value, stored, parsed, is_corr))
        status = Status.CORRECTION if contradiction else Status.FILLED
        return AnswerProposal(
            status=status,
            key=key,
            updates=tuple(updates),
            recheck_indices=tuple(question.options),
            recheck_options=tuple(question.option_texts),
        )
    except Exception:  # noqa: BLE001 - never raises
        return _unknown_answer(key, "unreadable")


def _contradicts(
    key: str, stored: str | None, value: str, parsed: tuple[tuple[str, str], ...]
) -> bool:
    """True when the stored limit already reads as something else than the answer."""
    if not stored:
        return False
    p = dict(parsed)
    if key == "budget_ceiling":
        old = cc.parse_ceiling(_text(stored)[: cc.LIMIT_CHARS])
        return old.value is not None and not old.floor_only and str(old.value) != p.get("value")
    if key == "budget_currency_period":
        old = cc.parse_ceiling(_text(stored)[: cc.LIMIT_CHARS])
        if old.currency and p.get("currency") and old.currency.upper() != p["currency"].upper():
            return True
        return bool(old.period and p.get("period") not in {None, old.period})
    if key == "staff_headcount":
        old_n = cc.parse_staff_limit(_text(stored)[: cc.LIMIT_CHARS])
        return old_n is not None and str(old_n) != p.get("max_people")
    if key == "deadline_duration":
        old_d = cc.parse_days(_text(stored)[: cc.LIMIT_CHARS], need_cue=False)
        return old_d is not None and f"{old_d:g}" != p.get("days")
    return False


# ------------------------------------------------------------------------- state bookkeeping


@dataclass(frozen=True, slots=True)
class ResolutionState:
    asked: tuple[str, ...] = ()
    non_answers: tuple[tuple[str, int], ...] = ()

    @property
    def non_answer_map(self) -> dict[str, int]:
        return dict(self.non_answers)


def record_outcome(
    state: ResolutionState | None, question: Question, proposal: AnswerProposal
) -> ResolutionState:
    """The state after one question and its answer: the key counts as asked, and an answer that
    stays
        unknown counts as a non-answer for it."""
    s = state if isinstance(state, ResolutionState) else ResolutionState()
    quiet = s.non_answer_map
    if proposal.status is Status.STILL_UNKNOWN:
        quiet[question.key] = quiet.get(question.key, 0) + 1
    return ResolutionState(s.asked + (question.key,), tuple(sorted(quiet.items())))


__all__ = [
    "FACTS",
    "AnswerProposal",
    "Code",
    "FieldUpdate",
    "MissingFact",
    "Question",
    "Resolution",
    "ResolutionPlan",
    "ResolutionState",
    "Status",
    "UnknownExplanation",
    "answered_in_messages",
    "apply_answer",
    "choose_question",
    "classify_reason",
    "explain_unknowns",
    "is_non_answer",
    "lint_question",
    "plan_resolution",
    "rank_missing_information",
    "record_outcome",
    "render_question",
    "safe_slot",
]
