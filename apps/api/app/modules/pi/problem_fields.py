"""B2a: the per-problem requirement fields (constraints, tried, cause, expected outcome).

Pure functions, no database. `problems.ProblemBook` calls them when a note carries these fields;
a note that carries none leaves the stored value alone, and a row written before migration 0053
reads as empty (NULL means "not said").

Shapes (docs/pi-saas/pi-p1-schema-review.md section 2.1; sizes are proposals, not measured):
  constraints  {"budget": {"text", "msg"}, "staff": {...}, "deadline": {...},
                "cannot_change": [{"text", "msg"}]}      4 keys, text 160, at most 5 cannot_change
  tried        [{"what", "outcome", "msg"}]              at most 5, 160 + 160
  cause        {"text", "status", "evidence": {"msgs", "words"}}   text 300, 3 words of 120
  expected_outcome  text, 300

A list past its cap keeps the newest entries and logs how many were dropped.

A cause has a status. `owner_said` needs the owner's own words as evidence: at least one evidence
word of 3+ characters, and EVERY word must occur, as whole words, in the owner's own message
(`owner_text`, nothing else: model-written user_words prove nothing; with no owner_text a cause
can only be `pi_inferred`).
A cause with no such proof is `pi_inferred`, pi's own guess. `confirmed` is reached only through
`confirm_cause` from `owner_said`: an inferred cause is never treated as a confirmed fact, and a
later guess never lowers or replaces what the owner said.

Every text is redacted (card, ID, account, phone, e-mail) and a third party's name is taken out
where the words around it give it away (best effort, see `third_party`), then cut to size.
"""

import logging
import re
from typing import Any

from app.modules.pi import safety, third_party

logger = logging.getLogger(__name__)

TEXT_CAP = 160
CAUSE_CAP = 300
OUTCOME_CAP = 300
LIST_CAP = 5
EVIDENCE_WORDS = 3
EVIDENCE_WORD_CAP = 120
SCALAR_KEYS = ("budget", "staff", "deadline")

PI_INFERRED = "pi_inferred"
OWNER_SAID = "owner_said"
CONFIRMED = "confirmed"
WITHDRAWN = "withdrawn"  # the owner took their cause back: no reader may state it
CAUSE_STATUSES = (PI_INFERRED, OWNER_SAID, CONFIRMED, WITHDRAWN)
# Statuses that mean the owner said it (or agreed to it): the only causes a reader may state.
OWNER_STATUSES = (OWNER_SAID, CONFIRMED)


# A phone number is never kept in a stored requirement, even the owner's own (the safety redactor
# lets "call me on ..." through, and misses the grouped Pakistani forms): 0300-1234567,
# 0300 123 4567, (0300) 1234567, +92 300 1234567, 0092-300-1234567, 042-35761234.
_LOCAL_PHONE = re.compile(
    r"(?<![\w+-])(?:(?:\+|00)?92[\s.-]*\(?3\d{2}\)?|\(?03\d{2}\)?)[\s.-]*\d{3}[\s.-]*\d{4}(?!\d)"
    r"|(?<![\w+-])0[1-9]\d?[\s.-]\d{7,8}(?!\d)"
)
PHONE_REMOVED = "[contact detail removed]"


def _redact_phones(text: str) -> str:
    return _LOCAL_PHONE.sub(PHONE_REMOVED, safety.PHONE.sub(PHONE_REMOVED, text))


def clean(text: Any, cap: int) -> tuple[str, bool]:
    """One text as it may be kept, and whether the redactor changed anything. Redact first, then
    cut, so a number cut in half is never left behind."""
    raw = " ".join(str(text or "").split())
    if not raw:
        return "", False
    redacted = _redact_phones(safety.redact_pii(raw).text)
    protected = " ".join(third_party.protect(redacted).split())
    return protected[:cap].strip(), protected != raw


def _entry(text: Any, msg: str | None, changed: list[bool]) -> dict[str, str] | None:
    value, was = clean(text, TEXT_CAP)
    changed.append(was)
    if not value:
        return None
    return {"text": value, "msg": msg} if msg else {"text": value}


def _same(a: str, b: str) -> bool:
    return a.casefold() == b.casefold()


def _keep_newest(items: list[Any], what: str) -> list[Any]:
    """At most LIST_CAP entries: the newest are kept, and the dropped count is logged."""
    if len(items) > LIST_CAP:
        dropped = len(items) - LIST_CAP
        logger.warning("pi_problem_field_over_cap", extra={"field": what, "dropped": dropped})
        return items[-LIST_CAP:]
    return items


def merge_constraints(
    old: dict[str, Any] | None,
    budget: str,
    staff: str,
    deadline: str,
    cannot_change: list[str],
    msg: str | None,
    remove: list[str] | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    """The stored constraints with what the note says. A said value replaces the older one of its
    key (the old value is kept by the revision diff), but the same text again changes nothing.
    cannot_change entries are added, never repeated; `remove` takes out an entry the owner
    corrected, by its text or by its 1-based position ("#2"). Past LIST_CAP the newest are kept.
    Returns (new value, or None when nothing changed; whether the redactor changed a text)."""
    changed: list[bool] = []
    new: dict[str, Any] = {
        k: v for k, v in (old or {}).items() if k in (*SCALAR_KEYS, "cannot_change", "history")
    }
    history: list[dict[str, Any]] = list(new.get("history") or [])
    touched = False
    for key, text in (("budget", budget), ("staff", staff), ("deadline", deadline)):
        entry = _entry(text, msg, changed)
        if entry and not _same(entry["text"], str((new.get(key) or {}).get("text", ""))):
            if (new.get(key) or {}).get("text"):  # a corrected value: the old one stays (G)
                history.append({"key": key, **(new[key]), "replaced_msg": msg or ""})
            new[key] = entry
            touched = True
    kept: list[dict[str, str]] = [dict(e) for e in new.get("cannot_change") or [] if e.get("text")]
    for ref in remove or []:
        ref = ref.strip()
        if ref.startswith("#") and ref[1:].isdigit():
            index = int(ref[1:]) - 1
            if 0 <= index < len(kept):
                history.append({"key": "cannot_change", **kept[index], "replaced_msg": msg or ""})
                del kept[index]
                touched = True
            continue
        text, was = clean(ref, TEXT_CAP)
        changed.append(was)
        left = [e for e in kept if not _same(e["text"], text)]
        if text and len(left) != len(kept):
            history += [
                {"key": "cannot_change", **e, "replaced_msg": msg or ""}
                for e in kept
                if _same(e["text"], text)
            ]
            kept = left
            touched = True
    for text in cannot_change:
        entry = _entry(text, msg, changed)
        if entry and not any(_same(entry["text"], e["text"]) for e in kept):
            kept.append(entry)
            touched = True
    kept = _keep_newest(kept, "cannot_change")
    if kept:
        new["cannot_change"] = kept
    else:
        new.pop("cannot_change", None)
    if history:
        new["history"] = history[-LIST_CAP * 2 :]
    return (new if touched else None), any(changed)


def merge_tried(
    old: list[dict[str, Any]] | None, said: list[dict[str, Any]], msg: str | None
) -> tuple[list[dict[str, Any]] | None, bool]:
    """What the owner already tried and how it went. The same attempt again updates its outcome."""
    changed: list[bool] = []
    kept: list[dict[str, Any]] = [
        {
            **{k: str(v) for k, v in e.items() if k in ("what", "outcome", "msg")},
            **({"history": e["history"]} if e.get("history") else {}),
        }
        for e in old or []
        if e.get("what")
    ]
    touched = False
    for item in said:
        what, w1 = clean(item.get("what"), TEXT_CAP)
        outcome, w2 = clean(item.get("outcome"), TEXT_CAP)
        changed += [w1, w2]
        if not what:
            continue
        entry = {"what": what, "outcome": outcome}
        if msg:
            entry["msg"] = msg
        same = next((e for e in kept if _same(e["what"], what)), None)
        if same is None:
            kept.append(entry)
            touched = True
        elif outcome and same.get("outcome") != outcome:
            if same.get("outcome"):  # the older outcome stays on this attempt's own record (G)
                same["history"] = [
                    *same.get("history", []),
                    {"outcome": same["outcome"], "msg": same.get("msg", "")},
                ][-LIST_CAP:]
            same["outcome"] = outcome
            touched = True
    return (_keep_newest(kept, "tried") if touched else None), any(changed)


MIN_WORD = 3  # an evidence word shorter than this proves nothing ("a", "no")


def _squash(text: Any) -> str:
    return " ".join(str(text or "").casefold().split())


ARABIC_LETTER = re.compile(r"[؀-ۿ]")
# attached to an Arabic word: and (waw, fa), with / to / like (ba, lam, kaf), the (alif-lam), and
# lam + the written "lam-lam" (for the ...)
_ARABIC_PREFIXES = ("لل", "ال", "و", "ف", "ب", "ل", "ك")


def _arabic_variants(word: str) -> set[str]:
    """The word and every form it has with attached prefixes taken off (three deep, three letters
    kept at least). Two words are the same word when their forms meet: the bare word and the
    same word with a glued conjunction, preposition or article, either way round."""
    forms = {word}
    frontier = [word]
    for _ in range(3):
        step: list[str] = []
        for form in frontier:
            for prefix in _ARABIC_PREFIXES:
                rest = form[len(prefix) :]
                if form.startswith(prefix) and len(rest) >= 3 and rest not in forms:
                    forms.add(rest)
                    step.append(rest)
        frontier = step
    return forms


def _heard(word: str, heard: str) -> bool:
    """`word` occurs in `heard` as whole words, not inside a longer word. An Arabic word also
    matches the same word with a clitic attached or removed."""
    if not word:
        return False
    if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", heard) is not None:
        return True
    if not ARABIC_LETTER.search(word):
        return False
    mine = _arabic_variants(word)
    return any(mine & _arabic_variants(t) for t in re.findall(r"\w+", heard))


# Words that prove nothing as evidence of a cause: function words in the five languages.
STOPWORDS = frozenset(
    """the and for are was were with that this its our has have had not but you your they them from
    because due been being very just also than then into about when what which there their here who
    how why all can will would could should may might hai hain thi tha aur ya ka ki ke ko se ne mein
    main par pe bhi yeh woh hum mera meri mere apna kar karna kiya hota hoti hote liye isliye kyun
    kyunke jab jo to لل
    کا کی کے کو سے نے میں پر ہے ہیں تھا تھی اور یہ وہ بھی
    على الى هذا هذه ذلك التي الذي عند كان
    है हैं का की के को से में पर और यह वह भी था थी""".split()
)

# --- the owner's own endorsement: who said it, whether it is negated, hypothetical or a question
_TOKEN = re.compile(r"[\wऀ-ॿً-ٰٟ']+")
_NEGATION = frozenset(
    """not never no isn't wasn't aren't weren't doesn't don't didn't nahi nahin nhi na
    نہیں نھیں نہ ليس ليست لا لم ما لن
    नहीं न""".split()
)
_FILLER = frozenset(
    """the a an of to due because from is are was it this that its our my cause reason wajah sabab
    ye yeh wo woh ka ki ke hai hain thi tha ho
    وجہ سبب ہے ہیں تھی تھا هو هي هذا السبب
    वजह कारण है थी था की का""".split()
)
_QUESTION_START = re.compile(
    r"^\s*(?:are|is|do|does|did|can|could|will|would|why|kya|کیا|هل|क्या)\b"
    r"|^\s*(?:کیا|هل|क्या)\s"
)
# pi's question said back, not the owner's claim
_ECHO = re.compile(
    r"\byou(?:'re| are)? (?:saying|asking|suggesting|claiming|telling)\b|\baap keh rahe\b"
    r"|آپ کہہ رہے|هل تقصد|आप कह रहे"
)
# someone else's opinion ("my partner thinks it is the rent")
_OPINION = re.compile(
    r"\b(?:partner|wife|husband|brother|sister|friend|manager|accountant|uncle|aunt|father|"
    r"mother|cousin|neighbou?r)\b"
    r"[^.?!]{0,30}\b(?:thinks?|says?|said|believes?|feels?|claims?|told|tells)\b"
    r"|\b(?:kehta|kehte|kehti|manta|mante|samajhta|samajhte|samajhti|sochta|sochte|sochti)\b"
    r"|\bne kaha\b|کہتے ہیں|کہتا|کہتی|بھائی کا خیال"
    r"|يقول|تقول|يعتقد|يرى|कहता|कहते|कहती|मानता|मानते|सोचता"
)


def _endorsing_clauses(corpus: str | None) -> list[str]:
    """The squashed clauses of the owner's text that can be their own claim about a cause: not a
    question (or pi's question said back), not a hypothetical, not someone else's opinion."""
    from app.modules.pi import tried_outcome as clauses

    out: list[str] = []
    for clause, is_question in clauses.split_clauses(corpus):
        said = _squash(clause)
        if is_question or _QUESTION_START.search(said) or _ECHO.search(said):
            continue
        if clauses._HYPOTHETICAL.search(said):
            continue
        if _OPINION.search(said) and not clauses._FIRST_PERSON.search(said):
            continue
        out.append(said)
    return out


def _negated(clause: str, word: str) -> bool:
    """A negation right before or after `word` ("it is NOT the rent", "rent wajah nahi hai"),
    skipping little words between them."""
    tokens = _TOKEN.findall(clause)
    for at, token in enumerate(tokens):
        if token != word and not (ARABIC_LETTER.search(word) and word in token):
            continue
        for step in (-1, 1):
            i = at + step
            for _ in range(3):
                if not 0 <= i < len(tokens):
                    break
                if tokens[i] in _NEGATION:
                    return True
                if tokens[i] not in _FILLER:
                    break
                i += step
    return False


def _endorsed(word: str, clauses: list[str]) -> bool:
    return any(_heard(word, c) and not _negated(c, word) for c in clauses)


def usable_words(words: list[str]) -> list[str]:
    """The evidence words that can count: at most EVIDENCE_WORDS, at least MIN_WORD characters,
    never a function word ("the", "hai"): those prove nothing."""
    return [w for w in words[:EVIDENCE_WORDS] if _content(w)]


def _content(word: str) -> bool:
    said = _squash(word)
    return len(said) >= MIN_WORD and said not in STOPWORDS


def content_words(text: str, limit: int = 6) -> list[str]:
    """The words of `text` that carry its meaning (function words and short words left out)."""
    return [w for w in _TOKEN.findall(_squash(text)) if _content(w)][:limit]


def support_share(words: list[str], corpus: str | None) -> float:
    """The share (0 to 1) of `words` that the owner's own claims in `corpus` carry."""
    clauses = _endorsing_clauses(corpus)
    if not words or not clauses:
        return 0.0
    return sum(1 for w in words if _endorsed(_squash(w), clauses)) / len(words)


def said_by_owner(words: list[str], corpus: str | None) -> bool:
    """True only when there is at least one usable evidence word and EVERY one occurs, as whole
    words and case-insensitively, in a clause of `corpus`, the owner's own message, that is the
    owner's own claim (not a question, not a hypothetical, not someone else's opinion) and does not
    negate the word. Nothing else is evidence: with no corpus the answer is always False (fail
    closed), and model-written words (a note's user_words, stored user_words) are never a corpus."""
    clauses = _endorsing_clauses(corpus)
    used = [_squash(w) for w in usable_words(words)]
    return bool(clauses) and bool(used) and all(_endorsed(w, clauses) for w in used)


def merge_cause(
    old: dict[str, Any] | None,
    text: str,
    owner_said: bool,
    words: list[str],
    msg: str | None,
    corpus: str | None = None,
    when: str = "",
) -> tuple[dict[str, Any] | None, bool]:
    """The cause with what the note says. `owner_said` needs the owner's own words as evidence:
    every evidence word must occur, as whole words, in `corpus` (the owner's own message only),
    otherwise the cause is pi's guess and a word the owner never wrote is not stored. A guess
    never replaces or lowers a cause the owner said; a different cause the owner says replaces it
    and starts again at `owner_said`."""
    value, changed = clean(text, CAUSE_CAP)
    if not value:
        return None, False
    clauses = _endorsing_clauses(corpus)
    candidates = usable_words(words)
    proven = said_by_owner(candidates, corpus)
    evidence_words: list[str] = []
    for word in candidates:
        if not _endorsed(_squash(word), clauses):
            continue  # not the owner's own claim: never stored as evidence
        cleaned, was = clean(word, EVIDENCE_WORD_CAP)
        changed = changed or was
        if cleaned:
            evidence_words.append(cleaned)
    status = OWNER_SAID if owner_said and proven and evidence_words else PI_INFERRED
    previous = old or {}
    prior_status = previous.get("status")
    prior_text = str(previous.get("text") or "")
    if prior_status == WITHDRAWN and any(
        _same(str(h.get("text") or ""), value) for h in previous.get("history") or []
    ):
        return None, changed  # a cause the owner took back is not brought back by a later note
    if status == PI_INFERRED and prior_status in OWNER_STATUSES:
        return None, changed  # a guess does not touch what the owner said
    if previous and _same(prior_text, value):
        if prior_status == CONFIRMED or status == prior_status:
            return None, changed  # the same cause again: nothing to change
    msgs = [msg] if msg else []
    if previous and _same(prior_text, value):
        msgs = [*previous.get("evidence", {}).get("msgs", []), *msgs]
        evidence_words = [*previous.get("evidence", {}).get("words", []), *evidence_words]
    evidence: dict[str, Any] = {
        "msgs": list(dict.fromkeys(msgs))[-EVIDENCE_WORDS:],
        "words": list(dict.fromkeys(evidence_words))[:EVIDENCE_WORDS],
    }
    result: dict[str, Any] = {"text": value, "status": status, "evidence": evidence}
    history = list(previous.get("history") or [])  # a withdrawn cause stays on record
    if prior_text and not _same(prior_text, value) and prior_status != WITHDRAWN:
        history.append(  # a cause that a correction replaces stays on record too (G)
            {
                "text": prior_text,
                "status": prior_status,
                "evidence": previous.get("evidence") or {},
                "replaced_msg": msg or "",
                "replaced_at": when,
            }
        )
    if history:
        result["history"] = history[-LIST_CAP:]
    return result, changed


def confirmed_cause(cause: dict[str, Any] | None) -> dict[str, Any] | None:
    """`cause` with status `confirmed`, only from an `owner_said` cause. An inferred cause, or
    none, cannot be confirmed (returns None)."""
    if not cause or cause.get("status") not in OWNER_STATUSES:
        return None
    if cause.get("status") == CONFIRMED:
        return None  # already confirmed
    return {**cause, "status": CONFIRMED}


def stated_cause(cause: dict[str, Any] | None) -> str:
    """The cause text a reader may present as the owner's: empty for a guess or no cause."""
    if not cause or cause.get("status") not in OWNER_STATUSES:
        return ""
    return str(cause.get("text") or "")


# The owner takes their cause back. Phrases, not a model's say-so: the code reads the owner's own
# latest message. English, Roman Urdu, Urdu, Arabic, Hindi.
WITHDRAWAL = re.compile(
    r"\b(?:i take (?:that|it) back|take that back|i was wrong about (?:the|that) (?:cause|reason)|"
    r"that (?:was not|wasn'?t|is not|isn'?t) (?:the|really the) (?:cause|reason)|"
    r"not the (?:real )?(?:cause|reason) after all|"
    r"maine (?:galat|ghalat) kaha|(?:wo|woh|yeh|ye) wajah nahi (?:thi|hai)|"
    r"(?:wo|woh|yeh|ye) (?:sabab|wajah|reason) (?:sahi )?nahi (?:thi|hai))\b"
    r"|(?:یہ|وہ)\s+وجہ\s+نہیں\s+(?:تھی|ہے)|میں\s+نے\s+غلط\s+کہا"
    r"|ليس\s+هذا\s+(?:هو\s+)?السبب|لم\s+يكن\s+هذا\s+(?:هو\s+)?السبب|قلت\s+(?:ذلك\s+)?(?:خطأ|غلط)"
    r"|(?:यह|ये|वो|वह)\s+वजह\s+नहीं\s+(?:थी|है)|मैंने\s+गलत\s+कहा",
    re.IGNORECASE,
)


_WITHDRAWAL_NEGATED = re.compile(
    r"(?:\b(?:not|never|won't|don't|didn't|can't|cannot|nahi|nahin|nhi|kabhi)\b|\u0646\u06c1\u06cc\u06ba|"
    r"\u0928\u0939\u0940\u0902|"
    r"\u0644\u0646|\u0644\u0627)[\s,]*(?:\S+\s+){0,2}$"
)
_WITHDRAWAL_REPORTED = re.compile(
    r"\b(?:you (?:said|told|mentioned|claimed|wrote)|aap ne kaha|aapne kaha|tum ne kaha|"
    r"tumne kaha)\b"
    r"|\u0622\u067e \u0646\u06d2 \u06a9\u06c1\u0627|\u0642\u0644\u062a \u0644\u064a"
    r"|\u0906\u092a\u0928\u0947 \u0915\u0939\u093e"
)


def withdrawal_said(text: str | None) -> bool:
    """True when the owner's message takes back the cause they gave ("I take that back", "maine
    galat kaha", "wo wajah nahi thi", Urdu, Arabic and Hindi forms). Not a question ("kya wo
    wajah nahi thi?"), not a refusal ("I do not take that back", "won't take that back"), and not
    someone's words said back ("you said that wasn't the cause but it is")."""
    from app.modules.pi import tried_outcome as clauses

    for clause, is_question in clauses.split_clauses(text):
        said = _squash(clause)
        found = WITHDRAWAL.search(said)
        if not found or is_question or _QUESTION_START.search(said):
            continue
        before = said[: found.start()]
        if _WITHDRAWAL_NEGATED.search(before) or _WITHDRAWAL_REPORTED.search(before):
            continue
        return True
    return False


def withdraw_cause(old: dict[str, Any] | None, msg: str | None, when: str) -> dict[str, Any] | None:
    """The cause after the owner took it back, or None when there is no owner cause to take back.
    The text is cleared and the status is `withdrawn`; the earlier cause (text, status, evidence,
    the message that withdrew it, when) goes to `history`. Nothing is deleted."""
    if not old or old.get("status") not in OWNER_STATUSES:
        return None
    entry: dict[str, Any] = {
        "text": old.get("text", ""),
        "status": old.get("status"),
        "evidence": old.get("evidence") or {},
        "withdrawn_msg": msg or "",
        "withdrawn_at": when,
    }
    return {
        "text": "",
        "status": WITHDRAWN,
        "evidence": {"msgs": [], "words": []},
        "history": [*(old.get("history") or []), entry],
    }
