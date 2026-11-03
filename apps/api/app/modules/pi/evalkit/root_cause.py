"""Root-cause scorer (L2-2, measure M1): scripted criteria for a saved cause record, no model, no
database, no network. A scripted run tests this code and the labelled cases, never the quality of
a model. The cases are agent-drafted and unreviewed (`cases/root_cause.json`).

A `record` is what pi saved or said for one problem:

    {"causes": [{"text", "status", "evidence": {"words": [..]}, "shown_as": "fact" | "hypothesis",
                 "confirmed_by": owner message index}],
     "evidence_for": [owner phrases], "evidence_against": [owner phrases],
     "factors": [contributing factors, plain words],
     "question": "the one question asked",
     "reply": "the reply text, when the record carries it"}

`status` is the B2a vocabulary of `problem_fields` (`pi_inferred`, `owner_said`, `confirmed`).

The scorer never raises on a malformed record: a wrong shape in any field is the hard flag
`malformed_record` (the fields are listed in `malformed_fields`), the field is ignored and the rest
is scored. Lists and strings past the caps below are cut and flagged `oversized_record`.

What is checked, per case (`expected` in the case file):

  hard flags (a flag is raised whatever else is right)
    unsupported_confirmed          an owner_said or confirmed cause the owner's words do not
                                   support:
                                   every evidence phrase must occur, as whole tokens in order,
                                   in one
                                   owner message; the cause must share at least one CONTENT
                                   word with
                                   the evidence; a cause of more than 3 content words needs at least
                                   half of them in the evidence or the owner's messages. Content
                                   words are 3+ letters (any digit counts) and not in the function-
                                   word list for English, Roman Urdu, Urdu, Hindi and Arabic
    confirmed_without_owner        a confirmed cause without `confirmed_by`, the index of an owner
                                   message (spec 3.5: only the owner's confirmation makes a fact)
    inferred_shown_as_fact         a pi_inferred cause with any `shown_as` other than a hypothesis
                                   label (hypothesis, guess, possible, maybe, shayad ...), or whose
                                   text is in the record's `reply` in a sentence with no hedge word
    unsupported_short_cause        with unsupported_confirmed: the cause is rejected only because
                                   its shared words are 2 letters (kept strict; the flag marks
                                   it "unknown", not plainly unsupported)
    unlabelled_inference           a pi_inferred cause with no explicit hypothesis label: neither a
                                   fact nor a declared hypothesis (allowed only when labelled)
    unknown_status                 a status outside the vocabulary
    trap_cause_stated              a cause stated as fact that contains a forbidden word (a
                                   plausible
                                   cause the owner never gave, or one the owner corrected away); a
                                   labelled hypothesis is not a stated cause
    cause_invented_without_facts   in a case with too few facts: a cause that is not a labelled
                                   hypothesis (status pi_inferred and an explicit hypothesis label)
    evidence_not_from_owner        an evidence_for or evidence_against phrase the owner did
                                   not write
    malformed_record, oversized_record   see above
  checks (False when expected and missing, None when not expected)
    cause_found       a SUPPORTED stated cause names the owner's cause
    both_sides        evidence for and against both present
    factors_named     how many expected factor groups are named
    insufficient_ok   one targeted question, and no cause other than a labelled hypothesis
    question_ok       exactly one question mark, as the last character

Matching: Unicode is normalised (NFKC), case-folded, digits of every script made ASCII; Arabic
marks (tashkeel, tatweel) are removed and alef, yeh, kaf and heh forms unified (Persian and Urdu
forms too); the Devanagari nukta and joiners are removed.

Limits, stated plainly: matching is by tokens, so a reworded cause is missed and a content word
the owner used elsewhere can count as support; the half-of-content-words rule is a heuristic
and the function-word lists are not complete; `shown_as` and hedge words are matched against short
lists; the scorer cannot tell whether a stated cause is true, only whether the owner's words
support it.

Output is numbers only. The decision on any threshold is the owner's; nothing here compares a
result with one. A group with fewer than `MIN_CASES` cases is "not yet measured".

Run from apps/api:  python -m app.modules.pi.evalkit.root_cause [--cases FILE]
"""

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.modules.pi import problem_fields
from app.modules.pi.evalkit import scorers, splits

CASES = Path(__file__).with_name("cases") / "root_cause.json"
MIN_CASES = scorers.MIN_CASES
LANGUAGES = ("en", "roman_ur", "ur", "ar", "hi")
STATUSES = problem_fields.CAUSE_STATUSES
OWNER_STATUSES = problem_fields.OWNER_STATUSES
CAUSE_STATED = "cause_stated"
INSUFFICIENT = "insufficient_evidence"
QUESTION_MARKS = ("?", "؟", "？")  # Latin, Arabic and Urdu, full-width
_SPLIT = re.compile(r"[\s.,;:!?()\"'،۔।؛؟—–…]+")
_SENTENCE = re.compile(r"[.!?\n؟۔।？]+")
MIN_WORD = 3
HALF_RULE_OVER = 3  # a cause of more content words than this needs half of them supported
# caps on what one record may carry; past them the record is cut and flagged
MAX_CAUSES = 20
MAX_ITEMS = 50
MAX_CHARS = 2000

_DROP = {0x0640} | set(range(0x064B, 0x0660)) | {0x0670} | set(range(0x06D6, 0x06EE))
_DROP |= {0x093C, 0x200C, 0x200D, 0x200E, 0x200F}
_UNIFY = str.maketrans(
    {
        "أ": "ا",  # alef with hamza above
        "إ": "ا",  # alef with hamza below
        "آ": "ا",  # alef with madda
        "ٱ": "ا",  # alef wasla
        "ى": "ي",  # alef maqsura
        "ی": "ي",  # Persian and Urdu yeh
        "ے": "ي",  # Urdu yeh barree
        "ک": "ك",  # Persian and Urdu kaf
        "ة": "ه",  # teh marbuta
        "ہ": "ه",  # Urdu heh goal
        "ھ": "ه",  # Urdu heh doachashmee
        "ۃ": "ه",
    }
)


def normalise(text: Any) -> str:
    folded = unicodedata.normalize("NFKC", str(text or "")).casefold()
    out = []
    for ch in folded:
        code = ord(ch)
        if code in _DROP:
            continue
        out.append(str(unicodedata.digit(ch)) if unicodedata.category(ch) == "Nd" else ch)
    return "".join(out).translate(_UNIFY)


def tokens(text: Any) -> list[str]:
    """Normalised tokens of any script; Latin, Arabic, Urdu and Devanagari punctuation removed."""
    return [t.replace("\x00", "") for t in _SPLIT.split(normalise(text)) if t]


def _norm_set(words: str) -> frozenset[str]:
    return frozenset(normalise(w) for w in words.split())


STOP = _norm_set(
    # English
    "a an the of to in on at by for from with and or but is are was were be been it its this that "
    "these those i we you he she they my our your their me us them as if so not no do does did "
    "have has had will would can could may might shall should one two also very just than then "
    "there here which who what when where why how because since while about into over under up "
    "down out only any some all each own more most such too don isn aren wasn doesn didn "
    # Roman Urdu
    "hai hain ho hota hotay hote hoti tha thi thay ka ki ke ko ne se mein me par pe aur ya bhi "
    "kyun kyunke kyunki liye lye us ye woh wo yeh hum humne hamare hamari hamara mera meri mere "
    "aap apni apna apne nahi nahin jo jab kab jahan jaha sirf bohat bahut kuch koi aik ek gayi "
    "gaya gaye gayin kar kia kiya raha rahi rahe sakta sakti tak wala wali wale "
    # Urdu
    "ہی ہے ہیں ہو تھا تھی تھے کا کی کے کو نے سے میں پر اور یا بھی کہ جو یہ وہ ایک اس ان ہم "
    "ہمارے ہماری ہمارا کیونکہ صرف نہیں کیا ہوتا ہوتی ہوتے رہا رہی رہے جاتی جاتا جاتے گیا گئی "
    "گئے کر کرتے والا والی والے "
    # Hindi
    "है हैं था थी थे का की के को ने से में पर और या भी कि जो यह वह एक इस उस हम हमारे हमारी "
    "हमारा क्योंकि सिर्फ़ नहीं कोई कुछ तो रहा रही रहे करना होता होती होते वाला वाली वाले "
    # Arabic
    "في من على إلى الى عن مع أن ان إن لأن لان هو هي هذا هذه ذلك التي الذي الذين و أو ثم لا لم "
    "لن قد كان كانت يكون عند فقط كل بعد قبل ما هل بين حتى"
)
HYPOTHESIS_LABELS = _norm_set(
    "hypothesis hypothetical guess possible possibly maybe might assumption unconfirmed "
    "shayad mumkin ممکن شاید शायद संभव ربما محتمل"
) | {normalise("may be")}
HEDGES = (
    "may",
    "might",
    "maybe",
    "perhaps",
    "possibly",
    "possible",
    "could",
    "guess",
    "hypothesis",
    "seems",
    "suspect",
    "likely",
    "i think",
    "not sure",
    "shayad",
    "ho sakta",
    "ho sakti",
    "mumkin",
    "شاید",
    "ممکن",
    "हो सकता",
    "शायद",
    "संभव",
    "ربما",
    "يمكن",
    "محتمل",
)
_HEDGES = tuple(" ".join(tokens(h)) for h in HEDGES)


def _padded(token_list: list[str]) -> str:
    return "\x00" + "\x00".join(token_list) + "\x00"


def owner_index(messages: list[str]) -> list[str]:
    """One padded token string per owner message, for `in_owner_text` (build it once per case)."""
    return [_padded(tokens(m)) for m in messages]


def in_owner_text(phrase: Any, messages: list[str], index: list[str] | None = None) -> bool:
    """The phrase occurs in one owner message as whole tokens, in order. One substring search per
    message over a padded token string, so the cost is linear in the size of the text."""
    wanted = tokens(phrase)
    if not wanted:
        return False
    needle = _padded(wanted)
    return any(needle in message for message in (index or owner_index(messages)))


def content_words(text: Any, min_len: int = MIN_WORD) -> set[str]:
    """Words that carry meaning: `min_len`+ letters (any digit) and not a function word."""
    return {t for t in tokens(text) if t not in STOP and (len(t) >= min_len or t.isdigit())}


def _has_any(text: Any, keywords: list[str]) -> bool:
    """Any keyword occurs in the text as whole tokens, in order (never inside a longer word)."""
    padded = _padded(tokens(text))
    return any(_padded(tokens(k)) in padded for k in keywords if tokens(k))


def _supported(
    cause: dict[str, Any],
    phrases: list[str],
    messages: list[str],
    index: list[str],
    min_len: int = MIN_WORD,
) -> bool:
    """Whether the owner's words support this cause (see the module docstring for the rule)."""
    if not phrases or not all(in_owner_text(p, messages, index) for p in phrases):
        return False
    evidence = set().union(*(content_words(p, min_len) for p in phrases))
    own = content_words(cause.get("text"), min_len)
    if not own & evidence:
        return False
    if len(own) > HALF_RULE_OVER:
        known = evidence | set().union(*(content_words(m, min_len) for m in messages))
        return 2 * len(own & known) >= len(own)
    return True


_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_CLOSERS = (
    " "
    + chr(9)
    + chr(10)
    + chr(13)
    + "\"'`)]}"
    + "".join(
        chr(c)
        for c in (0xBB, 0x201D, 0x2019, 0x203A, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0xFEFF)
    )
)


def _one_question(text: Any) -> bool:
    """Exactly one question mark, and it is the last thing said. A URL (with its query string),
    closing quotes or brackets and zero-width characters after it do not count."""
    folded = _URL.sub(" ", text).rstrip(_CLOSERS) if isinstance(text, str) else ""
    return (
        bool(folded)
        and sum(folded.count(mark) for mark in QUESTION_MARKS) == 1
        and folded.endswith(QUESTION_MARKS)
    )


def _label(value: Any) -> str | None:
    """How a cause was shown: "hypothesis" for an explicit hypothesis label, "fact" for any other
    value, None when nothing was recorded."""
    if not isinstance(value, str) or not value.strip():
        return None
    return "hypothesis" if " ".join(tokens(value)) in HYPOTHESIS_LABELS else "fact"


def _shown_in_reply(text: Any, reply: str) -> bool:
    """The cause appears in a sentence of the reply that has no hedge word."""
    own = content_words(text)
    if not own:
        return False
    for sentence in _SENTENCE.split(reply):
        words = tokens(sentence)
        if not words or 2 * len(own & set(words)) < len(own):
            continue
        padded = _padded(words)
        if not any(_padded(h.split()) in padded for h in _HEDGES if h):
            return True
    return False


class _Clean:
    """The record as the scorer may read it: only well-shaped fields, plus what was malformed."""

    def __init__(self, record: Any) -> None:
        self.bad: list[str] = []
        self.big = False
        if not isinstance(record, dict):
            self.bad.append("record")
            record = {}
        self.causes: list[dict[str, Any]] = []
        self.bad_causes = False
        raw = record.get("causes", [])
        if not isinstance(raw, list):
            self.bad.append("causes")
            self.bad_causes = True
            raw = []
        if len(raw) > MAX_CAUSES:
            self.big = True
        for i, item in enumerate(raw[:MAX_CAUSES]):
            if not isinstance(item, dict):
                self.bad.append(f"causes[{i}]")
                self.bad_causes = True
                continue
            self.causes.append(self._cause(i, item))
        self.evidence_for = self._strings(record, "evidence_for")
        self.evidence_against = self._strings(record, "evidence_against")
        self.factors = self._strings(record, "factors")
        self.question = record.get("question", "")
        if not isinstance(self.question, str):
            self.bad.append("question")
            self.question = ""
        self.reply = record.get("reply", "")
        if not isinstance(self.reply, str):
            self.bad.append("reply")
            self.reply = ""
        self._cut_text()

    def _cut_text(self) -> None:
        if len(self.question) > MAX_CHARS or len(self.reply) > MAX_CHARS:
            self.big = True
        self.question, self.reply = self.question[:MAX_CHARS], self.reply[:MAX_CHARS]

    def _strings(self, source: dict[str, Any], key: str, label: str = "") -> list[str]:
        label = label or key
        value = source.get(key, [])
        if not isinstance(value, list):
            self.bad.append(label)
            return []
        if len(value) > MAX_ITEMS:
            self.big = True
        out = []
        for i, item in enumerate(value[:MAX_ITEMS]):
            if not isinstance(item, str):
                self.bad.append(f"{label}[{i}]")
                continue
            self.big = self.big or len(item) > MAX_CHARS
            out.append(item[:MAX_CHARS])
        return out

    def _cause(self, i: int, item: dict[str, Any]) -> dict[str, Any]:
        text = item.get("text", "")
        if not isinstance(text, str):
            self.bad.append(f"causes[{i}].text")
            text = ""
        evidence = item.get("evidence", {})
        words: list[str] = []
        if evidence not in ({}, None):
            if not isinstance(evidence, dict):
                self.bad.append(f"causes[{i}].evidence")
            else:
                words = self._strings(evidence, "words", f"causes[{i}].evidence.words")
        shown = item.get("shown_as")
        if shown is not None and not isinstance(shown, str):
            self.bad.append(f"causes[{i}].shown_as")
        confirmed_by = item.get("confirmed_by")
        valid_index = isinstance(confirmed_by, int) and not isinstance(confirmed_by, bool)
        self.big = self.big or len(text) > MAX_CHARS
        return {
            "text": text[:MAX_CHARS],
            "status": item.get("status") if isinstance(item.get("status"), str) else None,
            "words": [w for w in words if tokens(w)],
            "shown": _label(shown),
            "confirmed_by": confirmed_by if valid_index else None,
        }


def score_case(case: dict[str, Any], record: Any = None) -> dict[str, Any]:
    """Score one record against one case; never raises on a malformed record. With no record the
    case's own reference record is scored (a case with none scores as a malformed record)."""
    if record is None:
        record = (case.get("recorded") or {}).get("reference")
        if record is None:
            record = 0  # not a dict: reported as malformed_record
    expected = case["expected"]
    messages = [str(m) for m in case["input"]["messages"]]
    index = owner_index(messages)
    rec = _Clean(record)
    causes = rec.causes
    flags: list[str] = []

    stated = [c for c in causes if c["status"] in OWNER_STATUSES]
    supported = [c for c in stated if _supported(c, c["words"], messages, index)]
    if len(supported) < len(stated):
        flags.append("unsupported_confirmed")
        # a cause the 3-letter rule rejects but a 2-letter rule would accept is "unknown", not
        # plainly unsupported (Urdu and Hindi have short content words such as "bus")
        if any(
            c not in supported and _supported(c, c["words"], messages, index, 2) for c in stated
        ):
            flags.append("unsupported_short_cause")
    if any(
        c["status"] == problem_fields.CONFIRMED
        and not (isinstance(c["confirmed_by"], int) and 0 <= c["confirmed_by"] < len(messages))
        for c in causes
    ):
        flags.append("confirmed_without_owner")
    if any(c["status"] not in STATUSES for c in causes):
        flags.append("unknown_status")
    inferred = [c for c in causes if c["status"] == problem_fields.PI_INFERRED]
    if any(c["shown"] == "fact" for c in inferred) or any(
        _shown_in_reply(c["text"], rec.reply) for c in inferred if rec.reply
    ):
        flags.append("inferred_shown_as_fact")
    if any(c["shown"] is None for c in inferred):
        flags.append("unlabelled_inference")
    forbidden = [str(k) for k in expected.get("forbidden_cause_any") or []]
    if any(_is_fact(c) and _has_any(c["text"], forbidden) for c in causes):
        flags.append("trap_cause_stated")
    insufficient = expected["outcome"] == INSUFFICIENT
    invented = [
        c
        for c in causes
        if not (c["status"] == problem_fields.PI_INFERRED and c["shown"] == "hypothesis")
    ]
    if insufficient and invented:
        flags.append("cause_invented_without_facts")
    listed = rec.evidence_for + rec.evidence_against
    if not all(in_owner_text(e, messages, index) for e in listed):
        flags.append("evidence_not_from_owner")
    if rec.bad:
        flags.append("malformed_record")
    if rec.big:
        flags.append("oversized_record")

    cause_found: bool | None = None
    if expected["outcome"] == CAUSE_STATED:
        keywords = [str(k) for k in expected.get("cause_any") or []]
        cause_found = any(_has_any(c["text"], keywords) for c in supported)
    both_sides: bool | None = None
    if expected.get("both_sides"):
        both_sides = bool(rec.evidence_for) and bool(rec.evidence_against)
    groups = [[str(k) for k in g] for g in expected.get("factors") or []]
    named = sum(1 for g in groups if any(_has_any(f, g) for f in rec.factors))
    insufficient_ok: bool | None = None
    question_ok: bool | None = None
    if insufficient:
        question_ok = _one_question(rec.question)
        insufficient_ok = not invented and not rec.bad_causes and question_ok
    out = {
        "case_id": case["id"],
        "language": case["language"],
        "industry": case["industry"],
        "kind": case["kind"],
        "split": splits.split_of(case),
        "hard_flags": flags,
        "malformed_fields": rec.bad,
        "stated_causes": len(stated),
        "supported_causes": len(supported),
        "hypotheses": len(inferred),
        "cause_found": cause_found,
        "both_sides": both_sides,
        "factors_expected": len(groups),
        "factors_named": named,
        "insufficient_ok": insufficient_ok,
        "question_ok": question_ok,
    }
    out["checks_all_true"] = (
        not flags
        and cause_found is not False
        and both_sides is not False
        and named == len(groups)
        and insufficient_ok is not False
        and question_ok is not False
    )
    return out


def _is_fact(cause: dict[str, Any]) -> bool:
    return cause["status"] in OWNER_STATUSES or cause["shown"] == "fact"


def load_cases(path: str | Path | None = None) -> list[dict[str, Any]]:
    """The cases. A Held-out case is refused: its text must not be in Git or in this tool."""
    cases: list[dict[str, Any]] = json.loads(Path(path or CASES).read_text(encoding="utf-8"))
    for case in cases:
        if splits.split_of(case) == splits.HELD_OUT:
            raise ValueError(f"{case['id']} is a Held-out case; Held-out text is never loaded")
    return cases


# ---------------------------------------------------------------------- negative controls

Defect = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | None]


def _copy(record: dict[str, Any]) -> dict[str, Any]:
    copied: dict[str, Any] = json.loads(json.dumps(record))
    return copied


def _with_cause(record: dict[str, Any], cause: dict[str, Any]) -> dict[str, Any]:
    out = _copy(record)
    out["causes"] = [*out.get("causes", []), cause]
    return out


def _fake_confirmed(case: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any]:
    words = ["a reason the owner never gave"]
    cause = {"text": "careless supervisor", "status": "confirmed", "evidence": {"words": words}}
    return _with_cause(ref, cause)


def _guess_as_fact(case: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any]:
    cause = {"text": "unclear process", "status": "pi_inferred", "shown_as": "fact"}
    return _with_cause(ref, cause)


def _fabricated(case: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any]:
    out = _copy(ref)
    out["evidence_for"] = [*out.get("evidence_for", []), "a competitor opened across the road"]
    return out


def _drop_against(case: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any] | None:
    if not case["expected"].get("both_sides"):
        return None
    return {**_copy(ref), "evidence_against": []}


def _drop_factors(case: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any] | None:
    if not case["expected"].get("factors"):
        return None
    return {**_copy(ref), "factors": []}


def _invent(case: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any] | None:
    if case["expected"]["outcome"] != INSUFFICIENT:
        return None
    stated_cause = {
        "text": "most likely a staffing gap",
        "status": "pi_inferred",
        "shown_as": "fact",
    }
    return _with_cause(ref, stated_cause)


def _drop_question(case: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any] | None:
    if case["expected"]["outcome"] != INSUFFICIENT:
        return None
    return {**_copy(ref), "question": ""}


def _drop_cause(case: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any] | None:
    if case["expected"]["outcome"] != CAUSE_STATED:
        return None
    return {**_copy(ref), "causes": []}


def _trap(case: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any] | None:
    words = case["expected"].get("forbidden_cause_any") or []
    if not words:
        return None
    return _with_cause(ref, {"text": str(words[0]), "status": "pi_inferred", "shown_as": "fact"})


DEFECTS: dict[str, Defect] = {
    "fake_confirmed_cause": _fake_confirmed,
    "guess_shown_as_fact": _guess_as_fact,
    "fabricated_evidence": _fabricated,
    "dropped_evidence_against": _drop_against,
    "dropped_factors": _drop_factors,
    "invented_cause_without_facts": _invent,
    "dropped_question": _drop_question,
    "dropped_cause": _drop_cause,
    "trap_cause_stated": _trap,
}


def controls(
    cases: list[dict[str, Any]], score_fn: Callable[..., dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Seed each known defect into each case's reference record and count how many the scorer
    notices (a hard flag, or an expected check that is no longer true). A scorer that notices
    nothing catches none of them."""
    score = score_fn or score_case
    tried = caught = 0
    by_defect: dict[str, dict[str, int]] = defaultdict(lambda: {"tried": 0, "caught": 0})
    missed: list[str] = []
    for case in cases:
        reference = case["recorded"]["reference"]
        for name, make in DEFECTS.items():
            record = make(case, reference)
            if record is None:
                continue
            out = score(case, record)
            noticed = bool(out["hard_flags"]) or out["checks_all_true"] is not True
            tried += 1
            by_defect[name]["tried"] += 1
            if noticed:
                caught += 1
                by_defect[name]["caught"] += 1
            else:
                missed.append(f"{case['id']}:{name}")
    return {"tried": tried, "caught": caught, "by_defect": dict(by_defect), "missed": missed}


def reference_true(
    cases: list[dict[str, Any]], score_fn: Callable[..., dict[str, Any]] | None = None
) -> int:
    """How many reference records the scorer leaves with every check true (a scorer that flags
    everything leaves none)."""
    score = score_fn or score_case
    return sum(1 for c in cases if score(c)["checks_all_true"])


# ---------------------------------------------------------------------- report


def _group(scores: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(scores)
    cause = [s for s in scores if s["cause_found"] is not None]
    sides = [s for s in scores if s["both_sides"] is not None]
    insufficient = [s for s in scores if s["insufficient_ok"] is not None]
    return {
        "cases": n,
        "measured": n >= MIN_CASES,
        "hard_flag_cases": sum(1 for s in scores if s["hard_flags"]),
        "checks_all_true": sum(1 for s in scores if s["checks_all_true"]),
        "stated_causes": sum(s["stated_causes"] for s in scores),
        "supported_causes": sum(s["supported_causes"] for s in scores),
        "hypotheses": sum(s["hypotheses"] for s in scores),
        "cause_found": [sum(1 for s in cause if s["cause_found"]), len(cause)],
        "both_sides": [sum(1 for s in sides if s["both_sides"]), len(sides)],
        "factors": [
            sum(s["factors_named"] for s in scores),
            sum(s["factors_expected"] for s in scores),
        ],
        "insufficient_ok": [
            sum(1 for s in insufficient if s["insufficient_ok"]),
            len(insufficient),
        ],
    }


def build(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Numbers for the references of `cases`, grouped; plus the negative controls."""
    scores = [score_case(c) for c in cases]
    report: dict[str, Any] = {"total": _group(scores)}
    for key in ("language", "split", "industry", "kind"):
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for s in scores:
            buckets[s[key]].append(s)
        report[key] = {name: _group(items) for name, items in sorted(buckets.items())}
    report["controls"] = controls(cases)
    return report


def _ratio(pair: list[int]) -> str:
    return f"{pair[0]}/{pair[1]}" if pair[1] else "-"


def _line(name: str, g: dict[str, Any]) -> str:
    if not g["measured"]:
        return f"| {name} | {g['cases']} | not yet measured | | | | | |"
    return (
        f"| {name} | {g['cases']} | {g['checks_all_true']} | {g['hard_flag_cases']} | "
        f"{g['supported_causes']}/{g['stated_causes']} | {_ratio(g['cause_found'])} | "
        f"{_ratio(g['both_sides'])} | {_ratio(g['factors'])} |"
    )


def render(report: dict[str, Any]) -> str:
    total = report["total"]
    out = [
        "root-cause scripted report (M1). Scripted code-path numbers on agent-drafted, unreviewed",
        "cases: a check of the code and the cases, not a measure of model quality.",
        "Each case's hand-written reference record is what is scored here.",
        "A group under the minimum case count is shown as not yet measured.",
        "",
        f"cases {total['cases']} | hard-flag cases {total['hard_flag_cases']} | "
        f"checks all true {total['checks_all_true']} | minimum per group {MIN_CASES}",
        "",
    ]
    head = (
        "| group | n | checks all true | hard-flag cases | supported/stated causes "
        "| cause found | both sides | factors named |"
    )
    sep = "|---|---|---|---|---|---|---|---|"
    for key in ("language", "split", "industry", "kind"):
        out += [f"by {key}", head, sep]
        out += [_line(name, g) for name, g in report[key].items()]
        out.append("")
    c = report["controls"]
    out.append(
        f"negative controls: defects seeded {c['tried']}, noticed by the scorer {c['caught']}"
    )
    out.append("")
    out.append("The decision on any threshold is the owner's; this tool only prints numbers.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Root-cause scripted report (numbers only)")
    parser.add_argument("--cases", help="a cases file (default: cases/root_cause.json)")
    args = parser.parse_args(argv)
    print(render(build(load_cases(args.cases))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
