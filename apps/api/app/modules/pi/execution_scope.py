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

Approval grammar. EXPLICIT_YES only when the WHOLE message is a short first-person present-tense approval:
optional filler words, exactly one approval phrase, optional filler words, and nothing else (no digits,
no symbols, no other content words). Anything with a second clause, a time word, a condition, a hedge, a
quote, a third person, a past tense, a negation or a question is not an approval. Default: not approved.

Forgery. An ApprovedScope carries a keyed HMAC seal. The key is `PI_EXECUTION_SEAL_KEY` (server-held, at
least 16 characters) or, when unset, a random per-process key. Only `create_scope` can produce a valid
seal, so a directly constructed object fails `is_intact`. Anything that is stored and read back (a later
persistence layer) needs the same key held on the server, otherwise stored scopes will not verify.
PRODUCTION MUST set PI_EXECUTION_SEAL_KEY: with the per-process random fallback, seals do not survive a
restart and differ between workers.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

MAX_CUE_CHARS = 1000
MAX_CUE_GRAMMAR_CHARS = 120
MAX_SCOPE_CHARS = 20_000
MAX_TOOLS = 50
MAX_LIMITS = 20
MAX_LIMIT_VALUE = 1_000_000
MAX_VALIDITY = timedelta(days=30)
MAX_ID = 120
MAX_FILLERS = 6

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


def ident(value: Any) -> str:
    """Identity form for comparing people: NFKC, casefold, whitespace collapsed (fullwidth letters match)."""
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def named_person(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(ident(value))
        and len(value) <= MAX_ID
        and ident(value) not in FORBIDDEN_APPROVERS
    )


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
        if 0x064B <= o <= 0x065F or o in (0x0670, 0x0640, 0x200C, 0x200D, 0x200E, 0x200F, 0x093C):
            continue  # Arabic marks, tatweel, joiners
        out.append(ch)
    t = "".join(out)
    for a in "أإآٱ":
        t = t.replace(a, "ا")
    t = t.replace("\u0901", "\u0902")
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


def _words(text: str) -> frozenset[str]:
    return frozenset(_tokens(text))


def _phrases(items: list[str]) -> frozenset[tuple[str, ...]]:
    return frozenset(tuple(_tokens(p)) for p in items)


_NEGATIVE = _words(
    "no not never dont doesnt cant cannot wont wouldnt shouldnt isnt arent nothing nobody none neither nor without hold wait stop cancel pause "
    "stopped declined reject rejected refuse nahi nahin nhi nai mat na ruk ruko rukein ruka band koi "
    "نہیں نہی نھیں مت نہ رکو رکیں روکو روک کچھ "
    "नहीं नही मत ना रुको रुकिए रोको कुछ "
    "لا ليس لن توقف قف الغ بدون"
)
_CONDITIONAL = _words(
    "if unless but once until after before when whenever while as long depending depends condition conditions case assuming assume except "
    "provided maybe perhaps probably possibly guess think suppose might could would should may whether or only also just kidding joking later "
    "tomorrow tonight today yesterday earlier next week weekend month monday tuesday wednesday thursday friday saturday sunday now soon "
    "morning evening night again first then with about regarding "
    "agar lekin magar par jab baad shayad shart warna kal aaj parso abhi pehle phir sirf bhi "
    "اگر لیکن مگر جب بعد شاید شرط ورنہ کل آج پہلے پھر صرف بھی "
    "अगर लेकिन मगर जब बाद शायद शर्त वरना कल आज पहले फिर सिर्फ भी "
    "اذا لكن ربما بعد عندما بشرط غدا لاحقا اليوم امس قبل ثم فقط ايضا"
)
_FORWARD = _words(
    "fwd forwarded wrote said says say told tell asked ask he she they his her their boss manager wants want kaha kehta kehti bola likha "
    "unhone woh wo usne "
    "کہا کہتا بولا وہ انہوں "
    "कहा बोला लिखा वह उन्होंने "
    "قال كتب هو هي هم"
)
_QUOTE_CHARS = frozenset('"“”„‟«»‹›「」`´')
_QUESTION = ("?", "؟", "？")
_PUNCT_OK = frozenset(",.!،۔؛-–—")

# Object words are stripped before matching ("I approve this", "main ye approve karta hoon").
_OBJECTS = _words(
    "it this that ye yeh isko isay ise the plan scope task work action یہ اسے اس यह इसे इसको هذا ذلك"
)
_FILLERS = _words(
    "please kindly yes yep yeah ok okay sure hereby absolutely certainly sir madam bhai sahab sahib "
    "thanks thankyou shukriya shukria meherbani mehrbani ji jee haan han haa ha hanji bilkul zaroor "
    "ہاں جی شکریہ مہربانی بالکل "
    "हाँ हां जी धन्यवाद शुक्रिया बिल्कुल "
    "نعم شكرا بالتاكيد على"
)
_NAME_INTRO = _words("thanks regards from shukriya shukria")
_AS_REF = _words("written shown described presented stated above attached")
_DANGER = _words(
    "delete remove erase wipe drop send email mail message pay payment refund transfer publish deploy cancel everything all more also "
    "plus too bigger another other new extra production live database customers customer everyone"
)


def _strip_objects(toks: list[str]) -> tuple[str, ...]:
    return tuple(t for t in toks if t not in _OBJECTS)


_CORES = frozenset(
    _strip_objects(_tokens(p))
    for p in [
        # English ("approve" alone is deliberately NOT here: it is also the command and the question word)
        "i approve",
        "we approve",
        "approved",
        "go ahead",
        "go on",
        "proceed",
        "you may proceed",
        "you can proceed",
        "you may go ahead",
        "you can go ahead",
        "i confirm",
        "we confirm",
        "confirmed",
        "i authorise",
        "i authorize",
        "we authorise",
        "we authorize",
        "authorised",
        "authorized",
        "i give my approval",
        "approval given",
        "go ahead and proceed",
        "i hereby approve",
        "we hereby approve",
        "i hereby authorise",
        "i hereby authorize",
        "i authorise you to go ahead",
        "i authorize you to go ahead",
        "i authorise you to proceed",
        "i authorize you to proceed",
        # Roman Urdu
        "kar do",
        "kar den",
        "kar dein",
        "kar dijiye",
        "kijiye",
        "karo",
        "shuru karo",
        "shuru kar do",
        "shuru kijiye",
        "shuru kar dein",
        "manzoor hai",
        "mangoor hai",
        "manzoor",
        "approve hai",
        "approve karta hoon",
        "approve karti hoon",
        "main approve karta hoon",
        "main approve karti hoon",
        "ijazat hai",
        "main manzoor karta hoon",
        "main manzoor karti hoon",
        "mujhe manzoor hai",
        "main ijazat deta hoon",
        "main ijazat deti hoon",
        "ijazat deta hoon",
        "ijazat deti hoon",
        # Urdu
        "منظور ہے",
        "منظور",
        "کر دو",
        "کر دیں",
        "شروع کریں",
        "شروع کر دیں",
        "شروع کر دو",
        "اجازت ہے",
        "میں منظوری دیتا ہوں",
        "میں منظوری دیتی ہوں",
        "میں منظور کرتا ہوں",
        "میں منظور کرتی ہوں",
        "میں اجازت دیتا ہوں",
        "میں اجازت دیتی ہوں",
        "مجھے منظور ہے",
        # Hindi
        "कर दो",
        "कर दीजिए",
        "शुरू करो",
        "शुरू कर दो",
        "शुरू कीजिए",
        "मंज़ूर है",
        "मंजूर है",
        "मंज़ूर",
        "मंजूर",
        "स्वीकृत है",
        "अनुमति है",
        "मैं मंज़ूरी देता हूँ",
        "मैं मंजूरी देता हूं",
        "मैं मंजूरी देती हूं",
        "मैं मंज़ूरी देती हूँ",
        "मैं स्वीकृति देता हूँ",
        "मैं स्वीकृति देती हूँ",
        "मैं अनुमति देता हूं",
        "मैं अनुमति देती हूं",
        "मैं मंज़ूर करता हूँ",
        "मैं मंज़ूर करती हूँ",
        "मुझे मंज़ूर है",
        # Arabic
        "اوافق",
        "انا اوافق",
        "موافق",
        "اني موافق",
        "وافقت",
        "تمت الموافقة",
        "تفضل",
        "تفضل بالبدء",
        "اعتمد",
        "مصرح لك",
        "اعطيك الموافقة",
        "اصرح لك",
        "اصرح لك بالبدء",
    ]
)
_CORE_WORDS = frozenset(w for c in _CORES for w in c)
_KNOWN = (
    _FILLERS | _OBJECTS | _NEGATIVE | _CONDITIONAL | _FORWARD | _DANGER | _CORE_WORDS | _NAME_INTRO
)
MAX_NAME_WORDS = 3


def _has_quote(text: str) -> bool:
    for i, ch in enumerate(text):
        if ch in _QUOTE_CHARS:
            return True
        if ch in "'‘’":
            before = text[i - 1] if i else ""
            after = text[i + 1] if i + 1 < len(text) else ""
            if not (before.isalpha() and after.isalpha()):
                return True  # a lone apostrophe is a quote mark; only a contraction (don't) is not
    return False


def _items(text: str) -> list[tuple[str, str, int]]:
    out: list[tuple[str, str, int]] = []
    cur: list[str] = []
    start = 0
    for i, ch in enumerate(text):
        if unicodedata.category(ch)[0] in "LMN":
            if not cur:
                start = i
            cur.append(ch)
        elif cur:
            w = "".join(cur)
            out.append((_norm(w), w, start))
            cur = []
    if cur:
        w = "".join(cur)
        out.append((_norm(w), w, start))
    return [it for it in out if it[0]]


def _is_name(norm: str, orig: str) -> bool:
    return (
        orig.isascii()
        and orig.isalpha()
        and 2 <= len(orig) <= 15
        and orig[0].isupper()
        and orig[1:].islower()
        and norm not in _KNOWN
    )


def _is_grammar_approval(text: str, tokens: list[str]) -> bool:
    """The whole message is: fillers, at most one name (1 to 3 capitalised Latin words, only after a dash,
    a comma, 'thanks', 'regards' or 'from'), exactly one approval phrase, and nothing else."""
    if len(text) > MAX_CUE_GRAMMAR_CHARS:
        return False
    for ch in text:
        cat = unicodedata.category(ch)
        if not (cat[0] in "LM" or ch.isspace() or ch in _PUNCT_OK):
            return False  # digits, symbols, brackets, emoji, colons ...
    nfk = unicodedata.normalize("NFKC", text)
    kept: list[str] = []
    names = 0
    prev = ""
    prev_name = False
    for norm, orig, start in _items(nfk):
        if names < MAX_NAME_WORDS and _is_name(norm, orig):
            before = nfk[:start].rstrip()[-1:]
            if (before and before in "-,–—،") or prev in _NAME_INTRO or prev_name:
                names += 1
                prev_name = True
                prev = norm
                continue
        prev_name = False
        prev = norm
        kept.append(norm)
    folded: list[str] = []
    for t in kept:
        if t == "you" and folded and folded[-1] == "thank":
            folded[-1] = "thanks"
        elif t in _AS_REF and folded and folded[-1] == "as":
            folded.pop()
            if folded and folded[-1] in ("exactly", "precisely"):
                folded.pop()
        else:
            folded.append(t)
    toks = _strip_objects(folded)
    fillers = _FILLERS | (_words("from regards") if names else frozenset())
    if not toks or len(toks) > MAX_FILLERS + 8:
        return False
    for core in _CORES:
        n = len(core)
        for i in range(len(toks) - n + 1):
            if tuple(toks[i : i + n]) != core:
                continue
            rest = toks[:i] + toks[i + n :]
            if len(rest) <= MAX_FILLERS and all(t in fillers for t in rest):
                return True
    return False


def classify_approval(text: Any) -> ApprovalCue:
    """Label one owner message. Only EXPLICIT_YES can create a scope; every other label is 'not approved'.
    Never raises; a non-string, empty, or over-long input is UNKNOWN/VAGUE (fail closed). A question mark
    is a symbol, so it already fails the grammar's character check (no separate branch is needed); the
    label below still reports such messages as CONDITIONAL. A bare 'approve' is VAGUE: it is also the
    command and question word, so a subject is required ('I approve', 'approved', 'approve hai')."""
    if not isinstance(text, str):
        return ApprovalCue.UNKNOWN
    if len(text) > MAX_CUE_CHARS:
        return ApprovalCue.UNKNOWN
    if not text.strip():
        return ApprovalCue.VAGUE
    if _has_quote(text) or any(line.lstrip().startswith(">") for line in text.splitlines()):
        return ApprovalCue.QUOTED
    toks = _tokens(text)
    if not toks:
        return ApprovalCue.VAGUE
    if _is_grammar_approval(text, toks):
        return ApprovalCue.EXPLICIT_YES
    if any(t in _FORWARD for t in toks):
        return ApprovalCue.QUOTED
    if any(t in _NEGATIVE for t in toks):
        return ApprovalCue.NEGATIVE
    if any(q in text for q in _QUESTION) or any(t in _CONDITIONAL for t in toks):
        return ApprovalCue.CONDITIONAL
    if any(any(unicodedata.category(c) == "Nd" for c in t) for t in toks):
        return ApprovalCue.UNKNOWN
    return ApprovalCue.VAGUE


def scope_sha(scope_text: str, tools: Any, limits: Mapping[str, int]) -> str:
    """Hash of the exact scope: text (byte for byte), sorted tool names, sorted limits."""
    body = json.dumps(
        [scope_text, sorted(tools), sorted(limits.items())],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _load_key() -> bytes:
    raw = os.environ.get("PI_EXECUTION_SEAL_KEY", "")
    return raw.encode("utf-8") if len(raw) >= 16 else secrets.token_bytes(32)


_KEY = _load_key()


def seal_mac(parts: Any) -> str:
    """Keyed HMAC-SHA256 over canonical JSON. Cannot be recomputed without the server-held key."""
    body = json.dumps(parts, ensure_ascii=True, separators=(",", ":"), default=str)
    return hmac.new(_KEY, body.encode("utf-8"), hashlib.sha256).hexdigest()


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
    task_owner: str
    task_creator: str
    seal: str

    def limit(self, name: str) -> int | None:
        for k, v in self.limits:
            if k == name:
                return v
        return None

    def issues(self) -> list[str]:
        """Everything re-checked at use, not only at creation. Empty list means genuine and sane."""
        try:
            out: list[str] = []
            if not isinstance(self.seal, str) or not hmac.compare_digest(self.seal, _seal(self)):
                return ["scope record was not issued by create_scope or was altered"]
            if self.scope_sha != scope_sha(self.scope_text, self.tools, dict(self.limits)):
                out.append("scope hash does not match its content")
            if not named_person(self.approver) or ident(self.approver) in {
                ident(self.task_owner),
                ident(self.task_creator),
            }:
                out.append("approver is not a valid independent person")
            if self.approval_source not in APPROVAL_SOURCES:
                out.append("approval source is not accepted")
            if not self.tools or len(self.tools) > MAX_TOOLS:
                out.append("tool list is malformed")
            for t in self.tools:
                cls = TOOL_CLASSES.get(t)
                if cls is None or cls in NEVER_SCOPED:
                    out.append("scope lists an unknown or forbidden tool")
                    break
            if not self.approved_at < self.expires_at <= self.approved_at + MAX_VALIDITY:
                out.append("expiry is outside the allowed window")
            for _k, v in self.limits:
                if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= MAX_LIMIT_VALUE:
                    out.append("a limit is out of range")
                    break
            return out
        except Exception:  # noqa: BLE001
            return ["scope record is malformed"]

    def is_intact(self) -> bool:
        return not self.issues()

    def is_live(self, now: datetime) -> bool:
        try:
            return (
                isinstance(now, datetime)
                and now.tzinfo is not None
                and self.approved_at <= now < self.expires_at <= self.approved_at + MAX_VALIDITY
            )
        except Exception:  # noqa: BLE001
            return False


def _seal(s: ApprovedScope) -> str:
    return seal_mac(
        [
            "scope",
            s.scope_sha,
            sorted(s.tools),
            list(s.limits),
            s.expires_at.isoformat(),
            s.approver,
            s.approval_source,
            s.approved_at.isoformat(),
            s.cue_sha,
            s.task_owner,
            s.task_creator,
        ]
    )


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
    task_creator: Any,
    now: Any,
) -> ScopeResult:
    """The only constructor of a valid approved scope. Never raises; every failure is a refusal with reasons."""
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
        if not named_person(approver):
            reasons.append("approver must be a named person, never pi or a model")
        if not named_person(task_owner) or not named_person(task_creator):
            reasons.append(
                "the task owner and creator must be named so independence can be checked"
            )
        elif named_person(approver) and ident(approver) in {ident(task_owner), ident(task_creator)}:
            reasons.append("approver must differ from the task owner and creator")
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
        assert (
            isinstance(expires_at, datetime)
            and isinstance(task_owner, str)
            and isinstance(task_creator, str)
        )
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
            task_owner=task_owner.strip(),
            task_creator=task_creator.strip(),
            seal="",
        )
        sealed = ApprovedScope(**{**draft.__dict__, "seal": _seal(draft)})
        return ScopeResult(True, sealed, ())
    except Exception:  # noqa: BLE001 - fail closed
        return _refuse("malformed input")
