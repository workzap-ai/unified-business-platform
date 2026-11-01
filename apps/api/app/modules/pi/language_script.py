# ruff: noqa: E501
"""Language and script intelligence for pi (agent 8, lane ps9). Pure functions, no model calls.

What it answers, per owner message and per chat:

* `detect_message_language(text, history=(), pinned=None)`: which language and script the message is
  in, how sure that is, which other languages are present (code-switching), and when to say "I do
  not know" instead of guessing (`uncertain`). Never raises, linear time, input capped.
* `LanguagePin`: the chat's pinned language and script from the owner's earlier messages, by the
  spec's stickiness rule (RLANG09: the language and script of the person's last substantive message,
  3 words or more, a voice transcript always counts; a short or ambiguous message never moves it).
* `reply_language_for` / `reply_plan`: the (code, script) pi answers in, with the spec's special
  cases (Punjabi, Sindhi, Pashto: Roman Urdu or Urdu, ask once; Tagalog, Malayalam, Tamil, Bengali:
  English plus one line offering to continue in English).
* `business_term_normalise`: business words in any spelling and script mapped to one concept id.
* `has_correction_or_withdrawal_cue`: "I take that back", "maine galat kaha", "نہیں میرا مطلب".

Spec: platform spec v1.6 Part 2.5 (languages and scripts, RLANG02, RLANG03, RLANG07, RLANG09),
10.3 (language stickiness), RVOICE04 (mirror language and script), Part 11 style profile (script).
The scripted tests prove wiring and the labelled sets, not real-world accuracy: the word lists were
written by one author and have had no native-speaker review (spec 2.5.1).
"""

from __future__ import annotations

import re
import unicodedata
from bisect import bisect_right
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from app.modules.pi import language_script_lexicon as lex

MAX_CHARS = 4000  # longer text is cut here (linear time, bounded work)
MAX_TOKENS = 600
MAX_HISTORY = 60  # the pin looks at the last 60 owner messages
SUBSTANTIVE_WORDS = 3  # RLANG09: "the last message of 3 words"
CONFIDENT = 0.5  # below this a detection is `uncertain` and never moves the pin

CLARIFY_URDU_OR_ENGLISH = "ask_urdu_or_english"  # spec 2.5: "Urdu ya English mein baat karein?"
CLARIFY_WHICH_LANGUAGE = "ask_which_language"
CLARIFY_TEXT = {CLARIFY_URDU_OR_ENGLISH: "Urdu ya English mein baat karein?"}

# Scripts by code. Arabic-script languages share one script name.
SCRIPT_OF_CODE: dict[str, str] = {
    "en": "latin", "roman_ur": "latin", "roman_hi": "latin", "roman_hi_or_ur": "latin",
    "fr": "latin", "es": "latin", "de": "latin", "id": "latin", "tr": "latin", "tl": "latin",
    "ur": "arabic", "ar": "arabic", "fa": "arabic", "ps": "arabic", "sd": "arabic", "pa": "arabic",
    "hi": "devanagari", "bn": "bengali", "ta": "tamil", "ml": "malayalam", "te": "telugu",
    "kn": "kannada", "gu": "gujarati", "pa_guru": "gurmukhi", "ru": "cyrillic", "el": "greek",
    "he": "hebrew", "th": "thai", "zh": "han", "ja": "kana", "ko": "hangul", "und": "none",
}  # fmt: skip
ROMAN_INDIC = ("roman_ur", "roman_hi", "roman_hi_or_ur")
# Languages with no fixed lines and no priority status: the spec says English plus an offer (UAE workforce).
ENGLISH_OFFER = ("tl", "bn", "ta", "ml", "te", "kn", "gu", "pa_guru")
ASK_ONCE = ("pa", "sd", "ps")

# ---------------------------------------------------------------- scripts

_SCRIPT_RANGES: tuple[tuple[int, int, str], ...] = (
    (0x00C0, 0x024F, "latin"), (0x0370, 0x03FF, "greek"), (0x0400, 0x04FF, "cyrillic"),
    (0x0590, 0x05FF, "hebrew"), (0x0600, 0x06FF, "arabic"), (0x0750, 0x077F, "arabic"),
    (0x08A0, 0x08FF, "arabic"), (0x0900, 0x097F, "devanagari"), (0x0980, 0x09FF, "bengali"),
    (0x0A00, 0x0A7F, "gurmukhi"), (0x0A80, 0x0AFF, "gujarati"), (0x0B80, 0x0BFF, "tamil"),
    (0x0C00, 0x0C7F, "telugu"), (0x0C80, 0x0CFF, "kannada"), (0x0D00, 0x0D7F, "malayalam"),
    (0x0E00, 0x0E7F, "thai"), (0x1100, 0x11FF, "hangul"), (0x1E00, 0x1EFF, "latin"),
    (0x3040, 0x30FF, "kana"), (0x3400, 0x4DBF, "han"), (0x4E00, 0x9FFF, "han"),
    (0xAC00, 0xD7AF, "hangul"), (0xFB50, 0xFDFF, "arabic"), (0xFE70, 0xFEFF, "arabic"),
)  # fmt: skip
_RANGE_STARTS = [r[0] for r in _SCRIPT_RANGES]
SCRIPT_TO_CODE = {
    "devanagari": "hi", "bengali": "bn", "tamil": "ta", "malayalam": "ml", "telugu": "te",
    "kannada": "kn", "gujarati": "gu", "gurmukhi": "pa_guru", "cyrillic": "ru", "greek": "el",
    "hebrew": "he", "thai": "th", "han": "zh", "kana": "ja", "hangul": "ko",
}  # fmt: skip


def script_of_char(ch: str) -> str | None:
    """The script of one letter, None for digits, marks, punctuation, emoji and symbols."""
    o = ord(ch)
    if o < 128:
        return "latin" if ("a" <= ch <= "z" or "A" <= ch <= "Z") else None
    if o in (0xD7, 0xF7) or not unicodedata.category(ch).startswith("L"):
        return None
    i = bisect_right(_RANGE_STARTS, o) - 1
    if i >= 0 and o <= _SCRIPT_RANGES[i][1]:
        return _SCRIPT_RANGES[i][2]
    return None


# ---------------------------------------------------------------- folding

_AR_DROP = {
    c: None for c in [*range(0x064B, 0x0660), 0x0670, 0x0640, 0x200C, 0x200D, 0x200F, 0x200E]
}
for _c in range(0x06D6, 0x06EE):
    _AR_DROP[_c] = None
_AR_MAP = {
    0x064A: "ی", 0x0649: "ی", 0x0643: "ک", 0x0623: "ا", 0x0625: "ا", 0x0622: "ا", 0x0671: "ا",
    0x06C0: "ہ", 0x06D5: "ہ",
}  # fmt: skip
_AR_TABLE = {**_AR_DROP, **{k: v for k, v in _AR_MAP.items()}}
_DEVA_TABLE = {0x093C: None, 0x0901: "ं", 0x200C: None, 0x200D: None}


def fold_arabic(text: str) -> str:
    """Drop vowel marks and tatweel, ي to ی, ك to ک, hamza forms to alef: voice and typed noise."""
    return text.translate(_AR_TABLE)


def fold_deva(text: str) -> str:
    return text.translate(_DEVA_TABLE)


_SQUEEZE = re.compile(r"(.)\1{2,}")


def _strip_marks(word: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", word) if not unicodedata.combining(c))


def fold_latin(word: str) -> str:
    """One spelling key for Roman Urdu/Hindi variants: kartay/karte/karty, nahee/nahi, bohooot/bohut."""
    w = _SQUEEZE.sub(r"\1\1", _strip_marks(word.lower()).replace("’", "'"))
    if w == "hay":
        return "hai"
    w = (
        w.replace("chh", "ch")
        .replace("aa", "a")
        .replace("ee", "i")
        .replace("oo", "u")
        .replace("ii", "i")
    )
    if len(w) >= 5 and (w.endswith("ay") or w.endswith("ey")):
        w = w[:-2] + "e"
    return w


# ---------------------------------------------------------------- tokens


def _tokens(text: str) -> list[str]:
    """Words: letters, marks and digits, with an inner apostrophe or ZWNJ. Linear, capped."""
    out: list[str] = []
    cur: list[str] = []
    for ch in text:
        if ch.isalnum() or ch in "‌" or unicodedata.category(ch)[0] == "M":
            cur.append(ch)
        elif ch in "'’" and cur:
            cur.append("'")
        elif cur:
            out.append("".join(cur).strip("'"))
            cur = []
            if len(out) >= MAX_TOKENS:
                return out
    if cur:
        out.append("".join(cur).strip("'"))
    return [t for t in out if t][:MAX_TOKENS]


_URL = re.compile(r"(?:https?://|www\.)\S+|\S+@\S+\.\S+|@\w+", re.IGNORECASE)


def _clean(text: str | None) -> str:
    text = unicodedata.normalize("NFKC", (text or "")[:MAX_CHARS])
    return _URL.sub(" ", text)


# ---------------------------------------------------------------- lexicon tables (built once)


def _set(words: Iterable[str], fold: Any = None) -> frozenset[str]:
    return frozenset(fold(w) if fold else w for w in words)


_AMBIG = _set(lex.AMBIGUOUS_ANSWERS)
_AMBIG_F = _set(lex.AMBIGUOUS_ANSWERS, fold_latin)
_AMBIG_NATIVE = _set(fold_deva(fold_arabic(w)) for w in lex.AMBIGUOUS_NATIVE)
_EN_FN = _set(lex.ENGLISH_FUNCTION)
_EN_WEAK = _set(lex.ENGLISH_WEAK)
_EN_VOCAB = _set(lex.ENGLISH_VOCAB)
_EN_ALL = _EN_FN | _EN_WEAK | _EN_VOCAB
_IND_STRONG = (
    _set(lex.ROMAN_INDIC_STRONG, fold_latin)
    - _set(_EN_ALL, fold_latin)
    - {"bar", "mat", "lie", "bare", "pore", "mile", "thin", "thy", "lag", "der"}
)
_IND_WEAK = _set(lex.ROMAN_INDIC_WEAK, fold_latin) | {"der"}
_UR_ONLY = _set(lex.ROMAN_URDU_ONLY, fold_latin)
_HI_ONLY = _set(lex.ROMAN_HINDI_ONLY, fold_latin)
_LATIN_LANGS = {
    k: _set(v.split()) | _set(_strip_marks(w) for w in v.split())
    for k, v in lex.LATIN_LANGS.items()
}
_AR_WORDS = {k: _set(fold_arabic(w) for w in v.split()) for k, v in lex.ARABIC_SCRIPT_WORDS.items()}
_PA_ONLY = _AR_WORDS["pa"] - _AR_WORDS["ur"]
_IND_MAXLEN = 12
_SEG_WORDS = (
    _IND_STRONG
    | (_EN_FN - {"a", "i", "it", "my", "of", "at", "by", "be", "an", "if", "up", "am", "as"})
) - frozenset()

_UR_LETTERS = frozenset("ٹڈڑںےہھۓۂ")
_PS_LETTERS = frozenset("ښځڅډټړږڼېۍګ")
_SD_LETTERS = frozenset("ڀٻٿٽڏڌڊڍڙڪڳڱڻڦڄڃڇ۽۾")
_FA_LETTERS = frozenset("پچژگ")
_AR_ONLY_LETTERS = frozenset("يكةىأإؤٱ")
_AR_INDIC_DIGITS = frozenset("٠١٢٣٤٥٦٧٨٩")


# ---------------------------------------------------------------- decision types


@dataclass(frozen=True)
class LanguageDecision:
    """The answer for one message. `code` is a language code ("und" when nothing is known), `script` a
    script name; when `uncertain` the code is the pinned language (or "und") and `detected` keeps
    what the message alone suggested."""

    code: str
    script: str
    confidence: float
    evidence: tuple[str, ...]
    uncertain: bool
    reason: str
    present: tuple[str, ...] = ()
    detected: str = "und"
    short: bool = False
    needs_clarification: bool = False
    clarify_key: str | None = None


@dataclass(frozen=True)
class PinState:
    """The chat's pinned language: `code`/`script`, the index (in the history given) of the message
    that set it, and how it was set."""

    code: str
    script: str
    index: int = -1
    basis: str = "default"


@dataclass(frozen=True)
class HistoryTurn:
    text: str
    voice: bool = False


@dataclass(frozen=True)
class ReplyPlan:
    code: str
    script: str
    ask_key: str | None = None
    offer_english: bool = False
    profile_note: str | None = None


@dataclass(frozen=True)
class _Raw:
    code: str
    confidence: float
    evidence: tuple[str, ...]
    reason: str
    present: tuple[str, ...]
    words: int
    all_ambiguous: bool = False


def _turn(item: Any) -> HistoryTurn | None:
    """A history entry: a string, a HistoryTurn, a dict with text/voice, or a message row (`body`,
    `message_type`, `sender_type`; rows that are not the owner's are skipped)."""
    try:
        if isinstance(item, HistoryTurn):
            return item
        if isinstance(item, str):
            return HistoryTurn(item)
        if isinstance(item, dict):
            return HistoryTurn(
                str(item.get("text") or item.get("body") or ""), bool(item.get("voice"))
            )
        body = getattr(item, "body", None)
        if body is None:
            return None
        sender = getattr(item, "sender_type", "customer")
        if sender not in ("customer", "owner", "user"):
            return None
        return HistoryTurn(str(body), getattr(item, "message_type", "text") == "audio")
    except Exception:  # never raise
        return None


def _pin_of(pinned: Any) -> tuple[str, str] | None:
    if pinned is None:
        return None
    if isinstance(pinned, str):
        return (pinned, SCRIPT_OF_CODE.get(pinned, "latin")) if pinned and pinned != "und" else None
    if (
        isinstance(pinned, (tuple, list))
        and pinned
        and isinstance(pinned[0], str)
        and pinned[0] != "und"
    ):
        return (
            pinned[0],
            str(pinned[1]) if len(pinned) > 1 else SCRIPT_OF_CODE.get(pinned[0], "latin"),
        )
    code = getattr(pinned, "code", None)
    if isinstance(code, str) and code != "und":
        return (code, str(getattr(pinned, "script", None) or SCRIPT_OF_CODE.get(code, "latin")))
    return None


# ---------------------------------------------------------------- Latin analysis


def _segment(token: str) -> list[str]:
    """Words of a run-together token ("mujhekyahai"): the words of the strong lists, covering all of
    it, 2 or more, else []. O(len * 12), only for tokens of 8 to 40 letters."""
    n = len(token)
    if n < 8 or n > 40:
        return []
    best: list[list[str] | None] = [None] * (n + 1)
    best[0] = []
    for i in range(n):
        base = best[i]
        if base is None:
            continue
        for j in range(i + 2, min(n, i + _IND_MAXLEN) + 1):
            w = token[i:j]
            if w in _SEG_WORDS and (best[j] is None or len(best[j] or []) > len(base) + 1):
                best[j] = [*base, w]
    out = best[n]
    return out if out and len(out) >= 2 else []


def _latin(tokens: list[str]) -> _Raw:
    ind = en = 0.0
    en_fn = ind_strong = en_vocab = 0
    ur_only = hi_only = 0
    ev_ind: list[str] = []
    ev_en: list[str] = []
    words = 0
    folded_all: list[str] = []
    lows: list[str] = []
    for tok in tokens:
        if not any(script_of_char(c) == "latin" for c in tok):
            continue
        words += 1
        low = tok.lower().replace("’", "'")
        if low not in _EN_ALL and _SQUEEZE.search(low):
            sq = _SQUEEZE.sub(r"\1", low)  # "thaaanks": a voice or typing stretch
            if sq in _EN_ALL:
                low = sq
        lows.append(low)
        folded_all.append(fold_latin(low))
    all_ambig = bool(lows) and all(
        w in _AMBIG or f in _AMBIG_F for w, f in zip(lows, folded_all, strict=True)
    )
    langs: dict[str, float] = {k: 0.0 for k in _LATIN_LANGS}
    letter_hint: dict[str, float] = {}
    extra_words: list[str] = []
    for low, f in zip(lows, folded_all, strict=True):
        if low in _AMBIG or f in _AMBIG_F:
            if all_ambig:
                continue
        is_ind = f in _IND_STRONG
        is_enfn = low in _EN_FN
        if is_ind and not is_enfn:
            ind += 1.0
            ind_strong += 1
            if len(ev_ind) < 6:
                ev_ind.append(low)
            if f in _UR_ONLY:
                ur_only += 1
            if f in _HI_ONLY:
                hi_only += 1
        elif is_enfn and not is_ind:
            en += 1.0
            en_fn += 1
            if len(ev_en) < 6:
                ev_en.append(low)
        elif f in _IND_WEAK and low not in _EN_ALL:
            ind += 0.4
        elif low in _EN_WEAK:
            en += 0.4
        elif low in _EN_VOCAB:
            en += 0.4
            en_vocab += 1
        elif f in _HI_ONLY or f in _UR_ONLY:
            ind += 1.0
            ind_strong += 1
            if f in _HI_ONLY:
                hi_only += 1
            else:
                ur_only += 1
            if len(ev_ind) < 6:
                ev_ind.append(low)
        else:
            seg = (
                _segment(f)
                if len(f) >= 8 and not any(f in v for v in _LATIN_LANGS.values())
                else []
            )
            if seg:
                extra_words.extend(seg)
        for k, vocab in _LATIN_LANGS.items():
            if low in vocab or _strip_marks(low) in vocab:
                langs[k] += 1.0
        for ch in low:
            hint = lex.LATIN_LETTER_HINTS.get(ch)
            if hint:
                letter_hint[hint[0]] = min(2.0, letter_hint.get(hint[0], 0.0) + hint[1])
    for w in extra_words:  # run-together tokens: each recovered word counts
        if w in _IND_STRONG and w not in _EN_FN:
            ind += 1.0
            ind_strong += 1
        else:
            en += 1.0
            en_fn += 1
    for k, v in letter_hint.items():
        langs[k] += v
    present: list[str] = []
    # Another Latin-script language: its own words clearly outnumber English and Roman Indic ones.
    best_lang = max(langs, key=lambda k: langs[k])
    best = langs[best_lang]
    second = max((v for k, v in langs.items() if k != best_lang), default=0.0)
    rival = ind_strong + en_fn
    if best >= 2.0 and best > rival and best >= second + 1.0:
        conf = min(1.0, best / 3.0) * (0.6 + 0.4 * best / (best + second + rival))
        return _Raw(best_lang, conf, (f"words:{best_lang}={int(best)}",), "ok", (best_lang,), words)
    total = ind + en
    if all_ambig or total < 0.9:
        return _Raw(
            "und", 0.0, (), "ambiguous_answer" if all_ambig else "no_markers", (), words, all_ambig
        )
    dominant = "indic" if ind > en else "en"
    if abs(ind - en) < 0.5:
        return _Raw(
            "und",
            0.3,
            (f"ind={ind:.1f}", f"en={en:.1f}"),
            "balanced_mix",
            tuple(_present_latin(ind, en, en_fn, en_vocab)),
            words,
        )
    top = max(ind, en)
    conf = min(1.0, top / 2.5) * (0.55 + 0.45 * top / total)
    if dominant == "en":
        code = "en"
        evidence: tuple[str, ...] = ("words:en=" + ",".join(ev_en),)
    else:
        if ur_only and not hi_only:
            code = "roman_ur"
            evidence = ("words:roman=" + ",".join(ev_ind), f"urdu_only={ur_only}")
        elif hi_only and not ur_only:
            code = "roman_hi"
            evidence = ("words:roman=" + ",".join(ev_ind), f"hindi_only={hi_only}")
        else:
            code = "roman_hi_or_ur"
            evidence = ("words:roman=" + ",".join(ev_ind), "urdu_vs_hindi_unresolved")
    if conf >= CONFIDENT or dominant == "en":
        present = _present_latin(ind, en, en_fn, en_vocab)
        if code != "en" and "en" in present:
            present = [code, "en"]
        elif code == "en" and ind >= 1.4:
            present = [
                "en",
                "roman_hi_or_ur"
                if not (ur_only or hi_only)
                else ("roman_ur" if ur_only else "roman_hi"),
            ]
        else:
            present = [code, *[p for p in present if p != code]]
    return _Raw(code, conf, evidence, "ok", tuple(dict.fromkeys(present)), words)


def _present_latin(ind: float, en: float, en_fn: int, en_vocab: int) -> list[str]:
    out: list[str] = []
    if ind >= 1.4:
        out.append("roman_hi_or_ur")
    if en_fn >= 1 or en_vocab >= 2:
        out.append("en")
    return out


# ---------------------------------------------------------------- Arabic-script analysis

_URDU_MI_WORDS = (
    "میرا",
    "میری",
    "میرے",
    "میدا",
    "میلا",
    "میڈ",
    "میٹ",
    "میں",
    "میز",
    "میل",
    "میوہ",
    "میکا",
)


def _persian_verb(raw: str) -> bool:
    """A Persian verb form: "می" or "نمی" alone, with ZWNJ, or glued to a verb ("میکند", "نمیتوانیم")."""
    if raw in lex.PERSIAN_PREFIX_TOKENS:
        return True
    if len(raw) > 3 and raw[:2] in lex.PERSIAN_PREFIX_TOKENS and "‌" in raw[:4]:
        return True
    if raw.startswith("نمی") and len(raw) >= 5:
        return True
    return (
        raw.startswith("می")
        and len(raw) >= 5
        and not raw.startswith(_URDU_MI_WORDS)
        and raw.endswith(("د", "م", "ند", "ید", "یم", "ست"))
    )


def _arabic_script(text: str, tokens: list[str]) -> _Raw:
    scores = {"ar": 0.0, "ur": 0.0, "fa": 0.0, "ps": 0.0, "sd": 0.0, "pa": 0.0}
    ev: dict[str, list[str]] = {k: [] for k in scores}
    counts = {"ur": 0, "ps": 0, "sd": 0, "fa": 0, "ar": 0, "zwnj": 0}
    tashkeel = 0
    for ch in text:
        if ch in _UR_LETTERS:
            counts["ur"] += 1
        elif ch in _PS_LETTERS:
            counts["ps"] += 1
        elif ch in _SD_LETTERS:
            counts["sd"] += 1
        elif ch in _FA_LETTERS:
            counts["fa"] += 1
        elif ch in _AR_ONLY_LETTERS or ch in _AR_INDIC_DIGITS:
            counts["ar"] += 1
        elif 0x064B <= ord(ch) <= 0x0652:
            tashkeel += 1
        elif ch == "‌":
            counts["zwnj"] += 1
    scores["ur"] += 1.5 * min(counts["ur"], 4)
    scores["pa"] += 0.5 * min(counts["ur"], 4)
    scores["ps"] += 3.0 * min(counts["ps"], 3)
    scores["sd"] += 3.0 * min(counts["sd"], 3)
    scores["fa"] += 0.5 * min(counts["fa"], 4) + 2.0 * min(counts["zwnj"], 2)
    scores["ar"] += 1.0 * min(counts["ar"], 4) + min(1.0, 0.25 * tashkeel)
    for k, c in counts.items():
        if c and len(ev.get(k, [])) < 1 and k in ev:
            ev[k].append(f"letters:{k}={c}")
    hits = {k: 0 for k in scores}
    for tok in tokens:
        if script_of_char(tok[0]) != "arabic" and not any(
            script_of_char(c) == "arabic" for c in tok
        ):
            continue
        raw = tok
        f = fold_arabic(raw)
        if _persian_verb(raw):
            hits["fa"] += 1
        for k in ("ur", "ar", "fa", "ps", "sd"):
            if f in _AR_WORDS[k] and not (k != "ur" and f in _AR_WORDS["ur"]):
                hits[k] += 1
                if len(ev[k]) < 4:
                    ev[k].append(f)
        if f in _PA_ONLY:
            hits["pa"] += 1
            if len(ev["pa"]) < 4:
                ev["pa"].append(f)
        if f.startswith("ال") and len(f) > 4:
            scores["ar"] += 0.5 if scores["ar"] < 6 else 0.0
    for k, h in hits.items():
        scores[k] += float(h) if k != "pa" else 1.5 * h
    # Punjabi (Shahmukhi) shares Urdu's letters: only its own words (two or more, more than Urdu's) tell it apart.
    if hits["pa"] < 2 or hits["pa"] <= hits["ur"]:
        scores["pa"] = 0.0
    else:
        scores["ur"] = max(0.0, scores["ur"] - 1.5 * min(counts["ur"], 4))
    best_k = max(scores, key=lambda k: scores[k])
    best = scores[best_k]
    second = max((v for k, v in scores.items() if k != best_k), default=0.0)
    if best < 1.0:
        return _Raw("und", 0.0, (), "no_markers", (), len(tokens))
    conf = min(1.0, best / 4.0) * (0.45 + 0.55 * best / (best + second))
    if best - second < 0.5:
        return _Raw("und", min(conf, 0.3), tuple(ev[best_k]), "balanced_mix", (), len(tokens))
    return _Raw(
        best_k, conf, tuple(ev[best_k]) or (f"score={best:.1f}",), "ok", (best_k,), len(tokens)
    )


# ---------------------------------------------------------------- one message


def _english_present(latin_tokens: list[str]) -> bool:
    """English words inside a message in another script: one function word or two vocabulary words."""
    lows = [t.lower() for t in latin_tokens]
    return any(w in _EN_FN for w in lows) or sum(w in _EN_VOCAB for w in lows) >= 2


def _analyse(text: str | None) -> _Raw:
    """Language of one message by itself (no pin): script by tokens, then the script's own analysis."""
    cleaned = _clean(text)
    tokens = _tokens(cleaned)
    by_script: dict[str, list[str]] = {}
    letters: dict[str, int] = {}
    for tok in tokens:
        sc_counts: dict[str, int] = {}
        for ch in tok:
            s = script_of_char(ch)
            if s:
                sc_counts[s] = sc_counts.get(s, 0) + 1
        if not sc_counts:
            continue
        top = max(sc_counts, key=lambda k: sc_counts[k])
        by_script.setdefault(top, []).append(tok)
        letters[top] = letters.get(top, 0) + sc_counts[top]
    if not by_script:
        return _Raw("und", 0.0, (), "no_letters", (), 0)
    if (
        all(
            fold_deva(fold_arabic(t)) in _AMBIG_NATIVE
            for t in tokens
            if script_of_char(t[0]) not in (None, "latin")
        )
        and "latin" not in by_script
    ):
        return _Raw(
            "und", 0.0, (), "ambiguous_answer", (), sum(len(v) for v in by_script.values()), True
        )
    dominant = max(by_script, key=lambda s: (len(by_script[s]), letters[s]))
    cjk = dominant in ("han", "kana", "hangul", "thai")
    # RLANG09 counts words as the person writes them: space-separated chunks ("Pouvez-vous" is one).
    chunks = sum(1 for c in cleaned.split() if any(script_of_char(ch) for ch in c))
    words = max(1, chunks) if not cjk else max(1, letters[dominant] // 2)
    others = [s for s in by_script if s != dominant]
    present_extra: list[str] = []
    if dominant == "latin":
        raw = _latin(tokens)
    elif dominant == "arabic":
        raw = _arabic_script(cleaned, tokens)
        lat_tokens = by_script.get("latin", [])
        if lat_tokens:
            if _english_present(lat_tokens):
                present_extra.append("en")
    else:
        code = SCRIPT_TO_CODE.get(dominant, "und")
        n = letters[dominant]
        raw = _Raw(
            code, min(1.0, n / 6.0) * 0.95 + 0.05, (f"script:{dominant}={n}",), "ok", (code,), words
        )
        lat_tokens = by_script.get("latin", [])
        if lat_tokens:
            if _english_present(lat_tokens):
                present_extra.append("en")
            lat = _latin(lat_tokens)
            if lat.code in ROMAN_INDIC and code == "hi":
                present_extra.append(lat.code)
    for s in others:
        if s == "latin":
            if dominant not in ("latin", "arabic", "devanagari"):
                lat = _latin(by_script["latin"])
                present_extra.extend(p for p in lat.present if p)
        elif s == "arabic":
            sec = _arabic_script(cleaned, by_script["arabic"])
            if sec.code != "und" and letters["arabic"] >= 3:
                present_extra.append(sec.code)
        else:
            c = SCRIPT_TO_CODE.get(s)
            if c and letters[s] >= 3:
                present_extra.append(c)
    present = tuple(dict.fromkeys([raw.code, *raw.present, *present_extra]))
    present = tuple(p for p in present if p and p != "und")
    return _Raw(
        raw.code, raw.confidence, raw.evidence, raw.reason, present, words, raw.all_ambiguous
    )


def _uncertain_decision(
    raw: _Raw, pin: tuple[str, str] | None, reason: str, short: bool
) -> LanguageDecision:
    code, script = pin if pin else ("und", "none")
    return LanguageDecision(
        code=code, script=script, confidence=raw.confidence, evidence=raw.evidence, uncertain=True,
        reason=reason, present=raw.present, detected=raw.code, short=short,
    )  # fmt: skip


def detect_message_language(
    text: str | None,
    *,
    history: Sequence[Any] = (),
    pinned: Any = None,
    voice: bool = False,
    asked: Iterable[str] = (),
) -> LanguageDecision:
    """Language and script of one owner message.

    `history`: the owner's earlier messages, oldest first (strings, HistoryTurn, dicts or message rows);
    used to work out the pin when `pinned` is None. `pinned`: the chat's pinned language (code, (code,
    script), PinState or LanguageDecision). `voice`: the text is a voice-note transcript (substantive
    however short, RLANG09). `asked`: clarifying-question keys already asked in this chat.

    A message under 3 words (and not a voice transcript) never decides: with a pin the pin comes back
    (`uncertain=True`, reason `short_keeps_pin`). A message that is longer but has no clear marker, is
    only fillers ("ok theek hai"), or is evenly mixed is `uncertain` too. Never raises."""
    try:
        return _detect(text, history, pinned, voice, tuple(asked))
    except (
        Exception
    ) as exc:  # pragma: no cover - defensive: pure code, but the contract is "never raise"
        return LanguageDecision("und", "none", 0.0, (type(exc).__name__,), True, "error")


def _detect(
    text: str | None, history: Sequence[Any], pinned: Any, voice: bool, asked: tuple[str, ...]
) -> LanguageDecision:
    pin = _pin_of(pinned)
    if pin is None and history:
        state = LanguagePin().pin(history)
        pin = (state.code, state.script) if state.basis != "default" else None
    raw = _analyse(text)
    short = raw.words < SUBSTANTIVE_WORDS and not voice
    if raw.code == "und" and raw.reason == "no_letters":
        return _uncertain_decision(raw, pin, "no_letters", True)
    if short:
        if pin:
            return _uncertain_decision(raw, pin, "short_keeps_pin", True)
        # Nothing to protect: a short message may still show its language, but only when it is sure.
        if raw.code == "und" or raw.confidence < CONFIDENT:
            return _uncertain_decision(
                raw, None, "short_no_pin" if raw.code == "und" else "low_confidence", True
            )
    elif raw.code == "und" or raw.confidence < CONFIDENT:
        reason = raw.reason if raw.code == "und" else "low_confidence"
        d = _uncertain_decision(raw, pin, reason, False)
        if (
            pin is None
            and raw.words >= SUBSTANTIVE_WORDS
            and CLARIFY_WHICH_LANGUAGE not in asked
            and raw.reason in ("no_markers", "balanced_mix")
        ):
            return LanguageDecision(
                **{**d.__dict__, "needs_clarification": True, "clarify_key": CLARIFY_WHICH_LANGUAGE}
            )
        return d
    code = raw.code
    reason = "ok"
    if code == "roman_hi_or_ur" and pin and pin[0] in ROMAN_INDIC:
        code, reason = (
            pin[0],
            "indic_family_unresolved_pin_kept",
        )  # honest: Hindi vs Urdu cannot be told, keep the pin
    elif (
        code in ROMAN_INDIC
        and pin
        and pin[0] in ROMAN_INDIC
        and pin[0] != "roman_hi_or_ur"
        and code == "roman_hi_or_ur"
    ):
        code = pin[0]
    ask = code in ASK_ONCE and CLARIFY_URDU_OR_ENGLISH not in asked
    return LanguageDecision(
        code=code, script=SCRIPT_OF_CODE.get(code, "latin"), confidence=round(raw.confidence, 3),
        evidence=raw.evidence, uncertain=False, reason=reason, present=raw.present, detected=raw.code,
        short=short, needs_clarification=ask, clarify_key=CLARIFY_URDU_OR_ENGLISH if ask else None,
    )  # fmt: skip


# ---------------------------------------------------------------- the pin


def _compatible(a: str, b: str) -> bool:
    """Same pin: equal, or both Roman Hindi/Urdu family members that are not told apart."""
    if a == b:
        return True
    return a in ROMAN_INDIC and b in ROMAN_INDIC and "roman_hi_or_ur" in (a, b)


class LanguagePin:
    """The chat's pinned language from the owner's earlier messages (RLANG09, RLANG02).

    Rule: walk the owner's messages oldest to newest; a message that is substantive (3 words or more,
    or a voice transcript) and clearly decided sets the pin; a short, ambiguous or unclear message
    never does; one stray word of another language cannot (the message's dominant language decides).
    `switch_after` is how many consecutive substantive messages in the new language it takes to move
    an existing pin: the spec says 1 ("detect per message, if the person switches pi switches",
    RLANG02), the default; 2 is the stricter "deliberate switch" some owners asked for and is a
    deviation from the spec that needs the owner's say-so."""

    def __init__(self, *, switch_after: int = 1) -> None:
        self.switch_after = max(1, int(switch_after))

    def pin(self, history: Sequence[Any]) -> PinState:
        try:
            return self._pin(history)
        except Exception:  # pragma: no cover
            return PinState("en", "latin", -1, "default")

    def _pin(self, history: Sequence[Any]) -> PinState:
        turns = list(history)[-MAX_HISTORY:]
        offset = len(list(history)) - len(turns)
        state: PinState | None = None
        pending_code = ""
        pending = 0
        for i, item in enumerate(turns):
            t = _turn(item)
            if t is None:
                continue
            raw = _analyse(t.text)
            substantive = raw.words >= SUBSTANTIVE_WORDS or t.voice
            if not substantive or raw.code == "und" or raw.confidence < CONFIDENT:
                continue
            code = raw.code
            idx = i + offset
            if state is None:
                state = PinState(code, SCRIPT_OF_CODE.get(code, "latin"), idx, "message")
                continue
            if _compatible(code, state.code):
                if state.code == "roman_hi_or_ur" and code != "roman_hi_or_ur":
                    state = PinState(code, state.script, idx, "message")
                else:
                    state = PinState(state.code, state.script, idx, "message")
                pending = 0
                continue
            pending = pending + 1 if code == pending_code else 1
            pending_code = code
            if pending >= self.switch_after:
                state = PinState(code, SCRIPT_OF_CODE.get(code, "latin"), idx, "message")
                pending = 0
        return state or PinState("en", "latin", -1, "default")


# ---------------------------------------------------------------- reply language


def reply_plan(
    decision: LanguageDecision,
    pinned: Any = None,
    history: Sequence[Any] = (),
    *,
    switch_after: int = 1,
) -> ReplyPlan:
    """What pi answers in. A clear substantive message sets it (RLANG02); an uncertain one keeps the pin;
    with no pin and nothing known the default is English (spec 2.5: English default).

    Special cases from the spec: Punjabi, Sindhi and Pashto are answered in Roman Urdu (Latin script)
    or Urdu (Arabic script) and the question "Urdu ya English mein baat karein?" is asked once
    (`ask_key`); Tagalog, Malayalam, Tamil, Bengali and other UAE-workforce languages get English plus
    one line offering to continue in English (`offer_english`), noted in the contact profile."""
    try:
        return _plan(decision, pinned, history, switch_after)
    except Exception:  # pragma: no cover
        return ReplyPlan("en", "latin")


def _plan(
    decision: LanguageDecision, pinned: Any, history: Sequence[Any], switch_after: int
) -> ReplyPlan:
    pin = _pin_of(pinned)
    if pin is None and history:
        state = LanguagePin(switch_after=switch_after).pin(history)
        pin = (state.code, state.script) if state.basis != "default" else None
    if decision.uncertain or decision.code == "und":
        base = pin or _pin_of(decision) or ("en", "latin")
        return _from_code(base[0], base[1], decision, pin)
    code = decision.code
    if switch_after > 1 and pin and not _compatible(code, pin[0]) and not _confirmed(code, history):
        return _from_code(
            pin[0], pin[1], decision, pin
        )  # one message in a new language: wait for the second
    if code == "roman_hi_or_ur":
        if pin and pin[0] in ROMAN_INDIC:
            return _from_code(
                pin[0] if pin[0] != "roman_hi_or_ur" else "roman_ur", "latin", decision, pin
            )
        return _from_code("roman_ur", "latin", decision, pin)
    return _from_code(code, SCRIPT_OF_CODE.get(code, decision.script), decision, pin)


def _confirmed(code: str, history: Sequence[Any]) -> bool:
    """The owner's latest earlier substantive message was already in this language (a second one)."""
    for item in reversed(list(history)[-MAX_HISTORY:]):
        t = _turn(item)
        if t is None:
            continue
        raw = _analyse(t.text)
        if (
            (raw.words >= SUBSTANTIVE_WORDS or t.voice)
            and raw.code != "und"
            and raw.confidence >= CONFIDENT
        ):
            return _compatible(raw.code, code)
    return False


def _from_code(
    code: str, script: str, decision: LanguageDecision, pin: tuple[str, str] | None
) -> ReplyPlan:
    if code == "roman_hi_or_ur":
        code = "roman_ur"  # Hindi vs Urdu not told apart: the platform answers Roman Urdu
    if code in ASK_ONCE:
        ask = decision.clarify_key if decision.code == code else None
        return ReplyPlan(
            "ur" if script == "arabic" else "roman_ur",
            "arabic" if script == "arabic" else "latin",
            ask,
            False,
            f"owner_language={code}",
        )
    if code in ENGLISH_OFFER:
        return ReplyPlan("en", "latin", None, True, f"owner_language={code}")
    if code == "pa_guru":
        return ReplyPlan("en", "latin", None, True, "owner_language=pa_gurmukhi")
    return ReplyPlan(
        code,
        SCRIPT_OF_CODE.get(code, script),
        decision.clarify_key if decision.code == code else None,
    )


def reply_language_for(
    decision: LanguageDecision,
    pinned: Any = None,
    history: Sequence[Any] = (),
    *,
    switch_after: int = 1,
) -> tuple[str, str]:
    """(code, script) pi answers in: an Urdu-script owner gets Urdu script, a Roman Urdu owner Roman
    Urdu; a short or unclear message keeps the pin. See `reply_plan` for the Punjabi/Sindhi/Pashto
    question and the English offer."""
    plan = reply_plan(decision, pinned, history, switch_after=switch_after)
    return plan.code, plan.script


def fixed_line_key(code: str, script: str = "latin") -> str:
    """The key of the fixed lines in fixed_lines.py (en, roman_ur, ur, ar, hi, fr, fa, es) for a reply
    code. Roman Hindi gets the Roman Urdu lines (as today: there are no Roman Hindi lines); a language
    with no lines gets English, or Urdu/Roman Urdu for Punjabi, Sindhi and Pashto."""
    if code in ("en", "roman_ur", "ur", "ar", "hi", "fr", "fa", "es"):
        return code
    if code in ("roman_hi", "roman_hi_or_ur"):
        return "roman_ur"
    if code in ASK_ONCE:
        return "ur" if script == "arabic" else "roman_ur"
    return "en"


# ---------------------------------------------------------------- business terms


def _build_terms() -> tuple[dict[str, str], dict[str, str], list[str]]:
    exact: dict[str, str] = {}
    folded_seen: dict[str, str | None] = {}
    collisions: list[str] = []
    never = _set(lex.NEVER_MAP)
    for line in lex.BUSINESS_TERMS:
        if ":" not in line:
            continue
        concept, variants = line.split(":", 1)
        concept = concept.strip()
        for v in variants.split():
            if "-" in v or v.lower() in never or any(c.isdigit() for c in v):
                continue
            key = _term_key(v)
            if not key:
                continue
            old = exact.get(key)
            if old is not None and old != concept:
                collisions.append(f"{key}: {old} / {concept}")
                continue
            exact[key] = concept
            if script_of_char(v[0]) == "latin":
                fk = fold_latin(key)
                if fk in folded_seen and folded_seen[fk] != concept:
                    folded_seen[fk] = None
                else:
                    folded_seen[fk] = concept
        exact.setdefault(_term_key(concept), concept)
    return exact, {k: v for k, v in folded_seen.items() if v is not None}, collisions


def _term_key(token: str) -> str:
    t = unicodedata.normalize("NFKC", token).strip("'")
    t = fold_deva(fold_arabic(t))
    return t.lower() if t and script_of_char(t[0]) == "latin" else t


_TERMS, _TERMS_FOLDED, TERM_COLLISIONS = _build_terms()
_NEVER = _set(lex.NEVER_MAP)
_AR_PREFIXES = ("وال", "بال", "ال", "لل")


def _lookup_term(token: str) -> str | None:
    if any(c.isdigit() for c in token):
        return None
    key = _term_key(token)
    if key in _NEVER or token.lower() in _NEVER:
        return None
    hit = _TERMS.get(key)
    if hit:
        return hit
    if key and script_of_char(key[0]) == "latin":
        if len(key) > 3 and key.endswith("s") and (h := _TERMS.get(key[:-1])):
            return h
        if len(key) > 4 and key.endswith("es") and (h := _TERMS.get(key[:-2])):
            return h
        f = fold_latin(key)
        if f in _TERMS_FOLDED and f not in _EN_FN:
            return _TERMS_FOLDED[f]
    elif key:
        for p in _AR_PREFIXES:
            if key.startswith(p) and len(key) > len(p) + 1 and (h := _TERMS.get(key[len(p) :])):
                return h
    return None


def business_term_matches(
    text: str | None, language: str | None = None
) -> list[tuple[int, str, str]]:
    """(token index, original token, concept id) for every business term found. `language` is accepted for
    symmetry with the other helpers; matching is by spelling in any script, so it is not needed."""
    try:
        return [(i, t, c) for i, t in enumerate(_tokens(_clean(text))) if (c := _lookup_term(t))]
    except Exception:  # pragma: no cover
        return []


def business_term_normalise(text: str | None, language: str | None = None) -> list[str]:
    """The text as tokens, each business term replaced by its concept id (order, delivery, stock, staff,
    customer, payment, salary...), every other token returned exactly as written. Negations, numbers
    and quantity words are never mapped, so "no stock" stays "no stock" and "5 orders" stays "5 order".
    Plurals fold to the singular concept id. Never raises."""
    try:
        return [_lookup_term(t) or t for t in _tokens(_clean(text))]
    except Exception:  # pragma: no cover
        return []


# ---------------------------------------------------------------- correction and withdrawal cues

_L = r"(?<![\ẁ-ͯ؀-ۿऀ-ॿ])"
_R = r"(?![\ẁ-ͯ؀-ۿऀ-ॿ])"

_CUE_SOURCES: dict[str, dict[str, tuple[str, ...]]] = {
    "en": {
        "withdrawal": (
            r"i take (?:that|it|this) back",
            r"take that back",
            r"forget (?:it|that|the rest|everything|about (?:it|that)|what i (?:said|wrote))",
            r"never ?mind",
            r"ignore (?:that|what i (?:said|wrote)|my (?:last|previous))",
            r"scratch that",
            r"strike that",
            r"disregard (?:that|what i|my (?:last|previous))",
            r"cancel that",
            r"let'?s drop (?:it|that)",
            r"drop it",
            r"pretend i (?:never )?said",
        ),
        "correction": (
            r"i (?:meant|mean|misspoke|mistyped|typed (?:it )?wrong|said (?:it )?wrong|got (?:that|it) wrong|wrote (?:it )?wrong)",
            r"sorry,? (?:i )?(?:meant|mean|it(?:'s| is| was)|that was)",
            r"let me (?:correct|fix|rephrase)",
            r"correction",
            r"to correct (?:myself|that)",
            r"typo",
            r"no,? wait",
            r"wait,? (?:no|actually)",
            r"actually,? (?:it|that|i|we)",
            r"i was wrong",
            r"my (?:mistake|bad)",
            r"i should have said",
            r"oops",
            r"i said (?:it )?wrong",
        ),
        "rejection": (
            r"that(?:'s| is) (?:not|wrong|incorrect|false)",
            r"no,? that(?:'s| is) not",
            r"not what i (?:said|meant|asked)",
            r"you (?:got|have) (?:it|that) wrong",
            r"i (?:never|didn'?t|did not) (?:say|said)",
            r"you (?:mis)?understood",
            r"you misunderstood",
            r"that isn'?t (?:right|true)",
            r"that is not (?:right|true)",
        ),
        "contradiction": (
            r"on the contrary",
            r"the opposite",
            r"the other way (?:round|around)",
            r"the reverse",
            r"no longer (?:true|the case)",
            r"not anymore",
            r"that (?:has )?changed",
            r"earlier i said .{0,40}\bbut\b",
            r"i said .{0,30} before,? but",
        ),
    },
    "roman": {
        "withdrawal": (
            r"(?:wo|woh|ye|yeh|us|ye baat|wo baat|woh baat|yeh baat) (?:baat )?(?:wapas|vapas) (?:le|lay|leta|leti|le raha|le rahi|lena)",
            r"(?:baat )?(?:wapas|vapas) le (?:raha|rahi|leta|leti) h(?:oon|un|u)",
            r"bh(?:o|u)ol jao",
            r"bh(?:o|u)ol jayen",
            r"bh(?:o|u)ol jaiye",
            r"bh(?:o|u)ol jaen",
            r"bh(?:o|u)l (?:jao|jayen|jaiye)",
            r"ch(?:h)?or (?:do|dein|den|dijiye|dijye)",
            r"ch(?:h)?odo",
            r"reh?ne (?:do|dein|den)",
            r"rahne (?:do|dein|den)",
            r"ignore kar(?:o|en|ein|iye|do)",
            r"cancel kar(?:o|en|ein|iye|do|dein)",
            r"jane do",
            r"janay do",
            r"jaane do",
            r"never ?mind",
            r"forget it",
        ),
        "correction": (
            r"(?:maine|main ?ne|mene|maene|maine) (?:galat|ghalat|galt) (?:kaha|likha|bataya|bola|likh diya|bata diya)",
            r"(?:galti|ghalti|ghalati) se (?:likh|likha|keh|kaha|bol|bata)",
            r"mera matlab",
            r"mera maqsad",
            r"mera kehna (?:ye|yeh) tha",
            r"mujhe kehna tha",
            r"(?:galti|ghalti) ho gayi",
            r"(?:galti|ghalti) hogayi",
            r"darasal",
            r"dar asal",
            r"asal mein",
            r"sahi (?:ye|yeh) hai",
            r"typo",
            r"oops",
            r"sorry,? (?:mera|main|maine)",
            r"correction",
            r"nahi nahi,? (?:mera|ye|yeh)",
        ),
        "rejection": (
            r"(?:ye|yeh) (?:baat )?(?:sahi|theek|durust|sach) nahi",
            r"(?:ye|yeh) (?:galat|ghalat) hai",
            r"aisa nahi hai",
            r"maine (?:ye|yeh|aisa|wo|woh|aisay) nahi kaha",
            r"maine aisa kab kaha",
            r"(?:ye|yeh) mera matlab nahi tha",
            r"mera matlab (?:ye|yeh) nahi tha",
            r"aap ne galat samjha",
            r"galat samjh",
            r"(?:ye|yeh) wo nahi (?:jo|ke)",
        ),
        "contradiction": (
            r"ulta",
            r"ulat",
            r"bilkul ulta",
            r"pehle (?:maine )?kaha tha .{0,40}(?:lekin|magar|par)",
            r"ab (?:aisa|ye|yeh|wo|woh) (?:baat )?nahi",
            r"halat badal",
            r"ab (?:aisa )?nahi raha",
            r"is ke bar aks",
            r"bar aks",
        ),
    },
    "ur": {
        "withdrawal": (
            r"(?:وہ|یہ) بات واپس",
            r"بھول جائیں",
            r"بھول جاؤ",
            r"بھول جایے",
            r"چھوڑیں",
            r"چھوڑ دیں",
            r"چھوڑ دو",
            r"رہنے دیں",
            r"رہنے دو",
            r"نظر انداز",
            r"منسوخ کر",
            r"جانے دیں",
            r"جانے دو",
        ),
        "correction": (
            r"میں نے غلط (?:کہا|لکھا|بتایا)",
            r"غلطی سے",
            r"میرا مطلب",
            r"نہیں میرا مطلب",
            r"میرا مقصد",
            r"مجھے کہنا تھا",
            r"دراصل",
            r"اصل میں",
            r"ٹائپو",
            r"غلطی ہو گئی",
            r"غلطی ہوگئی",
            r"درستگی",
            r"تصحیح",
        ),
        "rejection": (
            r"یہ (?:درست|صحیح|ٹھیک) نہیں",
            r"یہ غلط ہے",
            r"ایسا نہیں ہے",
            r"میں نے (?:یہ|ایسا|ایسے) نہیں کہا",
            r"یہ میرا مطلب نہیں",
            r"میرا مطلب یہ نہیں",
            r"آپ نے غلط سمجھا",
        ),
        "contradiction": (
            r"الٹا",
            r"الٹ ",
            r"برعکس",
            r"پہلے .{0,40}(?:لیکن|مگر)",
            r"اب ایسا نہیں",
            r"حالات بدل",
        ),
    },
    "ar": {
        "withdrawal": (
            r"أسحب كلامي",
            r"اسحب كلامي",
            r"انس(?:ى|وا)? (?:ذلك|ما قلت|الأمر|الامر)",
            r"تجاهل(?:ي|وا)? (?:ما|ذلك)",
            r"لا تهتم",
            r"دعك من",
            r"الغ(?:ي)? (?:ذلك|هذا)",
            r"ألغ (?:ذلك|هذا)",
            r"تراجعت",
            r"أتراجع",
            r"اتراجع",
        ),
        "correction": (
            r"قصدت",
            r"أقصد",
            r"اقصد",
            r"قصدي",
            r"عفوا",
            r"تصحيح",
            r"أخطأت",
            r"اخطات",
            r"كان خطأ",
            r"كتبت خطأ",
            r"قلت خطأ",
            r"سهوا",
            r"بالخطأ",
            r"في الحقيقة",
            r"الصحيح هو",
            r"الصواب",
        ),
        "rejection": (
            r"ليس هذا ما قصدته",
            r"ليس هذا ما قلته",
            r"هذا (?:غير )?(?:صحيح|خطأ)",
            r"ليس صحيح",
            r"لم أقل ذلك",
            r"لم اقل ذلك",
            r"فهمت خطأ",
            r"فهمتني خطأ",
            r"فهمتم خطأ",
        ),
        "contradiction": (
            r"بالعكس",
            r"على العكس",
            r"العكس",
            r"لم يعد",
            r"تغير الوضع",
            r"كنت قلت .{0,40}لكن",
        ),
    },
    "hi": {
        "withdrawal": (
            r"(?:वो|वह|यह|ये) बात वापस",
            r"भूल जाइए",
            r"भूल जाओ",
            r"भूल जाएं",
            r"छोड़िए",
            r"छोड़ दीजिए",
            r"छोड़ दो",
            r"रहने दीजिए",
            r"रहने दो",
            r"नज़रअंदाज़",
            r"नजरअंदाज",
            r"रद्द कर",
        ),
        "correction": (
            r"मैंने (?:गलत|ग़लत) (?:कहा|लिखा|बताया)",
            r"(?:गलती|ग़लती) से",
            r"मेरा मतलब",
            r"नहीं,? मेरा मतलब",
            r"मेरा कहने का मतलब",
            r"दरअसल",
            r"असल में",
            r"सुधार",
            r"टाइपो",
            r"माफ़? ?कीजिए",
            r"गलती हो गई",
            r"गलती हो गयी",
        ),
        "rejection": (
            r"यह (?:सही|ठीक) नहीं",
            r"ये (?:सही|ठीक) नहीं",
            r"यह गलत है",
            r"ये गलत है",
            r"ऐसा नहीं है",
            r"मैंने (?:यह|ये|ऐसा) नहीं कहा",
            r"मेरा मतलब (?:यह|ये) नहीं था",
            r"आपने गलत समझा",
        ),
        "contradiction": (r"उल्टा", r"इसके उलट", r"पहले .{0,40}(?:लेकिन|मगर|पर)\b", r"अब ऐसा नहीं"),
    },
}
_KINDS = ("withdrawal", "correction", "rejection", "contradiction")  # priority order
_REPORTED = re.compile(
    r"(?:he|she|they|someone|customer|client|manager) (?:said|says|told|wrote)\W*$|(?:usne|us ne|unhon ne|woh keh raha|wo keh raha)(?: kaha| keha)?\W*$"
    r"|(?:اس نے|انہوں نے|وہ کہتا|وہ کہہ)[^\n]{0,6}$|(?:قال|قالت|قالوا)\W*$|(?:उसने|उन्होंने) (?:कहा)?\W*$",
    re.IGNORECASE,
)


def _fold_pattern(src: str) -> str:
    return fold_deva(fold_arabic(src))


def _compile() -> dict[str, dict[str, list[re.Pattern[str]]]]:
    out: dict[str, dict[str, list[re.Pattern[str]]]] = {}
    for lang, kinds in _CUE_SOURCES.items():
        out[lang] = {}
        for kind, pats in kinds.items():
            out[lang][kind] = [
                re.compile(
                    _L + "(?:" + _fold_pattern(p) + ")" + (_R if not p.endswith(" ") else ""),
                    re.IGNORECASE,
                )
                for p in pats
            ]
    return out


_CUES = _compile()
_LANG_TO_CUE = {
    "en": ("en",),
    "roman_ur": ("roman",),
    "roman_hi": ("roman",),
    "roman_hi_or_ur": ("roman",),
    "ur": ("ur",),
    "ar": ("ar",),
    "hi": ("hi",),
    "fa": ("ar", "ur"),
    "ps": ("ur",),
    "sd": ("ur",),
    "pa": ("ur",),
}


@dataclass(frozen=True)
class CueResult:
    kind: str | None
    evidence: tuple[str, ...]
    kinds: tuple[str, ...] = ()
    language: str | None = None

    @property
    def found(self) -> bool:
        return self.kind is not None


def _cue_text(text: str | None) -> str:
    t = unicodedata.normalize("NFKC", (text or "")[:2000])
    t = fold_deva(fold_arabic(t)).lower()
    t = _SQUEEZE.sub(r"\1", t)  # a stretch of 3 or more is never real spelling
    return " ".join(t.split())


def has_correction_or_withdrawal_cue(text: str | None, language: str | None = None) -> CueResult:
    """Does the owner correct, withdraw, reject or contradict something they or pi said? `language` is a
    code (en, roman_ur, ur, ar, hi...) or None to try every language. Returns the strongest kind
    (withdrawal, then correction, rejection, contradiction), all kinds found, and the matched words.
    A cue right after "he said", "usne kaha", "قال" is somebody else's speech and is skipped. The flow
    uses it to update the current state while keeping the history: it never deletes anything."""
    try:
        t = _cue_text(text)
        groups = _LANG_TO_CUE.get(language or "", tuple(_CUES)) if language else tuple(_CUES)
        found: dict[str, list[str]] = {}
        for grp in groups:
            for kind in _KINDS:
                for pat in _CUES[grp][kind]:
                    for m in pat.finditer(t):
                        if _REPORTED.search(t[max(0, m.start() - 14) : m.start()]):
                            continue
                        found.setdefault(kind, []).append(m.group(0))
                        break
        if not found:
            return CueResult(None, (), (), language)
        kinds = tuple(k for k in _KINDS if k in found)
        return CueResult(kinds[0], tuple(dict.fromkeys(found[kinds[0]]))[:4], kinds, language)
    except Exception:  # pragma: no cover
        return CueResult(None, (), (), language)
