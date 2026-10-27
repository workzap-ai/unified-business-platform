# ruff: noqa: E501  (one fixed line per row reads better than wrapped text)
"""What pi says around the problem map, in the eight priority languages (pi platform spec Book 5,
4.4 and Part 6): the question that goes with a share, the reply buttons, the opening for an owner
who is back, the line that tells what changed after a dashboard edit, and the wording of the quiet
follow-up (decision 6). Only used behind `response_rules.brain.map_share`.

Every line is gender-neutral and carries at most one question, and it is the last sentence. The
wording for Hindi, French, Persian and Spanish follows the approved fixed lines; a native-speaker
review is still wanted for all of it (spec decision 10). Nothing here names an amount, a price or a
person, and nothing asks for card, password, OTP or ID numbers.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from app.modules.pi.fixed_lines import PRIORITY

BUTTON_LIMIT = 20  # WhatsApp: a reply button title is at most 20 characters
RETURN_AFTER = timedelta(days=1)  # "the owner comes back after a day or more" (4.4)

# Up to three questions, rotated by how many maps were shared before: are the links right, is
# something missing, which comes first (4.4: "one question").
QUESTIONS: dict[str, tuple[str, str, str]] = {
    "en": ("Are the links right?", "Is anything missing?", "Which one comes first?"),
    "roman_ur": (
        "Kya ye jorr sahi hain?",
        "Kya kuch chhoot raha hai?",
        "In mein se kaun sa pehle aata hai?",
    ),
    "ur": ("کیا یہ جوڑ ٹھیک ہیں؟", "کیا کچھ رہ گیا ہے؟", "ان میں سے پہلے کون سا آتا ہے؟"),
    "ar": ("هل الروابط صحيحة؟", "هل ينقص شيء؟", "أيّ منها يأتي أولاً؟"),
    "hi": ("क्या ये जोड़ सही हैं?", "क्या कुछ छूट गया है?", "इनमें से कौन सा पहले आता है?"),
    "fr": (
        "Les liens sont-ils justes ?",
        "Manque-t-il quelque chose ?",
        "Lequel passe en premier ?",
    ),
    "fa": ("آیا این پیوندها درست است؟", "آیا چیزی جا مانده است؟", "کدام یک اول می‌آید؟"),
    "es": ("¿Los vínculos son correctos?", "¿Falta algo?", "¿Cuál va primero?"),
}

# Confirm, change, add: the reply buttons (a tap comes back as a message with this text, so the
# confirm and change titles are read like any reply: see box_signals.confirms_or_changes_map).
# The confirm title names the map, so it is never read as the owner's "yes" to an offer (a map can
# be shared while an offer is open): decisions.classify must not see it as a yes, and
# `box_signals.confirms_or_changes_map` matches these titles exactly.
BUTTONS: dict[str, tuple[str, str, str]] = {
    "en": ("The map is correct", "Something's wrong", "Something's missing"),
    "roman_ur": ("Naqsha durust hai", "Kuch ghalat hai", "Kuch reh gaya"),
    "ur": ("نقشہ درست ہے", "کچھ غلط ہے", "کچھ رہ گیا"),
    "ar": ("الخريطة صحيحة", "فيه خطأ", "ينقص شيء"),
    "hi": ("नक्शा सही है", "कुछ गलत है", "कुछ छूट गया"),
    "fr": ("La carte est juste", "Il y a une erreur", "Il manque un truc"),
    "fa": ("نقشه درست است", "چیزی غلط است", "چیزی جا مانده"),
    "es": ("El mapa es correcto", "Hay un error", "Falta algo"),
}
CONFIRM_TITLES = frozenset(titles[0].casefold() for titles in BUTTONS.values())

# The owner is back (6.2): continuity, then the map from last time, then one open question.
RETURN_OPEN: dict[str, str] = {
    "en": "Good to have you back. Here is the map from last time.",
    "roman_ur": "Wapas aaye, achha laga. Pichli baar ka naqsha ye raha.",
    "ur": "دوبارہ آپ کا آنا اچھا لگا۔ پچھلی بار کا نقشہ یہ رہا۔",
    "ar": "سعدت بعودتك. هذه خريطة المرة السابقة.",
    "hi": "आपका वापस आना अच्छा लगा। पिछली बार का नक्शा ये रहा।",
    "fr": "Bon retour parmi nous. Voici la carte de la dernière fois.",
    "fa": "خوشحالم که برگشتید. این نقشه دفعه قبل است.",
    "es": "Qué bueno tenerte de vuelta. Este es el mapa de la última vez.",
}
RETURN_QUESTION: dict[str, str] = {
    "en": "Has anything changed since, or has a new problem come up?",
    "roman_ur": "Us ke baad kuch badla, ya koi naya masla aaya?",
    "ur": "اس کے بعد کچھ بدلا، یا کوئی نیا مسئلہ آیا؟",
    "ar": "هل تغيّر شيء منذ ذلك الحين، أم ظهرت مشكلة جديدة؟",
    "hi": "उसके बाद कुछ बदला, या कोई नई समस्या आई?",
    "fr": "Est-ce que quelque chose a changé depuis, ou un nouveau problème est apparu ?",
    "fa": "از آن زمان چیزی تغییر کرده، یا مشکل تازه‌ای پیش آمده؟",
    "es": "¿Algo cambió desde entonces, o surgió un problema nuevo?",
}
# Part 6.4: old nodes are not assumed to be true; the owner is asked, gently, before the question.
RETURN_STALE: dict[str, str] = {
    "en": "The ones marked from last time may have changed, so I have not assumed they are still true.",
    "roman_ur": "Jin par pichli baar ka likha hai, wo badal chuke ho sakte hain, is liye maine unhein abhi bhi sahi nahi maana.",
    "ur": "جن پر پچھلی بار کا لکھا ہے وہ بدل چکے ہو سکتے ہیں، اس لیے میں نے انہیں ابھی تک درست نہیں مانا۔",
    "ar": "المشكلات المعلَّمة بأنها من المرة السابقة قد تكون تغيّرت، لذلك لم أفترض أنها ما زالت صحيحة.",
    "hi": "जिन पर पिछली बार का लिखा है वे बदल चुके हो सकते हैं, इसलिए मैंने उन्हें अब भी सही नहीं मान लिया।",
    "fr": "Celles marquées « de la dernière fois » ont peut-être changé, je ne les ai donc pas supposées encore vraies.",
    "fa": "مواردی که «از دفعه قبل» نوشته شده ممکن است تغییر کرده باشند، پس فرض نکرده‌ام که هنوز درست‌اند.",
    "es": "Las marcadas como «de la última vez» pueden haber cambiado, así que no las he dado por ciertas todavía.",
}
DASHBOARD_LINE: dict[str, str] = {
    "en": "You can also see and change it here: {link}",
    "roman_ur": "Aap ise yahan bhi dekh aur badal sakte hain: {link}",
    "ur": "آپ اسے یہاں بھی دیکھ اور بدل سکتے ہیں: {link}",
    "ar": "يمكنك أيضاً رؤيتها وتعديلها هنا: {link}",
    "hi": "आप इसे यहाँ भी देख और बदल सकते हैं: {link}",
    "fr": "Vous pouvez aussi la voir et la modifier ici : {link}",
    "fa": "می‌توانید آن را اینجا هم ببینید و تغییر دهید: {link}",
    "es": "También puedes verlo y cambiarlo aquí: {link}",
}

# After a dashboard edit (4.9): one short line, no question. {what} is the owner's own words.
CHANGED: dict[str, str] = {
    "en": "I saw the changes you made to your map ({what}). My notes now match.",
    "roman_ur": "Aap ne naqshe mein jo badlaav kiye ({what}), maine dekh liye. Mere notes ab mel khate hain.",
    "ur": "آپ نے نقشے میں جو تبدیلیاں کیں ({what})، میں نے دیکھ لیں۔ میرے نوٹس اب ان کے مطابق ہیں۔",
    "ar": "رأيت التغييرات التي أجريتها على خريطتك ({what}). ملاحظاتي الآن مطابقة لها.",
    "hi": "आपने नक्शे में जो बदलाव किए ({what}), मैंने देख लिए। मेरे नोट्स अब उनसे मेल खाते हैं।",
    "fr": "J'ai vu les changements que vous avez faits sur votre carte ({what}). Mes notes sont à jour.",
    "fa": "تغییراتی که در نقشه‌تان دادید ({what}) را دیدم. یادداشت‌های من اکنون با آن‌ها یکی است.",
    "es": "Vi los cambios que hiciste en tu mapa ({what}). Mis notas ya coinciden.",
}

# The quiet follow-up (6.3, decision 6): value first, mentions the map, no pressure, never the box.
FOLLOWUP: dict[str, str] = {
    "en": "Your map is still ready. If a new problem has come up, tell me.",
    "roman_ur": "Aap ka naqsha abhi bhi tayyar hai. Koi naya masla aaya to bataiye.",
    "ur": "آپ کا نقشہ ابھی بھی تیار ہے۔ کوئی نیا مسئلہ آئے تو بتائیے۔",
    "ar": "خريطتك ما زالت جاهزة. إذا ظهرت مشكلة جديدة فأخبرني.",
    "hi": "आपका नक्शा अभी भी तैयार है। कोई नई समस्या आए तो बताइए।",
    "fr": "Votre carte est toujours prête. Si un nouveau problème est apparu, dites-le-moi.",
    "fa": "نقشه شما هنوز آماده است. اگر مشکل تازه‌ای پیش آمد، به من بگویید.",
    "es": "Tu mapa sigue listo. Si ha surgido un problema nuevo, cuéntamelo.",
}

# The map follow-up cadence: a small number, spaced out, then stop (6.3).
FOLLOWUP_DAYS = (3, 10)  # after the owner's last message
FOLLOWUP_LIFETIME = 4  # in all, over the life of the chat
CHANGE_DEBOUNCE = timedelta(minutes=2)  # edits in a burst become one line
CHANGE_GAP = timedelta(hours=1)  # and at most one such line an hour
MAX_CHANGE_LABELS = 3


def pick(table: dict[str, Any], language: str | None) -> Any:
    """The entry for this language, English when pi has none for it."""
    return table.get((language or "en").split("-")[0], table["en"])


def question(language: str | None, shared_before: int = 0) -> str:
    return str(pick(QUESTIONS, language)[shared_before % 3])


def buttons(language: str | None) -> list[str]:
    return list(pick(BUTTONS, language))


def changed_line(language: str | None, labels: list[str]) -> str:
    what = ", ".join(label for label in labels[:MAX_CHANGE_LABELS] if label)
    return str(pick(CHANGED, language)).format(what=what or "-")


def followup_text(language: str | None) -> str:
    return str(pick(FOLLOWUP, language))


def return_text(language: str | None, *, stale: bool, link: str = "") -> str:
    """The words that go with the picture for a returning owner: continuity, the dashboard link,
    what is old (if anything) and then the one open question as the last sentence."""
    parts = [str(pick(RETURN_OPEN, language))]
    if link:
        parts.append(str(pick(DASHBOARD_LINE, language)).format(link=link))
    if stale:
        parts.append(str(pick(RETURN_STALE, language)))
    parts.append(str(pick(RETURN_QUESTION, language)))
    return "\n".join(parts)


def dashboard_link(public_url: str | None) -> str:
    base = (public_url or "").rstrip("/")
    return f"{base}/customer" if base else ""


def is_return(previous_inbound: datetime | None, now: datetime) -> bool:
    """The owner writes after a day or more of quiet (a first message is not a return)."""
    if previous_inbound is None:
        return False
    if previous_inbound.tzinfo is None:
        previous_inbound = previous_inbound.replace(tzinfo=UTC)
    return now - previous_inbound >= RETURN_AFTER


def returning(rows: list[Any], message: Any, now: datetime | None = None) -> bool:
    """This inbound `message` comes a day or more after the owner's last one in `rows` (the
    messages before it). A first message, or a gap of under a day, is not a return."""
    stamp = getattr(message, "created_at", None) or now
    if stamp is None:
        return False
    before = [
        m.created_at
        for m in rows
        if getattr(m, "direction", "") == "inbound" and getattr(m, "created_at", None)
    ]
    return is_return(max(before) if before else None, stamp)


def note_dashboard_change(brief: dict[str, Any], label: str, now: datetime) -> dict[str, Any]:
    """The brief with this dashboard edit waiting to be told in one short line (4.9)."""
    pending = dict(brief.get("map_changes") or {})
    labels = [str(x) for x in pending.get("labels") or []]
    if label and label not in labels:
        labels.append(label)
    return {
        **brief,
        "map_changes": {"at": now.isoformat(), "labels": labels[:MAX_CHANGE_LABELS]},
    }


def titles_ok() -> bool:
    """Every language the priority list names has every line, and every button fits (a test)."""
    tables: tuple[dict[str, Any], ...] = (
        QUESTIONS,
        BUTTONS,
        RETURN_OPEN,
        RETURN_QUESTION,
        RETURN_STALE,
        DASHBOARD_LINE,
        CHANGED,
        FOLLOWUP,
    )
    return all(set(PRIORITY) <= set(t) for t in tables) and all(
        len(title) <= BUTTON_LIMIT for titles in BUTTONS.values() for title in titles
    )
