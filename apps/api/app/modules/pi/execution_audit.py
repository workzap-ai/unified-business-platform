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
_HAS_DIGIT = re.compile(r"\d")

# ---- secret screening: used on action parameters (refuse) and on audit details (redact) ----------
# Key names: strict. Normalised (casefold, letters and digits only) then matched against a closed list.
_KEY_EXACT = frozenset("pin otp pwd ssn cvv cvc pincode pinnumber otpcode".split())
_KEY_CONTAINS = (
    "password passwd passcode passphrase apikey accesstoken refreshtoken authtoken bearer authorization secret privatekey "
    "token creditcard cardnumber cardno card cvv cvc routing accountnumber accountno iban cnic nationalid credential expiry swift "
    "پاسورڈ पासवर्ड كلمةالمرور كلمةالسر الرقمالسري رمزالتحقق اوٹیپی ओटीपी"
).split()


def secret_key_name(key: Any) -> bool:
    if not isinstance(key, str):
        return True
    k = "".join(
        ch
        for ch in unicodedata.normalize("NFKC", key).casefold()
        if unicodedata.category(ch)[0] in "LMN"
    )
    return k in _KEY_EXACT or any(w in k for w in _KEY_CONTAINS)


# Values: DISCLOSURE patterns, not bare keywords.
_TRIGGERS = frozenset(
    "password passwd passcode pwd otp cvv cvc pin iban cnic ssn پاسورڈ पासवर्ड ओटीपी पिन सीवीवी پن".split()
)
_TRIGGER_PHRASES = (
    ("پاس", "ورڈ"),
    ("او", "ٹی", "پی"),
    ("اوٹی", "پی"),
    ("one", "time"),
    ("verification", "code"),
    ("security", "code"),
    ("secret", "code"),
    ("card", "number"),
    ("كلمه", "المرور"),
    ("كلمه", "السر"),
    ("الرقم", "السري"),
    ("رمز", "التحقق"),
    ("کارڈ", "نمبر"),
    ("कार्ड", "नंबर"),
    ("पास", "वर्ड"),
    ("credit", "card"),
)
_GLUE = frozenset(
    "is are number no code password hai hy hain ka ki ke ہے ہیں کا کی है हैं का की नंबर هو هي رقم نمبر : =".split()
)
_POSSESSIVE = frozenset("my your mera meri apka apki میرا میری मेरा मेरी".split())
_CONNECTORS = frozenset("is are hai hy hain ہے ہیں है हैं هو هي : =".split())
_STOP_VALUES = frozenset(
    "required not never optional shown sent secret hidden ok okay the a an your my our to on in by for via at valid invalid wrong "
    "correct expired reset changed strong weak safe private confidential mandatory needed ready also and or with from that this it "
    "zaroori nahi nahin mat ضروری نہیں जरूरी नहीं ضروري ليس لا".split()
)

_DIGIT_WORDS = frozenset(
    (
        "zero oh one two three four five six seven eight nine "
        "sifar sifr ek do teen char paanch panch chhe chay saat aath nau "
        "صفر ایک دو تین چار پانچ چھ سات آٹھ نو "
        "शून्य एक दो तीन चार पांच पाँच छह छः सात आठ नौ "
        "واحد اثنان اثنين ثلاثه ثلاث اربعه اربع خمسه خمس سته ست سبعه سبع ثمانيه ثماني تسعه تسع"
    ).split()
)
_TOKEN_PATTERNS = (
    re.compile(r"\bsk[-_](?:live|test)[-_][A-Za-z0-9_-]{4,}", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\b[pr]k_(?:live|test)_[A-Za-z0-9]{4,}", re.IGNORECASE),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{8,}"),
    re.compile(r"\bAKIA[0-9A-Z]{12,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}"),
    re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
    re.compile(
        r"[?&](?:[a-z_]*token|api_?key|password|passwd|secret|auth|key|sig|signature)=[^\s&]{3,}",
        re.IGNORECASE,
    ),
)
_LONG_TOKEN = re.compile(r"[A-Za-z0-9_-]{24,}")


def _norm_word(w: str) -> str:
    w = unicodedata.normalize("NFKC", w).casefold()
    for a in "أإآٱ":
        w = w.replace(a, "ا")
    return w.replace("़", "").replace("ة", "ه")


def _scan(text: str) -> list[tuple[str, str, int]]:
    """(normalised word, original word, start) for words, plus ':' and '=' as tokens."""
    out: list[tuple[str, str, int]] = []
    cur: list[str] = []
    start = 0
    for i, ch in enumerate(text):
        if unicodedata.category(ch)[0] in "LMN":
            if not cur:
                start = i
            cur.append(ch)
            continue
        if cur:
            w = "".join(cur)
            out.append((_norm_word(w), w, start))
            cur = []
        if ch in ":=":
            out.append((ch, ch, i))
    if cur:
        w = "".join(cur)
        out.append((_norm_word(w), w, start))
    return out


def _value_like(norm: str, orig: str) -> bool:
    if any(unicodedata.category(c) == "Nd" for c in norm):
        return True
    if len(orig) >= 4 and orig.isalpha():
        return any(c.isupper() for c in orig[1:]) and any(c.islower() for c in orig)
    return False


def _has_secret_shape(token: str) -> bool:
    digits = sum(1 for c in token if c.isdigit())
    letters = sum(1 for c in token if c.isalpha())
    return digits >= 3 and letters >= 3


def secret_start(text: str, digit_words: bool = True) -> int | None:
    """Earliest character index where a secret is disclosed, or None. Detects: token-looking values
    (API keys, JWTs, bearer headers, URL secret parameters, long mixed base64/hex strings), spelled-out
    card digits (five languages), and disclosure patterns (a secret word followed by 'is/:/=' and a value,
    or adjacent to a digit run or a value-like token). Bare mentions of the words are not disclosures."""
    if not isinstance(text, str):
        return 0
    found: list[int] = []
    for pat in _TOKEN_PATTERNS:
        m = pat.search(text)
        if m:
            found.append(m.start())
    for m in _LONG_TOKEN.finditer(text):
        if _has_secret_shape(m.group()):
            found.append(m.start())
            break
    toks = _scan(text)
    n = len(toks)
    # spelled-out or mixed digit runs of 13 or more
    run = 0
    run_start = 0
    for norm, _o, st in toks:
        k = (
            1
            if norm in _DIGIT_WORDS and not norm.isdigit()
            else (len(norm) if norm.isdigit() else 0)
        )
        if k:
            if run == 0:
                run_start = st
            run += k
            if digit_words and run >= 13:
                found.append(run_start)
                break
        else:
            run = 0
    # disclosure patterns
    for i in range(n):
        end = None
        if toks[i][0] in _TRIGGERS:
            end = i
        else:
            for ph in _TRIGGER_PHRASES:
                size = len(ph)
                if i + size <= n and all(toks[i + j][0] == ph[j] for j in range(size)):
                    end = i + size - 1
                    break
        if end is None:
            continue
        trig_start = toks[i][2]
        j = end + 1
        conn = False
        skipped = 0
        while j < n and toks[j][0] in _GLUE and skipped < 4:
            conn = conn or toks[j][0] in _CONNECTORS
            j += 1
            skipped += 1
        if j < n:
            norm, orig, _st = toks[j]
            if (conn and norm not in _STOP_VALUES and norm not in _TRIGGERS) or _value_like(
                norm, orig
            ):
                found.append(trig_start)
                continue
        k = i - 1
        while k >= 0 and k > i - 4 and (toks[k][0] in _GLUE or toks[k][0] in _POSSESSIVE):
            k -= 1
        if k >= 0 and sum(1 for c in toks[k][0] if c.isdigit()) >= 3:
            found.append(toks[k][2])
    return min(found) if found else None


def looks_secret(text: str) -> bool:
    return secret_start(text) is not None


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
    secret statements (passwords, OTPs, CVVs, API keys, tokens ...) never enter the trail."""
    text = value if isinstance(value, str) else str(value)
    text = text[: limit * 4]
    cut = secret_start(
        text, digit_words=False
    )  # tokens and disclosures first, while they are still intact
    if cut is not None:
        text = text[:cut] + "[secret]"
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
    cut = secret_start(text)  # spelled-out digits
    if cut is not None:
        text = text[:cut] + "[secret]"
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
