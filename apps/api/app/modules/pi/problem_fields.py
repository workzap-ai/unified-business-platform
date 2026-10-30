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
word, and EVERY word must occur in what the owner wrote (the message text and the stored words).
A cause with no such proof is `pi_inferred`, pi's own guess. `confirmed` is reached only through
`confirm_cause` from `owner_said`: an inferred cause is never treated as a confirmed fact, and a
later guess never lowers or replaces what the owner said.

Every text is redacted (card, ID, account, phone, e-mail) and a third party's name is taken out
where the words around it give it away (best effort, see `third_party`), then cut to size.
"""

import logging
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
CAUSE_STATUSES = (PI_INFERRED, OWNER_SAID, CONFIRMED)
# Statuses that mean the owner said it (or agreed to it): the only causes a reader may state.
OWNER_STATUSES = (OWNER_SAID, CONFIRMED)


def clean(text: Any, cap: int) -> tuple[str, bool]:
    """One text as it may be kept, and whether the redactor changed anything. Redact first, then
    cut, so a number cut in half is never left behind."""
    raw = " ".join(str(text or "").split())
    if not raw:
        return "", False
    redacted = safety.redact_pii(raw).text
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
        k: v for k, v in (old or {}).items() if k in (*SCALAR_KEYS, "cannot_change")
    }
    touched = False
    for key, text in (("budget", budget), ("staff", staff), ("deadline", deadline)):
        entry = _entry(text, msg, changed)
        if entry and not _same(entry["text"], str((new.get(key) or {}).get("text", ""))):
            new[key] = entry
            touched = True
    kept: list[dict[str, str]] = [dict(e) for e in new.get("cannot_change") or [] if e.get("text")]
    for ref in remove or []:
        ref = ref.strip()
        if ref.startswith("#") and ref[1:].isdigit():
            index = int(ref[1:]) - 1
            if 0 <= index < len(kept):
                del kept[index]
                touched = True
            continue
        text, was = clean(ref, TEXT_CAP)
        changed.append(was)
        left = [e for e in kept if not _same(e["text"], text)]
        if text and len(left) != len(kept):
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
    return (new if touched else None), any(changed)


def merge_tried(
    old: list[dict[str, Any]] | None, said: list[dict[str, Any]], msg: str | None
) -> tuple[list[dict[str, str]] | None, bool]:
    """What the owner already tried and how it went. The same attempt again updates its outcome."""
    changed: list[bool] = []
    kept: list[dict[str, str]] = [
        {k: str(v) for k, v in e.items() if k in ("what", "outcome", "msg")}
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
            same["outcome"] = outcome
            touched = True
    return (_keep_newest(kept, "tried") if touched else None), any(changed)


def _squash(text: Any) -> str:
    return " ".join(str(text or "").casefold().split())


def said_by_owner(words: list[str], corpus: str) -> bool:
    """True only when there is at least one evidence word and EVERY one occurs in what the owner
    wrote (case-insensitive substring of `corpus`). A word the owner never wrote is fabricated."""
    heard = _squash(corpus)
    used = [_squash(w) for w in words if _squash(w)]
    return bool(used) and all(w in heard for w in used)


def merge_cause(
    old: dict[str, Any] | None,
    text: str,
    owner_said: bool,
    words: list[str],
    msg: str | None,
    corpus: str = "",
) -> tuple[dict[str, Any] | None, bool]:
    """The cause with what the note says. `owner_said` needs the owner's own words as evidence:
    every evidence word must occur in `corpus` (the owner's message and stored words), otherwise
    the cause is pi's guess and a word the owner never wrote is not stored. A guess never replaces
    or lowers a cause the owner said; a different cause the owner says replaces it and starts
    again at `owner_said`."""
    value, changed = clean(text, CAUSE_CAP)
    if not value:
        return None, False
    heard = _squash(corpus)
    candidates = [w for w in words[:EVIDENCE_WORDS] if _squash(w)]
    proven = said_by_owner(candidates, corpus)
    evidence_words: list[str] = []
    for word in candidates:
        if _squash(word) not in heard:
            continue  # not in what the owner wrote: never stored as evidence
        cleaned, was = clean(word, EVIDENCE_WORD_CAP)
        changed = changed or was
        if cleaned:
            evidence_words.append(cleaned)
    status = OWNER_SAID if owner_said and proven and evidence_words else PI_INFERRED
    previous = old or {}
    prior_status = previous.get("status")
    prior_text = str(previous.get("text") or "")
    if status == PI_INFERRED and prior_status in OWNER_STATUSES:
        return None, changed  # a guess does not touch what the owner said
    if previous and _same(prior_text, value):
        if prior_status == CONFIRMED or status == prior_status:
            return None, changed  # the same cause again: nothing to change
    msgs = [msg] if msg else []
    if previous and _same(prior_text, value):
        msgs = [*previous.get("evidence", {}).get("msgs", []), *msgs]
        evidence_words = [*previous.get("evidence", {}).get("words", []), *evidence_words]
    evidence: dict[str, list[str]] = {
        "msgs": list(dict.fromkeys(msgs))[-EVIDENCE_WORDS:],
        "words": list(dict.fromkeys(evidence_words))[:EVIDENCE_WORDS],
    }
    return {"text": value, "status": status, "evidence": evidence}, changed


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
