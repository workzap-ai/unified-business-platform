"""PS-4: text hygiene and the honesty and completeness checks of a solution blueprint.

Pure functions, no database, no model. Nothing here raises: every reader tolerates the wrong type.

  fold / numbers_in / canon_number   digits of any script to ASCII, numbers found, one spelling each
  has_money / has_promise / has_credential   the three things a blueprint text may never carry
  clean_text                         cut a text to size, drop sentences that promise or ask for
                                     credentials, mask money (the builder uses this on option text)
  check_blueprint                    `blueprint_issues` of a built blueprint, against known numbers
  section_report                     which sections are present and which are grounded

Limits, stated: number words are understood in English and Roman Urdu only (two, teen, paanch ...);
Urdu and Arabic number words are not, only their digits. The promise and credential lists are
word lists, not understanding; a clever paraphrase passes. `brain_docs.MONEY_IN_TEXT` is the
reference money pattern: `MONEY` here is a superset of it (a unit test asserts so).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from app.modules.pi.blueprint_types import (
    INSUFFICIENT,
    READY,
    REFUSED,
    ROLES,
    STEP_KINDS,
    Blueprint,
)

MASK = "[--]"
_DIGITS = {c: str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_DIGITS.update({c: str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})
_DIGITS.update({c: str(i) for i, c in enumerate("０１２３４５６７８９")})
_DIGIT_TABLE = str.maketrans(_DIGITS)
_INVISIBLE = dict.fromkeys(
    [0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0xFEFF, 0x00AD, 0x061C, 0x0640]
    + list(range(0x064B, 0x0660))
    + [0x0670]
)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

NUM = re.compile(r"(?<![A-Za-z_\d])\d+(?:[.,]\d+)*")
_WORD_NUMBERS = {
    "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9", "ten": "10", "twenty": "20", "hundred": "100",
    "thousand": "1000", "dozen": "12",
    "teen": "3", "paanch": "5", "panch": "5", "saat": "7", "aath": "8", "das": "10",
    "sau": "100", "hazaar": "1000", "hazar": "1000",
}  # fmt: skip
NUMBER_WORD = re.compile(
    r"\b(" + "|".join(sorted(_WORD_NUMBERS, key=len, reverse=True)) + r")\b", re.I
)

MONEY = re.compile(
    r"\b(?:rs\.?|pkr|aed|cad|usd|sar|dirhams?|rupees?|rupay[ae]?|lakhs?|lacs?|crores?|dollars?|riyals?)\b"
    r"|[$€£₹]|روپ(?:ے|یہ|ی)|ریال|درهم|دولار|دينار"
    r"|\b\d{1,3}(?:,\d{2,3})+(?:\.\d+)?\b"
    r"|\b\d+(?:\.\d+)?\s?(?:k|m|lakh|lac|crore|million|thousand|hazaar|hazar|grand)\b"
    r"|\b(?:cost|costs|price|priced|fee|fees|charge|charged|budget|pay|paying|cheap|free)\b\D{0,15}\d{3,}"
    r"|\b(?:for free|at no cost|no cost|free of charge|cheaply)\b",
    re.IGNORECASE,
)

_DENIED = re.compile(
    r"\b(?:no|not|cannot|can't|cant|never|without|nahi|nahin|na)\b[^.!?\n]{0,25}\b(?:guarantee[sd]?|promise[sd]?|garanti|guarantee)\b"
    r"|\b(?:guarantee|garanti|promise)\b[^.!?\n]{0,12}\b(?:nahi|nahin|nhi|nahee)\b"
    r"|لا\s?(?:نضمن|أضمن|اضمن)|لا\s?(?:يمكن\w*\s)?ضمان"
    r"|گارنٹی[^.!?\n]{0,12}نہیں|ضمانت[^.!?\n]{0,12}نہیں",
    re.IGNORECASE,
)
PROMISE = re.compile(
    r"\b(?:guarantee[sd]?|guaranteeing|promise[sd]?|definitely|certainly|surely|for sure|"
    r"risk[- ]free|zero risk|no risk|never fails?|cannot fail|can't fail|always works?|"
    r"100\s?%|hundred percent|trust me|bound to|ensure[sd]? that|you will see|"
    r"will (?:double|triple|increase|boost|grow|save|fix|solve|eliminate|stop|end|cut|raise|"
    r"remove|improve|reduce|make you)|going to (?:double|boost|fix|solve|save|increase)|"
    r"saves? you|pays? for itself|roi)\b"
    r"|\b(?:zaroor|zarur|yaqeen\s?se|yaqeeni|yakeeni|pakka|pakki|lazmi|garanti|guarantee|"
    r"waada|wada|kabhi\s+fail\s+nahi|ho\s+jaye\s?ga|ho\s+jaega|ho\s+jayega|theek\s+ho\s+jaye\s?ga|"
    r"sau\s+(?:fi\s?sad|percent)|100\s?percent|bilkul\s+(?:theek|hal))\b"
    r"|(?<![ء-يٱ-ۓ])(?:ال|بال|وال)?(?:ضرور|یقینی|یقین\s?سے|گارنٹی|ضمانت|پکا|وعدہ|"
    r"لازمی\s+ہو|ہو\s+جائے\s?گا|بالکل\s+ٹھیک|کبھی\s+ناکام\s+نہیں|سو\s+فیصد|"
    r"مضمون|نضمن|أضمن|ضمان|بالتأكيد|بالتاكيد|حتما|وعد|وعدا|نعدك|أعدك|لن\s+يفشل|"
    r"مئة\s+بالمئة|مائة\s+بالمائة|سيتحسن|سيحل|سيزيد|سيتضاعف)(?![ء-يٱ-ۓ])",
    re.IGNORECASE,
)
CREDENTIAL = re.compile(
    r"\b(?:passwords?|passcodes?|otp|one[- ]time (?:code|password|pin)|cvv|cvc|pin code|"
    r"card (?:number|no)|cnic|id (?:number|card number)|iban|secret key|api key|login details)\b"
    r"|پاس\s?ورڈ|او\s?ٹی\s?پی|شناختی کارڈ نمبر|كلمة المرور|كلمه المرور|رقم البطاقة|رمز التحقق",
    re.IGNORECASE,
)
_MASKS = re.compile(re.escape(MASK) + r"(?:\s*" + re.escape(MASK) + r")+")
_SENTENCES = re.compile(r"(?<=[.!?۔؟])\s+|\n+")
_WS = re.compile(r"\s+")


# ---- text --------------------------------------------------------------------------------------


def text_of(value: Any) -> str:
    """A string as it is; anything else reads as empty."""
    return value if isinstance(value, str) else ""


def fold_digits(text: str) -> str:
    """Arabic-Indic, Extended Arabic-Indic and full-width digits to ASCII, one character each, so a
    position in the result is a position in the original."""
    return text.translate(_DIGIT_TABLE)


def fold(text: str) -> str:
    """For matching only: NFKC, casefold, digits to ASCII, zero-width marks, tatweel and Arabic
    diacritics removed, whitespace collapsed."""
    t = unicodedata.normalize("NFKC", text_of(text)).translate(_INVISIBLE)
    return _WS.sub(" ", fold_digits(t).casefold()).strip()


def tidy(text: Any, cap: int = 300) -> str:
    """Control and zero-width characters out, whitespace collapsed, cut at a word boundary."""
    t = text_of(text)[: cap * 4]
    t = _CONTROL.sub(" ", t).translate({k: None for k in (0x200B, 0x200C, 0x200D, 0xFEFF, 0x2060)})
    t = _WS.sub(" ", t).strip()
    if len(t) <= cap:
        return t
    cut = t[:cap]
    space = cut.rfind(" ")
    return (cut[:space] if space > cap // 2 else cut).rstrip()


def canon_number(raw: str) -> str:
    """One spelling per number: 1,000 and 1000 and 1000.0 are the same; leading zeros go."""
    s = fold_digits(raw).replace(",", "")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    s = s.lstrip("0")
    return s if s and s[0].isdigit() else ("0" + s if s else "0")


def numbers_in(text: Any) -> list[str]:
    """Every number in a text, canonical, digits of any script plus English and Roman Urdu number
    words. An id like S1 or p2 is not a number (a letter before the digits)."""
    t = unicodedata.normalize("NFKC", text_of(text)).translate(_INVISIBLE)
    folded = fold_digits(t)
    out = [canon_number(m.group()) for m in NUM.finditer(folded)]
    out += [_WORD_NUMBERS[m.group().casefold()] for m in NUMBER_WORD.finditer(folded)]
    return out


def has_money(text: Any) -> bool:
    return MONEY.search(fold(text_of(text))) is not None


def has_credential(text: Any) -> bool:
    return CREDENTIAL.search(fold(text_of(text))) is not None


def has_promise(text: Any) -> bool:
    """A promise or guarantee. A denied guarantee ("I cannot guarantee anything") is cut out first
    and is not one; the rest of the sentence still counts."""
    t = _DENIED.sub(" ", fold(text_of(text)))
    if PROMISE.search(t):
        return True
    return "guarantee" in re.sub(r"[^a-z]", "", t)  # "g u a r a n t e e" and "guar-antee"


def clean_text(text: Any, known: frozenset[str], cap: int = 300) -> tuple[str, tuple[str, ...]]:
    """Make an option's or an owner's text safe to place in a blueprint.

    Returns (text, notes). Sentences with a promise or a credential are removed; money and a number
    that is not in `known` are replaced by MASK. The notes are codes ("promise", "credential",
    "money", "number") for the builder to list as unknowns. A text that is all removed
    reads as ""."""
    notes: list[str] = []
    kept: list[str] = []
    for sentence in _SENTENCES.split(unicodedata.normalize("NFKC", tidy(text, cap * 2))):
        s = sentence.strip()
        if not s:
            continue
        if has_promise(s):
            notes.append("promise")
            continue
        if has_credential(s):
            notes.append("credential")
            continue
        kept.append(s)
    out = " ".join(kept)
    out, n_money = _mask_money(out)
    if n_money:
        notes.append("money")
    out, n_num = _mask_numbers(out, known)
    if n_num:
        notes.append("number")
    out = _MASKS.sub(MASK, out)
    return tidy(out, cap), tuple(dict.fromkeys(notes))


def _mask_money(text: str) -> tuple[str, int]:
    lowered = fold_digits(text)
    count = 0
    out: list[str] = []
    last = 0
    for m in MONEY.finditer(lowered):
        out.append(text[last : m.start()])
        out.append(MASK)
        last = m.end()
        count += 1
    out.append(text[last:])
    return "".join(out), count


def _mask_numbers(text: str, known: frozenset[str]) -> tuple[str, int]:
    folded = fold_digits(text)
    spans: list[tuple[int, int]] = []
    for m in NUM.finditer(folded):
        if canon_number(m.group()) not in known:
            spans.append((m.start(), m.end()))
    for m in NUMBER_WORD.finditer(folded):
        if _WORD_NUMBERS[m.group().casefold()] not in known:
            spans.append((m.start(), m.end()))
    if not spans:
        return text, 0
    spans.sort()
    out: list[str] = []
    last = 0
    count = 0
    for a, b in spans:
        if a < last:
            continue
        out.append(text[last:a])
        out.append(MASK)
        last = b
        count += 1
    out.append(text[last:])
    return "".join(out), count


# ---- the checks --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Issue:
    code: str
    where: str
    text: str


SECTIONS = (
    "summary",
    "architecture",
    "workflow",
    "dependencies",
    "external",
    "responsibilities",
    "costs",
    "timeline",
    "risks",
    "milestones",
    "acceptance",
    "success",
    "rollback",
    "approvals",
    "constraints",
)


def free_texts(bp: Blueprint) -> Iterator[tuple[str, str]]:
    """Every free-text field of a blueprint with a name for where it is (ids and enums excluded)."""
    if bp.summary is not None:
        yield "summary", bp.summary.text
    for m in bp.modules:
        yield f"module {m.id}", m.name
        for n in m.not_changed:
            yield f"module {m.id} not changed", n
    for s in bp.steps:
        yield f"step {s.id}", s.text
        yield f"step {s.id} done-check", s.done_check
    for e in bp.external:
        yield f"external {e.id}", e.text
    for c in bp.costs:
        yield "cost item", c.item
        yield "cost source", c.source
    for t in bp.timeline:
        yield f"timeline {t.item}", t.duration
        yield f"timeline {t.item} source", t.source
    for i, r in enumerate(bp.risks):
        yield f"risk {i + 1}", r.text
    for i, u in enumerate(bp.unknowns):
        yield f"unknown {i + 1}", u
    for m2 in bp.milestones:
        yield f"milestone {m2.id}", m2.name
        yield f"milestone {m2.id} check", m2.check
    for c2 in bp.acceptance:
        yield f"acceptance {c2.id}", c2.text
    for me in bp.success:
        yield f"measure {me.id} what", me.what
        yield f"measure {me.id} baseline", me.baseline
        yield f"measure {me.id} target", me.target
    for k in bp.constraints:
        yield f"constraint {k.label}", k.text
        yield f"constraint {k.label} reason", k.reason
    for i, x in enumerate(bp.missing):
        yield f"missing {i + 1}", x.text
    for i, x2 in enumerate(bp.refusal):
        yield f"refusal {i + 1}", x2
    yield "next question", bp.next_question


def section_report(bp: Blueprint) -> dict[str, tuple[bool, bool]]:
    """For each section: (present with non-empty text, grounded). Grounded means the content comes
    from the owner, the option or staff; a section that only says "not known yet" is present but not
    grounded. Cost is grounded only by a staff amount, timeline only by a given duration."""
    gates = [s for s in bp.steps if s.kind == "approval"]
    rollback = [s for s in bp.steps if s.kind == "rollback"]
    option_steps = [s for s in bp.steps if s.source == "option"]
    return {
        "summary": (
            bool(bp.summary and bp.summary.text.strip()),
            bool(bp.summary and bp.summary.problem_ids),
        ),
        "architecture": (
            any(m.name.strip() for m in bp.modules),
            any(m.source == "option" for m in bp.modules),
        ),
        "workflow": (any(s.text.strip() for s in bp.steps), bool(option_steps)),
        "dependencies": (bool(bp.edges) or len(bp.steps) > 0, bool(bp.edges)),
        "external": (
            any(e.text.strip() for e in bp.external),
            any(e.text.strip() for e in bp.external),
        ),
        "responsibilities": (
            any(r.role and r.steps for r in bp.responsibilities),
            any(r.steps for r in bp.responsibilities),
        ),
        "costs": (bool(bp.costs), any(c.amount is not None for c in bp.costs)),
        "timeline": (bool(bp.timeline), any(t.duration.strip() for t in bp.timeline)),
        "risks": (
            any(r.text.strip() for r in bp.risks) or bool(bp.unknowns),
            any(r.source == "option" for r in bp.risks),
        ),
        "milestones": (
            any(m.steps and m.name.strip() for m in bp.milestones),
            any(m.steps for m in bp.milestones),
        ),
        "acceptance": (
            any(c.text.strip() for c in bp.acceptance),
            any(c.text.strip() for c in bp.acceptance),
        ),
        "success": (
            any(m.what.strip() for m in bp.success),
            any(m.baseline.strip() for m in bp.success),
        ),
        "rollback": (
            any(s.text.strip() for s in rollback),
            any(s.done_check.strip() for s in rollback),
        ),
        "approvals": (any(s.text.strip() for s in gates), any(s.done_check.strip() for s in gates)),
        "constraints": (bool(bp.constraints), any(k.result != "unknown" for k in bp.constraints)),
    }


def check_blueprint(bp: Blueprint, known: Iterable[str]) -> tuple[Issue, ...]:
    """Completeness and honesty of a blueprint. Never raises. `known` is the set of canonical
    numbers the owner's facts and the staff inputs contain; any other number in a free-text field
    is an issue. An insufficient or refused blueprint is checked for honesty only."""
    try:
        return _check(bp, frozenset(str(k) for k in known))
    except Exception as exc:  # a malformed record must report, never raise
        return (
            Issue(
                "BP-MALFORMED", "blueprint", f"could not read the blueprint: {type(exc).__name__}"
            ),
        )


def _check(bp: Blueprint, known: frozenset[str]) -> tuple[Issue, ...]:
    out: list[Issue] = []
    add = out.append
    if not isinstance(bp, Blueprint):
        return (Issue("BP-MALFORMED", "blueprint", "not a blueprint"),)
    if bp.status not in (READY, INSUFFICIENT, REFUSED):
        add(Issue("BP-STATUS", "status", "unknown status"))
    if bp.executes_nothing is not True:
        add(Issue("BP-EXEC", "executes_nothing", "a blueprint must never execute anything"))

    # honesty over every free text
    for where, text in free_texts(bp):
        if not text:
            continue
        for n in numbers_in(text):
            if n not in known:
                add(
                    Issue(
                        "BP-NUM",
                        where,
                        f"the number {n} is not in the owner's facts or staff inputs",
                    )
                )
        if has_money(text):
            add(
                Issue(
                    "BP-MONEY", where, "money in a text; only staff cost lines may carry an amount"
                )
            )
        if has_promise(text):
            add(Issue("BP-PROMISE", where, "promise or guarantee wording"))
        if has_credential(text):
            add(Issue("BP-CRED", where, "a credential or personal-number word"))
    for c in bp.costs:
        if c.amount is not None:
            if not c.source.strip() or c.source.strip().lower() == "pi":
                add(Issue("BP-COST", "cost", "an amount needs a staff source"))
            if canon_number(str(c.amount)) not in known:
                add(Issue("BP-COST", "cost", "an amount that staff did not supply"))
        elif c.status != "unknown":
            add(Issue("BP-COST", "cost", "no amount but not marked as to be quoted by staff"))
    for t in bp.timeline:
        if t.duration.strip() and not t.source.strip():
            add(
                Issue("BP-TIME", f"timeline {t.item}", "a duration needs a source (staff or owner)")
            )

    if bp.status != READY:
        if bp.status == INSUFFICIENT and not bp.missing:
            add(
                Issue("BP-MISSING", "missing", "insufficient information must list what is missing")
            )
        if bp.status == REFUSED and not bp.refusal:
            add(Issue("BP-REFUSAL", "refusal", "a refusal must name the violated constraint"))
        if bp.steps:
            add(Issue("BP-EMPTY", "steps", "a blueprint that is not ready carries no steps"))
        return tuple(out)

    # completeness of a ready blueprint
    report = section_report(bp)
    for name in SECTIONS:
        if not report[name][0]:
            add(Issue(f"BP-SEC-{name.upper()}", name, f"section {name} is missing or empty"))
    if bp.summary is not None and not set(bp.summary.problem_ids) & set(bp.problem_ids):
        add(Issue("BP-PROB", "summary", "the summary is not tied to a stated problem"))
    ids = [s.id for s in bp.steps]
    if len(set(ids)) != len(ids):
        add(Issue("BP-STEP-ID", "steps", "duplicate step id"))
    idset = set(ids)
    if len(bp.steps) > 200:
        add(Issue("BP-SIZE", "steps", "too many steps to check"))
        return tuple(out)
    for s in bp.steps:
        if s.role not in ROLES:
            add(
                Issue(
                    "BP-STEP-ROLE",
                    f"step {s.id}",
                    "a step needs an owner role (owner, staff, pi, reviewer)",
                )
            )
        if not s.done_check.strip():
            add(Issue("BP-STEP-DONE", f"step {s.id}", "a step needs a done-check"))
        if not s.text.strip():
            add(Issue("BP-STEP-TEXT", f"step {s.id}", "a step needs text"))
        if s.kind not in STEP_KINDS:
            add(Issue("BP-STEP-KIND", f"step {s.id}", "unknown step kind"))
    for e in bp.edges:
        if e.before not in idset or e.after not in idset:
            add(
                Issue(
                    "BP-DEP-MISSING",
                    f"{e.before}->{e.after}",
                    "a dependency names a step that does not exist",
                )
            )
    if _has_cycle(ids, bp.edges):
        add(Issue("BP-DEP-CYCLE", "dependencies", "the dependencies contain a cycle"))
    else:
        for s in bp.steps:
            if s.kind == "action" and not _has_gate_before(s.id, bp):
                add(
                    Issue(
                        "BP-GATE", f"step {s.id}", "an action step has no owner approval before it"
                    )
                )
    if not any(s.kind == "rollback" for s in bp.steps):
        add(Issue("BP-ROLLBACK", "rollback", "no rollback or exit step"))
    for r in bp.responsibilities:
        if r.role not in ROLES:
            add(
                Issue(
                    "BP-ROLE",
                    "responsibilities",
                    "a responsibility names something that is not a role",
                )
            )
        if any(sid not in idset for sid in r.steps):
            add(Issue("BP-RESP-STEP", r.role, "a responsibility names a step that does not exist"))
    for m in bp.milestones:
        if not m.steps or any(sid not in idset for sid in m.steps):
            add(Issue("BP-MILE", f"milestone {m.id}", "a milestone must be tied to existing steps"))
    for me in bp.success:
        if me.target.strip() and not me.target_source.strip():
            add(Issue("BP-SUCC", f"measure {me.id}", "a target needs the owner as its source"))
        if me.baseline.strip() and me.baseline_source != "owner":
            add(Issue("BP-SUCC", f"measure {me.id}", "a baseline must come from the owner"))
        if not me.baseline.strip() and (
            not me.baseline_source.strip() or me.baseline_source == "owner"
        ):
            add(
                Issue(
                    "BP-SUCC",
                    f"measure {me.id}",
                    "no baseline: it needs a step that records it first",
                )
            )
        elif not me.baseline.strip() and me.baseline_source.split(" ")[-1] not in idset:
            add(
                Issue(
                    "BP-SUCC",
                    f"measure {me.id}",
                    "the step that records the baseline does not exist",
                )
            )
    for k in bp.constraints:
        if k.result == "violates" and k.hard:
            add(
                Issue(
                    "BP-CONSTR",
                    f"constraint {k.label}",
                    "a violated hard constraint in a ready blueprint",
                )
            )
        if k.result not in ("ok", "violates", "unknown"):
            add(Issue("BP-CONSTR", f"constraint {k.label}", "unknown result value"))
        if k.result == "ok" and not k.reason.strip():
            add(Issue("BP-CONSTR", f"constraint {k.label}", "satisfied without a reason"))
    return tuple(out)


def _has_cycle(ids: list[str], edges: tuple[Any, ...]) -> bool:
    indeg = {i: 0 for i in ids}
    nxt: dict[str, list[str]] = {i: [] for i in ids}
    for e in edges:
        if e.before in indeg and e.after in indeg:
            nxt[e.before].append(e.after)
            indeg[e.after] += 1
    queue = [i for i, d in indeg.items() if d == 0]
    seen = 0
    while queue:
        cur = queue.pop()
        seen += 1
        for n in nxt[cur]:
            indeg[n] -= 1
            if indeg[n] == 0:
                queue.append(n)
    return seen != len(indeg)


def _has_gate_before(step_id: str, bp: Blueprint) -> bool:
    gates = {s.id for s in bp.steps if s.kind == "approval" and s.role == "owner"}
    prev: dict[str, list[str]] = {}
    for e in bp.edges:
        prev.setdefault(e.after, []).append(e.before)
    seen: set[str] = set()
    stack = list(prev.get(step_id, ()))
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        if cur in gates:
            return True
        stack.extend(prev.get(cur, ()))
    return False
