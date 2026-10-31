# ruff: noqa: E501
"""Controlled execution (Q-8): append-only, hash-chained audit trail. Pure and dry-run: no database,
no I/O, no clock reads (the caller passes `at`). Design: docs/pi-saas/pi-controlled-execution-design.md.

Every decision, action, refusal, verification and rollback is one entry. Each entry's hash covers its
own fields and the previous entry's hash, so editing, removing from the middle, reordering or inserting
an entry is detected by `verify_chain`. Dropping entries from the END is only detectable when the caller
kept the head hash (`expected_head`); that is a stated limit of any chain without an external anchor.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any

GENESIS = "0" * 64
MAX_DETAIL = 500
MAX_FIELD = 120
MAX_ENTRIES = 100_000

KINDS = frozenset(
    {
        "decision",
        "approval",
        "action",
        "refusal",
        "verification",
        "rollback",
        "transition",
        "scope",
    }
)

_EMAIL = re.compile(
    r"[\w.+-]{1,64}\s{0,3}(?:@|\(at\)|\[at\])\s{0,3}[\w-]{1,63}(?:\s{0,3}(?:\.|\(dot\)|\[dot\])\s{0,3}[\w-]{1,63})+",
    re.IGNORECASE,
)
MAX_GAP = 3  # separators tolerated between digits of one number: ". ", " - ", zero-width, nbsp ...

# Words that announce a secret. Any value containing one is treated as secret-bearing (fail closed).
SECRET_WORDS = frozenset(
    "password passwd passcode pwd otp cvv cvc pin iban cnic ssn "
    "پاسورڈ پاس ورڈ اوٹی پی پن "
    "पासवर्ड ओटीपी पिन सीवीवी "
    "كلمه المرور السر الرقم السري رمز".split()
)
SECRET_PHRASES = (
    "one time",
    "verification code",
    "security code",
    "card number",
    "secret code",
    "كلمة المرور",
    "كلمة السر",
    "الرقم السري",
    "رمز التحقق",
    "او ٹی پی",
    "کارڈ نمبر",
    "कार्ड नंबर",
)


_ASCII_WORD = re.compile(r"[a-z0-9]+")
_HAS_DIGIT = re.compile(r"\d")


def _words(text: str) -> list[str]:
    if text.isascii():
        return _ASCII_WORD.findall(text.casefold())
    out: list[str] = []
    cur: list[str] = []
    for ch in unicodedata.normalize("NFKC", text).casefold():
        if unicodedata.category(ch)[0] in "LMN":
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def looks_secret(text: str) -> bool:
    """A secret keyword in any of the five languages (password, OTP, CVV, PIN, card number ...)."""
    words = _words(text)
    if any(w in SECRET_WORDS for w in words):
        return True
    joined = " " + " ".join(words) + " "
    return any(f" {' '.join(_words(p))} " in joined for p in SECRET_PHRASES)


def digit_spans(text: str, min_digits: int) -> list[tuple[int, int]]:
    """Spans holding at least `min_digits` digits where separators between digits are at most MAX_GAP
    characters of any kind. Any Unicode decimal digit counts. Linear time."""
    if not _HAS_DIGIT.search(text):
        return []
    spans: list[tuple[int, int]] = []
    start = last = -1
    count = gap = 0
    for i, ch in enumerate(text):
        if unicodedata.category(ch) == "Nd":
            if count == 0:
                start = i
            count += 1
            last = i
            gap = 0
        elif count:
            gap += 1
            if gap > MAX_GAP:
                if count >= min_digits:
                    spans.append((start, last + 1))
                count = gap = 0
    if count >= min_digits:
        spans.append((start, last + 1))
    return spans


def has_card_like(text: str, min_digits: int = 13) -> bool:
    return bool(digit_spans(text, min_digits))


def _clean(value: Any, limit: int) -> str:
    """Bounded, redacted text: numbers (7+ digits in any separator style), emails (also 'a @ b . com') and
    secret statements (password, OTP, CVV, PIN ...) never enter the trail."""
    text = value if isinstance(value, str) else str(value)
    text = text[: limit * 4]
    spans = digit_spans(text, 7)
    if spans:
        out: list[str] = []
        pos = 0
        for a, b in spans:
            out.append(text[pos:a])
            out.append("[number]")
            pos = b
        out.append(text[pos:])
        text = "".join(out)
    text = _EMAIL.sub("[email]", text)
    if looks_secret(text):
        for m in re.finditer(r"\S+", text):
            if looks_secret(m.group()):
                text = text[: m.start()] + "[secret]"  # the secret word and all that follows it
                break
        else:
            text = "[secret]"
    return text[:limit]


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    at: str
    kind: str
    actor: str
    task_id: str
    detail: str
    prev_hash: str
    hash: str


def _digest(seq: int, at: str, kind: str, actor: str, task_id: str, detail: str, prev: str) -> str:
    body = json.dumps(
        [seq, at, kind, actor, task_id, detail, prev], ensure_ascii=True, separators=(",", ":")
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChainVerdict:
    ok: bool
    bad_index: int | None = None
    reason: str = ""


class AuditLog:
    """Append-only. There is no update or delete method; `entries` is an immutable tuple."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    @property
    def entries(self) -> tuple[AuditEntry, ...]:
        return tuple(self._entries)

    @property
    def head(self) -> str:
        return self._entries[-1].hash if self._entries else GENESIS

    def append(
        self, *, at: datetime, kind: str, actor: str, task_id: str, detail: str = ""
    ) -> AuditEntry | None:
        """Returns the entry, or None when the input is malformed or the log is full (fail closed)."""
        if (
            not isinstance(kind, str)
            or kind not in KINDS
            or not isinstance(at, datetime)
            or at.tzinfo is None
        ):
            return None
        if len(self._entries) >= MAX_ENTRIES:
            return None
        seq = len(self._entries)
        at_s = at.isoformat()
        actor_s = _clean(actor, MAX_FIELD)
        task_s = _clean(task_id, MAX_FIELD)
        detail_s = _clean(detail, MAX_DETAIL)
        prev = self.head
        entry = AuditEntry(
            seq,
            at_s,
            kind,
            actor_s,
            task_s,
            detail_s,
            prev,
            _digest(seq, at_s, kind, actor_s, task_s, detail_s, prev),
        )
        self._entries.append(entry)
        return entry


def verify_chain(entries: Any, expected_head: str | None = None) -> ChainVerdict:
    """Linear time. Never raises; anything malformed is a failed verdict."""
    try:
        items = list(entries)
        prev = GENESIS
        for i, e in enumerate(items):
            if not isinstance(e, AuditEntry):
                return ChainVerdict(False, i, "not an audit entry")
            if e.seq != i:
                return ChainVerdict(
                    False, i, "sequence broken (entry removed, inserted or reordered)"
                )
            if e.kind not in KINDS:
                return ChainVerdict(False, i, "unknown kind")
            if e.prev_hash != prev:
                return ChainVerdict(False, i, "previous hash does not match")
            if e.hash != _digest(e.seq, e.at, e.kind, e.actor, e.task_id, e.detail, e.prev_hash):
                return ChainVerdict(False, i, "entry content does not match its hash")
            prev = e.hash
        if expected_head is not None and expected_head != prev:
            return ChainVerdict(
                False,
                len(items),
                "head differs from the anchor (entries dropped or added at the end)",
            )
        return ChainVerdict(True)
    except Exception:  # noqa: BLE001 - fail closed
        return ChainVerdict(False, None, "unreadable chain")
