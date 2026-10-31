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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.modules.pi import constraint_check as cc
from app.modules.pi import idea_relevance, option_gate
from app.modules.pi.requirements_types import Requirements

BULLET = re.compile(r"^\s*(?:[•*-]|\d{1,2}[.)])\s+(.*)$")
QUESTION = re.compile(r"[?؟]")

T: dict[str, dict[str, str]] = {
    "en": {
        "label": "(not yet checked against what you told me)",
        "off_topic": "I left out one idea that does not address what you told me.",
        "generic": "I left out one idea that would fit any business.",
        "repeat": 'I left out one idea, because you already tried: "{words}".',
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
        "off_topic": "Maine ek idea chhor diya jo aap ki batayi hui baat se nahi judta.",
        "generic": "Maine ek idea chhor diya jo har karobar par lagu ho jata hai.",
        "repeat": 'Maine ek idea chhor diya, kyunki aap pehle hi aazma chuke hain: "{words}".',
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
        "off_topic": "میں نے ایک خیال چھوڑ دیا جو آپ کی بتائی ہوئی بات سے نہیں جڑتا۔",
        "generic": "میں نے ایک خیال چھوڑ دیا جو ہر کاروبار پر لگ جاتا ہے۔",
        "repeat": 'میں نے ایک خیال چھوڑ دیا، کیونکہ آپ پہلے ہی آزما چکے ہیں: "{words}"۔',
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
        "off_topic": "تركت فكرة لا تتعلق بما ذكرته.",
        "generic": "تركت فكرة عامة تناسب أي عمل.",
        "repeat": 'تركت فكرة لأنك جرّبتها من قبل: "{words}".',
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


def _limit_text(reqs: Requirements, rule: str, evidence: tuple[str, ...]) -> str:
    """The owner's own words for the limit that ruled an idea out: the stated limit that shares a
    word with the evidence, else the first limit of that kind, else the matched words."""
    texts = {
        cc.RULE_CANNOT_CHANGE: [x.text for x in reqs.cannot_change],
        cc.RULE_TRIED: [t.what for t in reqs.tried],
        cc.RULE_BUDGET: [x.text for x in reqs.budgets],
        cc.RULE_DEADLINE: [x.text for x in reqs.deadlines],
    }
    pool = texts.get(rule) or [t for ts in texts.values() for t in ts]
    words = {w.casefold() for w in evidence if w}
    for text in pool:
        if words & {w.casefold() for w in re.findall(r"\w+", text)}:
            return text
    return pool[0] if pool else ", ".join(evidence)


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


K = idea_relevance.IdeaKind
DROPPED = (K.VIOLATES_CONSTRAINT, K.UNLINKED, K.GENERIC, K.REPEATS_TRIED)


def _records(problems: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The noted problems as `evaluate_idea` reads them (the book's `group` is its category)."""
    return [{**p, "category": p.get("category") or p.get("group", "")} for p in problems]


def voice(
    reply: str,
    reqs: Requirements,
    language: str | None,
    problems: Sequence[Mapping[str, Any]] = (),
) -> Voiced:
    """See the module docstring. Every listed idea gets PS-3's verdict (`evaluate_idea`) with the
    L2-1 gate plugged in (`gate_from_option_gate`), so one verdict path decides:

      LINKED and the gate said ok       the idea stays;
      LINKED and the gate cannot tell,
      or UNKNOWN                        the idea stays, labelled "not yet checked", never as linked;
      VIOLATES_CONSTRAINT               removed, the owner's own words for the limit are quoted;
      UNLINKED / GENERIC / REPEATS_TRIED removed, with one plain statement each.
    """
    lines = (reply or "").splitlines()
    found = _bullets(lines)
    if not found:
        return Voiced(reply)
    tb = table(language)
    gate = idea_relevance.gate_from_option_gate(option_gate.gate_options, lambda c: c)
    records = _records(problems)
    tried = [t.what for t in reqs.tried]
    verdicts: dict[int, idea_relevance.IdeaVerdict] = {}
    for i, text in found:
        verdicts[i] = idea_relevance.evaluate_idea(
            text.rstrip(". "),
            records,
            constraints=reqs,
            tried=tried,
            language=language,
            constraint_gate=gate,
        )
    drop = {i for i, v in verdicts.items() if v.kind in DROPPED}
    kept_ids = [i for i, _ in found if i not in drop]
    unknown_at = {
        i
        for i in kept_ids
        if verdicts[i].kind is K.UNKNOWN or verdicts[i].constraint_status != "ok"
    }
    # positions among the ideas that stay (the label is put in after the language step, in the
    # reply's own language, so a translation of the reply never garbles it)
    unmarked = tuple(n for n, i in enumerate(kept_ids) if i in unknown_at)
    keep = [line for i, line in enumerate(lines) if i not in drop]
    if not _bullets(keep):  # no idea left: the opener line that introduced them goes too
        while keep and (not keep[-1].strip() or keep[-1].rstrip().endswith((":", "："))):
            keep.pop()
    block: list[str] = []
    violated = [v for i, v in verdicts.items() if v.kind is K.VIOLATES_CONSTRAINT]
    if violated:
        rule = violated[0].reason.partition(":")[2]
        words = _limit_text(reqs, rule, violated[0].evidence_words)
        block.append(tb["left_out"].format(words=words))
    if any(v.kind is K.REPEATS_TRIED for v in verdicts.values()) and tried:
        again = next(v for v in verdicts.values() if v.kind is K.REPEATS_TRIED)
        words = _limit_text(reqs, cc.RULE_TRIED, again.evidence_words)
        block.append(tb["repeat"].format(words=words))
    if any(v.kind is K.UNLINKED for v in verdicts.values()):
        block.append(tb["off_topic"])
    if any(v.kind is K.GENERIC for v in verdicts.values()):
        block.append(tb["generic"])
    sure = [
        i
        for i in kept_ids
        if i not in unknown_at and verdicts[i].constraint_status == "ok" and not reqs.empty
    ]
    if sure:
        block.append(tb["start"])
    if unknown_at:
        block.append(tb["unknown"])
    new_reply = chr(10).join(keep).strip()
    question = ""
    if not QUESTION.search(new_reply):
        if not kept_ids:
            rules = Counter(
                v.reason.partition(":")[2]
                for v in violated
                if v.reason.partition(":")[2] in BLOCKING
            )
            key = BLOCKING[rules.most_common(1)[0][0]] if rules else "q_default"
            question = tb[key]
        elif not sure:
            texts = [t.rstrip(". ") for i, t in found if i in unknown_at]
            held = option_gate.gate_options(texts, reqs, language).unknown
            rules = Counter(g.verdict.rule for g in held if g.verdict.rule in BLOCKING)
            question = tb[BLOCKING[rules.most_common(1)[0][0]]] if rules else ""
    changed = bool(block or question or drop or unmarked)
    return Voiced(
        new_reply,
        chr(10).join(block),
        question,
        changed,
        unmarked,
        len(violated) + sum(v.kind in DROPPED[1:] for v in verdicts.values()),
        len(unknown_at),
        len(sure),
    )
