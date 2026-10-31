# ruff: noqa: E501  (phrase banks read better one alternative per line)
"""Controlled execution (Q-8): the exact owner-approved scope. Pure and dry-run: nothing here calls
anything outside the process. Design: docs/pi-saas/pi-controlled-execution-design.md (section 5: approval
is for an exact scope; a changed scope is a new approval).

Rules held here:
- A scope exists only from an explicit approval cue. 'ok', 'hmm', 'maybe', 'sure', 'theek hai', a bare
  'yes', anything conditional, negated, a question, quoted or forwarded is NOT approval. Ambiguous means no.
- The approval names the hash of the exact scope it was shown; any change to the scope text, tools or
  limits changes the hash and the approval no longer applies.
- Payment and credential tools can never be in a scope. Irreversible, destructive and outbound-message
  tools may be listed but every single action still needs its own explicit approval (see execution_task).
Linear time; every input is length-bounded.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

MAX_CUE_CHARS = 1000
MAX_SCOPE_CHARS = 20_000
MAX_TOOLS = 50
MAX_LIMITS = 20
MAX_LIMIT_VALUE = 1_000_000
MAX_VALIDITY = timedelta(days=30)
MAX_ID = 120

# Tool classes. 'payment' and 'credential' can never be scoped. The last three need a separate approval per action.
TOOL_CLASSES: dict[str, str] = {
    "read_record": "read",
    "read_document": "read",
    "draft_text": "read",
    "write_note": "write_reversible",
    "update_task_status": "write_reversible",
    "create_draft_document": "write_reversible",
    "send_message": "outbound_message",
    "send_email": "outbound_message",
    "delete_record": "destructive",
    "overwrite_file": "destructive",
    "publish_live": "irreversible",
    "change_production_config": "irreversible",
    "take_payment": "payment",
    "refund": "payment",
    "store_card": "payment",
    "request_password": "credential",
    "request_otp": "credential",
}
NEVER_SCOPED = frozenset({"payment", "credential"})
NEEDS_OWN_APPROVAL = frozenset({"irreversible", "destructive", "outbound_message"})
APPROVAL_SOURCES = frozenset({"owner_chat", "staff_console", "signed_form"})
FORBIDDEN_APPROVERS = frozenset({"pi", "model", "assistant", "system", "ai", "bot", "llm", "agent"})


class ApprovalCue(StrEnum):
    EXPLICIT_YES = "explicit_yes"
    VAGUE = "vague"
    NEGATIVE = "negative"
    CONDITIONAL = "conditional"
    QUOTED = "quoted"
    UNKNOWN = "unknown"


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).casefold()
    t = t.replace("’", "'").replace("‘", "'").replace("'", "")
    out = []
    for ch in t:
        o = ord(ch)
        if 0x064B <= o <= 0x065F or o in (0x0670, 0x0640, 0x200C, 0x200D, 0x200E, 0x200F):
            continue  # Arabic marks, tatweel, joiners
        out.append(ch)
    t = "".join(out)
    for a in "أإآٱ":
        t = t.replace(a, "ا")
    return t.replace("ى", "ي").replace("ك", "ک").replace("ھ", "ہ")


def _tokens(text: str) -> list[str]:
    """Words = runs of letters, digits and combining marks (the regex word class drops Devanagari and Arabic marks)."""
    out: list[str] = []
    cur: list[str] = []
    for ch in _norm(text):
        if unicodedata.category(ch)[0] in "LMN":
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def _phrase_set(phrases: list[str]) -> frozenset[str]:
    return frozenset(" ".join(_tokens(p)) for p in phrases)


def _has_phrase(padded: str, phrases: frozenset[str]) -> bool:
    return any(f" {p} " in padded for p in phrases)


_NEGATIVE = frozenset(
    _tokens(
        "no not never dont doesnt cant wont wouldnt shouldnt isnt arent hold wait stop cancel pause stopped declined reject rejected refuse "
        "nahi nahin nhi nai nai mat na ruk ruko rukein ruka band "
        "نہیں نہی نھیں مت نہ رکو رکیں روکو روک "
        "नहीं नही मत ना रुको रुकिए रोको "
        "لا ليس لن توقف قف الغ"
    )
)
_CONDITIONAL = frozenset(
    _tokens(
        "if unless but once until after when provided maybe perhaps probably later tomorrow depends "
        "agar lekin magar par jab baad shayad shart "
        "اگر لیکن مگر جب بعد شاید شرط "
        "अगर लेकिन मगर जब बाद शायद शर्त "
        "اذا لكن ربما بعد عندما بشرط"
    )
)
_QUOTE_CHARS = frozenset('"“”„‟«»‹›「」')
_FORWARD_TOKENS = frozenset(
    _tokens("fwd forwarded wrote said says told kaha bola likha کہا بولا लिखा कहा बोला قال كتب")
)
_QUESTION = ("?", "؟", "？")

_EXPLICIT = _phrase_set(
    [
        # English
        "i approve",
        "we approve",
        "approved",
        "i approve this",
        "go ahead",
        "please proceed",
        "yes proceed",
        "yes go ahead",
        "proceed",
        "i confirm",
        "confirmed",
        "i authorise",
        "i authorize",
        "authorised",
        "authorized",
        # Roman Urdu
        "haan kar do",
        "han kar do",
        "ji haan kar do",
        "ji kar do",
        "kar do",
        "manzoor hai",
        "mangoor hai",
        "approve hai",
        "main approve karta hoon",
        "main approve karti hoon",
        "shuru karo",
        "shuru kar do",
        "ijazat hai",
        # Urdu
        "منظور ہے",
        "منظور",
        "ہاں کر دو",
        "ہاں کر دیں",
        "جی ہاں کر دیں",
        "شروع کریں",
        "شروع کر دیں",
        "اجازت ہے",
        "میں منظوری دیتا ہوں",
        "میں منظوری دیتی ہوں",
        # Hindi
        "हाँ कर दो",
        "हां कर दो",
        "जी हाँ कर दीजिए",
        "मंज़ूर है",
        "मंजूर है",
        "स्वीकृत है",
        "शुरू करो",
        "शुरू कर दो",
        "अनुमति है",
        "मैं मंज़ूरी देता हूँ",
        "मैं मंजूरी देती हूं",
        # Arabic
        "اوافق",
        "موافق",
        "وافقت",
        "تمت الموافقة",
        "نعم تفضل",
        "اعتمد",
        "مصرح لك",
    ]
)


def classify_approval(text: Any) -> ApprovalCue:
    """Label one owner message. Only EXPLICIT_YES can create a scope; every other label is 'not approved'.
    Never raises; a non-string, empty, or over-long input is UNKNOWN/VAGUE (fail closed)."""
    if not isinstance(text, str):
        return ApprovalCue.UNKNOWN
    if len(text) > MAX_CUE_CHARS:
        return ApprovalCue.UNKNOWN
    if not text.strip():
        return ApprovalCue.VAGUE
    if any(c in _QUOTE_CHARS for c in text) or any(
        line.lstrip().startswith(">") for line in text.splitlines()
    ):
        return ApprovalCue.QUOTED
    toks = _tokens(text)
    if not toks:
        return ApprovalCue.VAGUE
    if any(t in _FORWARD_TOKENS for t in toks):
        return ApprovalCue.QUOTED
    if any(t in _NEGATIVE for t in toks):
        return ApprovalCue.NEGATIVE
    if any(q in text for q in _QUESTION) or any(t in _CONDITIONAL for t in toks):
        return ApprovalCue.CONDITIONAL
    padded = " " + " ".join(toks) + " "
    if _has_phrase(padded, _EXPLICIT):
        return ApprovalCue.EXPLICIT_YES
    return ApprovalCue.VAGUE


def scope_sha(scope_text: str, tools: Any, limits: Mapping[str, int]) -> str:
    """Hash of the exact scope: text (byte for byte), sorted tool names, sorted limits."""
    body = json.dumps(
        [scope_text, sorted(tools), sorted(limits.items())],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ApprovedScope:
    scope_text: str
    tools: frozenset[str]
    limits: tuple[tuple[str, int], ...]
    expires_at: datetime
    approver: str
    approval_source: str
    approved_at: datetime
    scope_sha: str
    cue_sha: str  # hash of the approval message (the message itself is not kept)
    seal: str

    def limit(self, name: str) -> int | None:
        for k, v in self.limits:
            if k == name:
                return v
        return None

    def is_intact(self) -> bool:
        try:
            lim = dict(self.limits)
            return self.scope_sha == scope_sha(
                self.scope_text, self.tools, lim
            ) and self.seal == _seal(self)
        except Exception:  # noqa: BLE001
            return False

    def is_live(self, now: datetime) -> bool:
        return isinstance(now, datetime) and now.tzinfo is not None and now < self.expires_at


def _seal(s: ApprovedScope) -> str:
    body = json.dumps(
        [
            s.scope_sha,
            sorted(s.tools),
            list(s.limits),
            s.expires_at.isoformat(),
            s.approver,
            s.approval_source,
            s.approved_at.isoformat(),
            s.cue_sha,
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ScopeResult:
    ok: bool
    scope: ApprovedScope | None
    reasons: tuple[str, ...]


def _refuse(*reasons: str) -> ScopeResult:
    return ScopeResult(False, None, tuple(reasons))


def create_scope(
    *,
    scope_text: Any,
    tools: Any,
    limits: Any,
    expires_at: Any,
    approver: Any,
    approval_source: Any,
    approval_text: Any,
    referenced_sha: Any,
    task_owner: Any,
    now: Any,
) -> ScopeResult:
    """The only constructor of an approved scope. Never raises; every failure is a refusal with reasons."""
    try:
        reasons: list[str] = []
        if not isinstance(now, datetime) or now.tzinfo is None:
            return _refuse("now must be a timezone-aware datetime")
        if not isinstance(scope_text, str) or not scope_text.strip():
            reasons.append("scope text is empty")
        elif len(scope_text) > MAX_SCOPE_CHARS:
            reasons.append("scope text is too long")
        if (
            not isinstance(tools, (list, tuple, set, frozenset))
            or not tools
            or len(tools) > MAX_TOOLS
        ):
            reasons.append("tools must be a non-empty list within the cap")
            tool_set: frozenset[str] = frozenset()
        else:
            tool_set = frozenset(tools) if all(isinstance(t, str) for t in tools) else frozenset()
            if not tool_set:
                reasons.append("tool names must be text")
        for t in sorted(tool_set):
            cls = TOOL_CLASSES.get(t)
            if cls is None:
                reasons.append(f"unknown tool: {t[:40]}")
            elif cls in NEVER_SCOPED:
                reasons.append(f"tool {t} is never allowed (payment or credential)")
        lim: dict[str, int] = {}
        if not isinstance(limits, Mapping) or len(limits) > MAX_LIMITS:
            reasons.append("limits must be a mapping within the cap")
        else:
            for k, v in limits.items():
                if (
                    not isinstance(k, str)
                    or not k
                    or len(k) > MAX_ID
                    or isinstance(v, bool)
                    or not isinstance(v, int)
                    or not 0 <= v <= MAX_LIMIT_VALUE
                ):
                    reasons.append("a limit is malformed")
                    break
                lim[k] = v
        if not isinstance(expires_at, datetime) or expires_at.tzinfo is None:
            reasons.append("expiry must be a timezone-aware datetime")
        elif expires_at <= now:
            reasons.append("expiry is not in the future")
        elif expires_at - now > MAX_VALIDITY:
            reasons.append("expiry is too far away")
        if (
            not isinstance(approver, str)
            or not approver.strip()
            or len(approver) > MAX_ID
            or approver.strip().casefold() in FORBIDDEN_APPROVERS
        ):
            reasons.append("approver must be a named person, never pi or a model")
        elif (
            isinstance(task_owner, str)
            and approver.strip().casefold() == task_owner.strip().casefold()
        ):
            reasons.append("approver must differ from the task owner")
        if approval_source not in APPROVAL_SOURCES:
            reasons.append("approval source is not an accepted channel")
        cue = classify_approval(approval_text)
        if cue is not ApprovalCue.EXPLICIT_YES:
            reasons.append(f"approval is not an explicit yes ({cue.value})")
        if reasons:
            return _refuse(*reasons)
        assert (
            isinstance(scope_text, str)
            and isinstance(approver, str)
            and isinstance(approval_text, str)
        )
        assert isinstance(expires_at, datetime)
        sha = scope_sha(scope_text, tool_set, lim)
        if referenced_sha != sha:
            return _refuse("the approval does not refer to this exact scope")
        draft = ApprovedScope(
            scope_text=scope_text,
            tools=tool_set,
            limits=tuple(sorted(lim.items())),
            expires_at=expires_at,
            approver=approver.strip(),
            approval_source=str(approval_source),
            approved_at=now,
            scope_sha=sha,
            cue_sha=hashlib.sha256(approval_text.encode("utf-8")).hexdigest(),
            seal="",
        )
        sealed = ApprovedScope(**{**draft.__dict__, "seal": _seal(draft)})
        return ScopeResult(True, sealed, ())
    except Exception:  # noqa: BLE001 - fail closed
        return _refuse("malformed input")
