# ruff: noqa: E501
"""PS-10: the self-review gate. A deterministic solution-quality check of a structured draft.

The flow lead calls `review(draft)` after the draft and before the send. The constitution linter still
runs; this adds the solution-quality layer. Per the spec's pre-send rule (v1.6 section 18: regenerate
once with the reason, a safe fallback after a second failure, log rule_break), the caller regenerates
once with `report.reasons`, then sends `owner_safe_fallback(report, language)` and raises the alert.

Verdicts:
  COMPLETE    no critical failure and no unknown in a critical check.
  INCOMPLETE  a critical check FAILED: do not pretend the solution is complete; ask one question or
              say what is missing.
  BLOCKED     no critical failure, but a critical check is UNKNOWN. Unknown is never approved.

Critical checks: SR-01, 04, 06, 07, 09, 10, 16; SR-13 (FAIL only, an undetectable language is not a
block); SR-14 (only the invented price, promise, guarantee, saving or ROI claim).

Pure, never raises (a check that errors is reported UNKNOWN), no model, no database, no I/O.
"""

from __future__ import annotations

from app.modules.pi.self_review_checks import CHECKS, NAMES
from app.modules.pi.self_review_types import (
    BLOCKED,
    COMPLETE,
    FAIL,
    INCOMPLETE,
    LANGS,
    UNKNOWN,
    CheckResult,
    DraftResult,
    ReviewReport,
)

CRITICAL = frozenset(
    {"SR-01", "SR-04", "SR-06", "SR-07", "SR-09", "SR-10", "SR-16", "SR-13", "SR-14"}
)
UNKNOWN_BLOCKS = CRITICAL - {"SR-13", "SR-14"}
# The single most useful repair first: a lie to the owner, then the wrong language, then an unsafe or
# irrelevant option, then dropped constraints, then honesty labels, then missing understanding.
PRIORITY = ("SR-16", "SR-14", "SR-13", "SR-10", "SR-07", "SR-06", "SR-09", "SR-04", "SR-05",
            "SR-11", "SR-01", "SR-08", "SR-02", "SR-03", "SR-12", "SR-15")  # fmt: skip

REPAIRS = {
    "ask_detail": "ask the owner for the problem in their own words and the facts around it",
    "drop_question": "drop the question: the records already answer it",
    "retrieve_context": "retrieve the stored records before replying",
    "connect_problems": "state how the problems connect, or mark them unrelated",
    "label_causes": "label causes as hypotheses and word them with a hedge",
    "list_constraints": "list every stored constraint with a status; ask for the missing limit",
    "drop_option": "drop the option",
    "drop_item": "drop the item that is not tied to the problem",
    "label_unknown": "label what is unknown as 'not yet checked'; never show it as approved",
    "learn_first": "present the recommendation as a learn-first step",
    "ask_tried": "ask what the owner already tried",
    "add_deps_risks": "add dependencies and risks, or an explicit 'none known'",
    "rewrite_reply": "rewrite the reply in the owner's language and script",
    "remove_claims": "remove the invented price, promise, guarantee or saving",
    "plain_words": "use plain words",
    "one_step": "give exactly one clear next step",
    "ask_one_question": "keep one question and make it the last sentence",
    "reword_proposed": "word the solution as a proposal, not as done",
}
LANG_NAMES = {"en": "English", "roman_ur": "Roman Urdu", "ur": "Urdu script", "ar": "Arabic"}


def _safe_check(fn, check_id: str, draft: DraftResult) -> CheckResult:  # type: ignore[no-untyped-def]
    try:
        r = fn(draft)
        return (
            r
            if isinstance(r, CheckResult)
            else CheckResult(check_id, NAMES[check_id], UNKNOWN, ("bad result",))
        )
    except Exception as exc:  # a check never raises into the flow
        return CheckResult(
            check_id, NAMES[check_id], UNKNOWN, (f"check error: {type(exc).__name__}",)
        )


def _blocking_fail(c: CheckResult) -> bool:
    if c.status != FAIL or c.id not in CRITICAL:
        return False
    return c.id != "SR-14" or c.tag == "claim"


def _blocking_unknown(c: CheckResult) -> bool:
    return c.status == UNKNOWN and c.id in UNKNOWN_BLOCKS


def review(draft: DraftResult | None) -> ReviewReport:
    """Evaluate every check; return the report. Never raises."""
    d = draft if isinstance(draft, DraftResult) else DraftResult()
    checks = tuple(_safe_check(fn, cid, d) for cid, fn in CHECKS)
    fails = [c for c in checks if _blocking_fail(c)]
    unknowns = [c for c in checks if _blocking_unknown(c)]
    verdict = INCOMPLETE if fails else BLOCKED if unknowns else COMPLETE
    reasons = tuple(
        f"{c.id} {c.name}: {c.evidence[0] if c.evidence else c.status}" for c in (*fails, *unknowns)
    )
    warns = tuple(
        f"{c.id} {c.name}: {c.evidence[0] if c.evidence else c.status}"
        for c in checks
        if c.status in (FAIL, UNKNOWN) and c not in fails and c not in unknowns
    )
    pool = fails or unknowns or [c for c in checks if c.status == FAIL]
    best = min(pool, key=lambda c: PRIORITY.index(c.id)) if pool else None
    code = best.repair if best else ""
    arg = best.repair_arg if best else ""
    action = ""
    if best and code:
        action = REPAIRS.get(code, code) + (
            f" ({arg})" if arg and code in ("drop_option", "rewrite_reply") else ""
        )
        if code == "rewrite_reply" and arg in LANG_NAMES:
            action = f"rewrite the reply in {LANG_NAMES[arg]}"
    return ReviewReport(checks, verdict, reasons, (action,) if action else (), code, arg, warns)


_VERDICT_WORD = {
    "en": {COMPLETE: "complete", INCOMPLETE: "incomplete", BLOCKED: "blocked (unknown)"},
    "roman_ur": {COMPLETE: "mukammal", INCOMPLETE: "adhoora", BLOCKED: "ruka hua (maloom nahi)"},
    "ur": {COMPLETE: "مکمل", INCOMPLETE: "ادھورا", BLOCKED: "رکا ہوا (نامعلوم)"},
    "ar": {COMPLETE: "مكتمل", INCOMPLETE: "غير مكتمل", BLOCKED: "معلق (غير معروف)"},
}


def render_report(report: ReviewReport, language: str = "en") -> str:
    """One internal log text (not owner-facing)."""
    lang = language if language in LANGS else "en"
    lines = [
        f"self_review: {_VERDICT_WORD[lang].get(report.verdict, report.verdict)} [{report.verdict}]"
    ]
    for c in report.checks:
        ev = f" - {c.evidence[0]}" if c.evidence else ""
        lines.append(f"{c.id} {c.status} {c.name}{ev}")
    lines.extend(f"reason: {r}" for r in report.reasons)
    lines.extend(f"next: {a}" for a in report.next_actions)
    return "\n".join(lines)


# Fixed owner-facing lines. Each has exactly one question and it is the last sentence; none promises,
# prices, or says anything is done; none contains a digit. British spelling.
_FALLBACKS: dict[str, dict[str, str]] = {
    "detail": {
        "en": "I want to be sure I have understood you properly before I suggest anything. "
        "What is the main problem you most want fixed first?",
        "roman_ur": "Kuch bhi suggest karne se pehle main yeh theek se samajhna chahta hoon. "
        "Aap sab se pehle kaun sa masla theek karwana chahte hain?",
        "ur": "کوئی بھی تجویز دینے سے پہلے میں آپ کی بات ٹھیک سے سمجھنا چاہتا ہوں۔ "
        "آپ سب سے پہلے کون سا مسئلہ حل کروانا چاہتے ہیں؟",
        "ar": "قبل أن أقترح أي شيء أريد أن أتأكد أنني فهمتك جيدا. "
        "ما هي المشكلة الأهم التي تريد حلها أولا؟",
    },
    "constraints": {
        "en": "Before I suggest a plan, I need to know what limits we must work within. "
        "What is your budget, staff or time limit for this?",
        "roman_ur": "Plan batane se pehle mujhe woh hadood janni hain jin mein rehna hai. "
        "Is kaam ke liye aap ka budget, staff ya waqt ki kya hadd hai?",
        "ur": "منصوبہ بتانے سے پہلے مجھے وہ حدود جاننی ہیں جن میں رہنا ہے۔ "
        "اس کام کے لیے آپ کا بجٹ، عملہ یا وقت کی کیا حد ہے؟",
        "ar": "قبل أن أقترح خطة أحتاج أن أعرف الحدود التي يجب أن نعمل ضمنها. "
        "ما هي حدود الميزانية أو الموظفين أو الوقت لديك؟",
    },
    "options": {
        "en": "The ideas I have so far do not fit your situation well enough yet. "
        "What have you already tried that did not work?",
        "roman_ur": "Mere paas abhi jo khayalat hain woh aap ki surat-e-haal se poori tarah nahi milte. "
        "Aap ne pehle kya try kiya jo kaam nahi aaya?",
        "ur": "میرے پاس ابھی جو خیالات ہیں وہ آپ کی صورتحال سے پوری طرح نہیں ملتے۔ "
        "آپ نے پہلے کیا آزمایا جو کام نہیں آیا؟",
        "ar": "الأفكار التي لدي حتى الآن لا تناسب وضعك بما يكفي. ما الذي جربته من قبل ولم ينجح؟",
    },
    "proposal": {
        "en": "This is only a suggestion so far, and I have not started anything. "
        "Which part would you like to go through first?",
        "roman_ur": "Yeh abhi sirf ek tajweez hai, aur kuch bhi shuru nahi hua. "
        "Aap pehle kaun sa hissa dekhna chahenge?",
        "ur": "یہ ابھی صرف ایک تجویز ہے، اور کچھ بھی شروع نہیں ہوا۔ "
        "آپ پہلے کون سا حصہ دیکھنا چاہیں گے؟",
        "ar": "هذا مجرد اقتراح حتى الآن ولم نبدأ أي شيء. أي جزء تود أن نراجعه أولا؟",
    },
    "blueprint": {
        "en": "Before I call this a plan, I still need to list what it depends on and what could go wrong. "
        "Is there anything that could block this for you, such as time or people?",
        "roman_ur": "Isay plan kehne se pehle mujhe yeh likhna hai ke yeh kis par munhasir hai aur kya ghalat ho sakta hai. "
        "Kya koi cheez isay rok sakti hai, jaise waqt ya log?",
        "ur": "اسے منصوبہ کہنے سے پہلے مجھے لکھنا ہے کہ یہ کس پر منحصر ہے اور کیا غلط ہو سکتا ہے۔ "
        "کیا کوئی چیز اسے روک سکتی ہے، جیسے وقت یا لوگ؟",
        "ar": "قبل أن أسميه خطة أحتاج أن أحدد ما يعتمد عليه وما قد يسوء. "
        "هل هناك ما قد يعيق ذلك لديك، مثل الوقت أو الأشخاص؟",
    },
}
_GROUP = {
    "ask_detail": "detail", "drop_question": "detail", "retrieve_context": "detail",
    "connect_problems": "detail", "label_causes": "detail", "ask_one_question": "detail",
    "rewrite_reply": "detail", "plain_words": "detail", "one_step": "detail",
    "list_constraints": "constraints", "label_unknown": "constraints", "learn_first": "constraints",
    "drop_option": "options", "drop_item": "options", "ask_tried": "options",
    "remove_claims": "proposal", "reword_proposed": "proposal",
    "add_deps_risks": "blueprint",
}  # fmt: skip


def fallback_templates() -> dict[str, dict[str, str]]:
    """The fixed fallback lines, for the linter tests."""
    return {k: dict(v) for k, v in _FALLBACKS.items()}


def owner_safe_fallback(report: ReviewReport, language: str = "en") -> str:
    """A short owner-language line (what is missing plus one question) for a verdict that is not
    COMPLETE. Empty when the verdict is COMPLETE: the caller sends the draft."""
    if report.verdict == COMPLETE:
        return ""
    lang = language if language in LANGS else "en"
    group = _GROUP.get(report.repair_code, "constraints" if report.verdict == BLOCKED else "detail")
    return _FALLBACKS[group][lang]
