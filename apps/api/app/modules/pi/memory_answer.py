"""RMEM05 / RPRIV06 (platform spec v1.6): the answer to "what do you remember about me?".

The list comes from the PS-8 bundle (`context_memory.build_context`, as the compact records
`known_records` makes): every item says what it is, where it came from and its status. Rules:

* a fact the owner said or confirmed is worded as theirs ("you told me");
* a pi guess (`pi_inferred`, `derived`) or a page read is never worded as a fact: it goes in its
  own sentence, marked "not confirmed";
* no third party's name (`third_party.protect` on every text; the stored text was redacted already);
* the owner's raw messages are not repeated, only what was noted from them;
* the answer is a statement, in the owner's language, and ends with the right to delete.

Pure functions. `reply` returns the caller's fallback line when there is nothing to list.
"""

from typing import Any

from app.modules.pi import third_party

MAX_ITEMS = 10  # items listed in one WhatsApp message; the rest is counted

_OWNER = ("owner_said", "confirmed")
_GUESS = ("pi_inferred", "derived", "page_read")
_KIND_SOURCE = {
    "problem": "problem",
    "correction": "correction",
    "rejection": "said_no",
    "tried": "tried",
    "file": "file",
    "document": "solution",
    "quote": "solution",
    "box": "solution",
    "deal_document": "solution",
    "payment": "solution",
    "kickoff": "solution",
    "offer": "decision",
    "approval": "decision",
    "yes": "decision",
    "decline": "decision",
    "revision_request": "decision",
    "document_approval": "decision",
    "box_move": "decision",
    "open_item": "decision",
}

TEXT: dict[str, dict[str, str]] = {
    "en": {
        "intro": "Here is what I keep, and where each item came from:",
        "more": "and {n} more",
        "guesses": "Not confirmed, my guesses and not facts: {items}.",
        "end": "You can ask me to delete all of it.",
        "owner_said": "you told me",
        "confirmed": "you confirmed it",
        "remembered": "from an earlier chat",
        "stored": "kept on file",
        "page_read": "read from your page",
        "pi_inferred": "my guess",
        "derived": "my reading",
        "problem": "problem",
        "correction": "correction",
        "said_no": "you said no to",
        "tried": "something you tried",
        "file": "file",
        "solution": "document or quote",
        "decision": "decision",
        "fact": "detail",
        "state": "status",
    },
    "roman_ur": {
        "intro": "Mere paas ye hai, aur har cheez kahan se aayi:",
        "more": "aur {n} aur",
        "guesses": "Tasdeeq nahi hui, ye mere andaze hain, haqeeqat nahi: {items}.",
        "end": "Aap in sab ko delete karne ko keh sakte hain.",
        "owner_said": "aap ne bataya",
        "confirmed": "aap ne tasdeeq ki",
        "remembered": "pichli baat se",
        "stored": "record mein hai",
        "page_read": "aap ke page se parha",
        "pi_inferred": "mera andaza",
        "derived": "meri samajh",
        "problem": "masla",
        "correction": "durusti",
        "said_no": "aap ne mana kiya",
        "tried": "jo aap ne try kiya",
        "file": "file",
        "solution": "document ya quote",
        "decision": "faisla",
        "fact": "tafseel",
        "state": "halat",
    },
    "ur": {
        "intro": "میرے پاس یہ ہے، اور ہر چیز کہاں سے آئی:",
        "more": "اور {n} مزید",
        "guesses": "تصدیق نہیں ہوئی، یہ میرے اندازے ہیں، حقیقت نہیں: {items}۔",
        "end": "آپ مجھے یہ سب حذف کرنے کو کہہ سکتے ہیں۔",
        "owner_said": "آپ نے بتایا",
        "confirmed": "آپ نے تصدیق کی",
        "remembered": "پچھلی بات سے",
        "stored": "ریکارڈ میں ہے",
        "page_read": "آپ کے صفحے سے پڑھا",
        "pi_inferred": "میرا اندازہ",
        "derived": "میری سمجھ",
        "problem": "مسئلہ",
        "correction": "درستی",
        "said_no": "آپ نے منع کیا",
        "tried": "جو آپ نے آزمایا",
        "file": "فائل",
        "solution": "دستاویز یا کوٹیشن",
        "decision": "فیصلہ",
        "fact": "تفصیل",
        "state": "حالت",
    },
    "ar": {
        "intro": "هذا ما أحتفظ به، ومن أين جاء كل بند:",
        "more": "و{n} أخرى",
        "guesses": "غير مؤكد، هذه تخميناتي وليست حقائق: {items}.",
        "end": "يمكنك أن تطلب مني حذف كل ذلك.",
        "owner_said": "أخبرتني",
        "confirmed": "أكدت ذلك",
        "remembered": "من محادثة سابقة",
        "stored": "محفوظ في السجل",
        "page_read": "قرأته من صفحتك",
        "pi_inferred": "تخميني",
        "derived": "قراءتي",
        "problem": "مشكلة",
        "correction": "تصحيح",
        "said_no": "رفضت",
        "tried": "ما جربته",
        "file": "ملف",
        "solution": "وثيقة أو عرض سعر",
        "decision": "قرار",
        "fact": "تفصيل",
        "state": "الحالة",
    },
}


def _table(language: str | None) -> dict[str, str]:
    return TEXT.get((language or "en").split("-")[0], TEXT["en"])


def _clean(text: str) -> str:
    return " ".join(third_party.protect(str(text or "")).split())[:140]


def _status_label(record: dict[str, Any], table: dict[str, str]) -> str:
    status = str(record.get("status") or "")
    if status in table and status in (*_OWNER, "remembered", "stored", *_GUESS):
        return table[status]
    if str(record.get("kind")) in ("problem", "correction", "rejection", "tried"):
        return table["owner_said"]
    return f"{table['state']}: {status}" if status else table["stored"]


def _listing(records: list[dict[str, Any]], table: dict[str, str]) -> tuple[list[str], list[str]]:
    """(lines for what the owner said or the files show, guesses). Raw messages are skipped."""
    lines: list[str] = []
    guesses: list[str] = []
    for r in records:
        kind = str(r.get("kind") or "")
        source = str(r.get("source") or "")
        if kind == "message" or source == "messages":
            continue
        text = _clean(str(r.get("text") or ""))
        if not text:
            continue
        if str(r.get("status")) in _GUESS:
            guesses.append(text)
            continue
        label = table[_KIND_SOURCE.get(kind, "fact")]
        lines.append(f"- {text} ({label}, {_status_label(r, table)})")
    return lines, guesses


def reply(records: list[dict[str, Any]], language: str | None, fallback: str) -> str:
    """The answer from `known_records` (PS-8), or `fallback` when nothing is stored to list."""
    table = _table(language)
    lines, guesses = _listing(list(records or []), table)
    if not lines and not guesses:
        return fallback
    shown = lines[:MAX_ITEMS]
    if len(lines) > MAX_ITEMS:
        shown.append("- " + table["more"].format(n=len(lines) - MAX_ITEMS))
    parts = [table["intro"], *shown] if shown else []
    text = "\n".join(parts)
    if guesses:
        note = table["guesses"].format(items="; ".join(guesses[:3]))
        text = f"{text}\n{note}" if text else note
    return f"{text}\n{table['end']}"


def export_bundle(bundle: Any) -> dict[str, Any]:
    """The same PS-8 bundle for the customer export: profile facts, problems, constraints (budget,
    team, deadline, what cannot change), decisions, solutions and corrections. Not the messages
    (the export lists those itself). Never raises."""
    try:
        data = bundle.to_dict()
        constraints = [
            {
                "problem": p.get("number"),
                "budget": p.get("budget"),
                "staff": p.get("staff"),
                "deadline": p.get("deadline"),
                "cannot_change": p.get("cannot_change"),
                "history": p.get("constraint_history") or [],
            }
            for p in data.get("problems") or []
            if any(
                p.get(k)
                for k in ("budget", "staff", "deadline", "cannot_change", "constraint_history")
            )
        ]
        return {
            "profile": data.get("facts") or [],
            "problems": data.get("problems") or [],
            "constraints": constraints,
            "decisions": data.get("decisions") or [],
            "solutions": data.get("solutions") or [],
            "corrections": data.get("corrections") or [],
            "rejections": data.get("rejections") or [],
            "tried": data.get("tried") or [],
            "files": data.get("files") or [],
            "unavailable": data.get("unavailable") or [],
            "truncated": data.get("truncated") or [],
            "erased": bool(data.get("erased")),
        }
    except Exception:  # noqa: BLE001 - an export must not fail because the bundle could not be read
        return {"unavailable": ["unavailable: context"]}


def answer(context: dict[str, Any], language: str | None, fallback: str) -> str:
    """What the brain gate says to "what do you remember about me?": the PS-8 listing when the
    turn's context carries the bundle's records, else the profile-facts answer of `memory_block`
    (a context built without the bundle), else the fixed line."""
    from app.modules.pi import memory_block

    known = list((context.get("memory") or {}).get("known") or [])
    said = reply(known, language, fallback)
    if said != fallback:
        return said
    return memory_block.memory_reply(context.get("what_i_know") or {}, language, fallback)
