# ruff: noqa: E501  (one fixed line per row reads better than wrapped text)
"""PS-flow group A: what the owner sees in the chat about the options (brain mode only).

`voice` reads the ideas a reply lists (bullets), runs the L2-1 gate over them against what the owner
stated, and returns the reply with the rejected ideas removed and the unchecked ones labelled, plus:

  * a short block of fixed statements (which idea to start with and why, which one was left out and
    the owner's own words that ruled it out, what is not yet checked), put in front of the reply;
  * one targeted question, last, when the owner has to settle something (nothing was accepted, or
    the unknowns share one blocking limit) and the reply does not already ask one.

Pure and deterministic. The statements are FIXED templates in English, Roman Urdu, Urdu and Arabic
(British spelling in English; no price, no promise, no "will"; nothing that claims a result). The
owner's own words are quoted as they were stored. Another language gets the English templates and
the reply composer's language step is not asked to translate them: the block is put in after that
step, like the cost line, and the reply linter still runs over the final text.
"""

import re
from collections import Counter
from dataclasses import dataclass

from app.modules.pi import constraint_check as cc
from app.modules.pi import option_gate
from app.modules.pi.requirements_types import Requirements

BULLET = re.compile(r"^\s*(?:[•*-]|\d{1,2}[.)])\s+(.*)$")
QUESTION = re.compile(r"[?؟]")

T: dict[str, dict[str, str]] = {
    "en": {
        "label": "(not yet checked against what you told me)",
        "left_out": 'I left out one idea, because you said: "{words}".',
        "start": "I would start with the first idea below: it does not break anything you told me.",
        "unknown": "The ideas marked as not yet checked are not yet compared with everything you told me.",
        "q_budget": "What is the most you can spend on this, in one figure?",
        "q_cannot_change": "Which part of how you work could you change?",
        "q_tried_failed": "What did you try before, and what happened?",
        "q_deadline": "By when do you need this to start working?",
        "q_default": "What would a workable fix look like for you?",
    },
    "roman_ur": {
        "label": "(abhi aap ki baton se check nahi hua)",
        "left_out": 'Maine ek idea chhor diya, kyunki aap ne kaha: "{words}".',
        "start": "Neeche pehle idea se shuru karna theek rahega: ismein aap ki batayi hui koi baat nahi tootti.",
        "unknown": "Jin ideas par abhi check nahi hua likha hai, unhein aap ki saari baton se abhi nahi milaya gaya.",
        "q_budget": "Is par aap zyada se zyada kitna kharch kar sakte hain, ek raqam mein?",
        "q_cannot_change": "Aap apne kaam ka kaun sa hissa badal sakte hain?",
        "q_tried_failed": "Pehle aap ne kya try kiya, aur kya hua?",
        "q_deadline": "Aap ko yeh kab tak chalna chahiye?",
        "q_default": "Aap ke liye kaam karne wala hal kaisa hoga?",
    },
    "ur": {
        "label": "(ابھی آپ کی باتوں سے جانچ نہیں ہوئی)",
        "left_out": 'میں نے ایک خیال چھوڑ دیا، کیونکہ آپ نے کہا: "{words}"۔',
        "start": "نیچے پہلے خیال سے آغاز بہتر رہے گا: اس سے آپ کی بتائی ہوئی کوئی بات نہیں ٹوٹتی۔",
        "unknown": "جن خیالات پر ابھی جانچ نہیں ہوئی لکھا ہے، انہیں آپ کی تمام باتوں کے ساتھ ابھی نہیں ملایا گیا۔",
        "q_budget": "اس پر آپ زیادہ سے زیادہ کتنا خرچ کر سکتے ہیں، ایک رقم میں؟",
        "q_cannot_change": "آپ اپنے کام کا کون سا حصہ بدل سکتے ہیں؟",
        "q_tried_failed": "پہلے آپ نے کیا آزمایا، اور کیا ہوا؟",
        "q_deadline": "آپ کو یہ کب تک چلنا چاہیے؟",
        "q_default": "آپ کے لیے کارآمد حل کیسا ہوگا؟",
    },
    "ar": {
        "label": "(لم يُفحص بعد مع ما قلته)",
        "left_out": 'تركت فكرة واحدة لأنك قلت: "{words}".',
        "start": "الأفضل البدء بالفكرة الأولى أدناه: فهي لا تخالف شيئاً ذكرته.",
        "unknown": "الأفكار المكتوب عليها لم يُفحص بعد لم تُقارن بعد بكل ما قلته.",
        "q_budget": "ما أكثر مبلغ يمكنك إنفاقه على هذا، برقم واحد؟",
        "q_cannot_change": "ما الجزء من طريقة عملك الذي يمكنك تغييره؟",
        "q_tried_failed": "ماذا جرّبت من قبل، وماذا حدث؟",
        "q_deadline": "متى تحتاج أن يبدأ هذا بالعمل؟",
        "q_default": "كيف سيبدو الحل المناسب لك؟",
    },
}
BLOCKING = {
    cc.RULE_BUDGET: "q_budget",
    cc.RULE_CANNOT_CHANGE: "q_cannot_change",
    cc.RULE_TRIED: "q_tried_failed",
    cc.RULE_DEADLINE: "q_deadline",
}


def table(language: str | None) -> dict[str, str]:
    return T.get(language or "en") or T["en"]


@dataclass
class Voiced:
    reply: str  # the reply with rejected ideas removed and unchecked ones labelled
    block: str = ""  # fixed statements, put in front of the reply after the language step
    question: str = ""  # the one targeted question, put last ("" when none is needed)
    changed: bool = False
    unmarked: tuple[int, ...] = ()  # positions (among the listed ideas) of the not yet checked ones
    rejected: int = 0
    unknown: int = 0
    accepted: int = 0


def _limit_text(reqs: Requirements, verdict: cc.Verdict) -> str:
    """The owner's own words for the limit that ruled an idea out: the stated limit that shares a
    word with the evidence, else the first limit of that kind, else the matched words."""
    texts = {
        cc.RULE_CANNOT_CHANGE: [x.text for x in reqs.cannot_change],
        cc.RULE_TRIED: [t.what for t in reqs.tried],
        cc.RULE_BUDGET: [x.text for x in reqs.budgets],
        cc.RULE_DEADLINE: [x.text for x in reqs.deadlines],
    }
    pool = texts.get(verdict.rule) or [t for ts in texts.values() for t in ts]
    words = {w.casefold() for w in verdict.evidence if w}
    for text in pool:
        if words & {w.casefold() for w in re.findall(r"\w+", text)}:
            return text
    return pool[0] if pool else ", ".join(verdict.evidence)


def _bullets(lines: list[str]) -> list[tuple[int, str]]:
    return [(i, m.group(1)) for i, line in enumerate(lines) if (m := BULLET.match(line))]


def label_ideas(reply: str, positions: tuple[int, ...], language: str | None) -> str:
    """The not yet checked label after the listed ideas at these positions, in the reply's language."""
    if not positions:
        return reply
    label = table(language)["label"]
    out: list[str] = []
    n = -1
    for line in (reply or "").splitlines():
        if BULLET.match(line):
            n += 1
            if n in positions:
                line = f"{line.rstrip()} {label}"
        out.append(line)
    return chr(10).join(out)


def voice(reply: str, reqs: Requirements, language: str | None) -> Voiced:
    """See the module docstring."""
    lines = (reply or "").splitlines()
    found = _bullets(lines)
    if not found or (reqs.empty and reqs.columns_available):
        return Voiced(reply)
    result = option_gate.gate_options([t.rstrip(". ") for _, t in found], reqs, language)
    verdict_of = {
        g.option: g.verdict for g in (*result.accepted, *result.rejected, *result.unknown)
    }
    tb = table(language)
    keep: list[str] = []
    drop = {i for i, t in found if verdict_of[t.rstrip(". ")].status == "violates"}
    unknown_at = {i for i, t in found if verdict_of[t.rstrip(". ")].status == "unknown"}
    for i, line in enumerate(lines):
        if i in drop:
            continue
        keep.append(line)
    # positions among the ideas that stay (the label is put in after the language step, in the
    # reply's own language, so a translation of the reply never garbles it)
    kept_ids = [i for i, _ in found if i not in drop]
    unmarked = tuple(n for n, i in enumerate(kept_ids) if i in unknown_at)
    remaining_bullets = [x for x in _bullets(keep)]
    if not remaining_bullets:  # no idea left: the opener line that introduced them goes too
        while keep and (not keep[-1].strip() or keep[-1].rstrip().endswith((":", "："))):
            keep.pop()
    block: list[str] = []
    if result.rejected:
        first = result.rejected[0].verdict
        block.append(tb["left_out"].format(words=_limit_text(reqs, first)))
    if result.accepted and any(g.verdict.rule != cc.RULE_NONE for g in result.accepted):
        block.append(tb["start"])
    if result.unknown:
        block.append(tb["unknown"])
    new_reply = "\n".join(keep).strip()
    question = ""
    if not QUESTION.search(new_reply):
        if not result.accepted and result.rejected and result.ask_about:
            question = tb[BLOCKING.get(result.ask_about, "q_default")]
        elif not result.accepted and result.unknown:
            rule = Counter(g.verdict.rule for g in result.unknown if g.verdict.rule in BLOCKING)
            question = tb[BLOCKING[rule.most_common(1)[0][0]]] if rule else ""
    changed = bool(block or question or drop or unmarked)
    return Voiced(
        new_reply,
        "\n".join(block),
        question,
        changed,
        unmarked,
        len(result.rejected),
        len(result.unknown),
        len(result.accepted),
    )
