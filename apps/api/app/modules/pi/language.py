"""Which language a customer wrote in, decided by code, not the model.

pi must answer in the language of the customer's latest words. Models drift toward the
conversation's earlier language, so the system detects it here and the reply is checked
against it. Only clear signals count; anything unclear returns None and the caller falls
back to the conversation's last known language.
"""

import re
from typing import Any

# Urdu/Hindi written in English letters. Words that are not also common English words.
ROMAN_URDU = frozenset(
    """
    aap ap apka apki apke aapka aapki aapke hum ham hamara hamari hamare mera meri mere
    mujhe mujhy mjhe muje humein hamein tum tumhara tera unka unki uska uski iska iski
    hai hain hy hn hoon hun tha thi thay thy hoga hogi hogya hogaya ho gya
    kya kia kyun kyu kiyun kaise kese kaisay kab kahan kidhar kitna kitni kitne kon kaun
    nahi nahin nai nhi nh na ji jee haan han bilkul acha accha achha theek thik
    chahiye chahye chaiye chahiyay chahte chahta chahti chahta
    karna krna karo kro kar kr karen kren karein kiya kia krdo kardo karwana krwana
    raha rahi rahe rha rhi rhy rahy gaya gayi gya gyi
    bata batao btao bataen batayen batain bataye btaen
    sakte sakta sakti skte skta sakhte
    ka ki ke ko se mein mai ma bhi bh ye yeh wo woh wahan yahan aur ya lekin magar
    abhi jaldi phir dobara sirf bas kuch kch koi sab sath saath liye liye kyunke
    salam salaam assalam assalamualaikum walaikum shukriya shukria meherbani mehrbani
    bhai bhae behan sahab sahib janab
    dekh dekho dekhna dena dedo de lena lelo milega milegi chalega
    batayein samajh samjha samjhi pata maloom
    """.split()
)

# Common English words that Roman Urdu never uses on its own.
ENGLISH = frozenset(
    """
    the a an you your yours can could would should will what when where why how which who
    is are was were am be been have has had do does did don't i'm it's i've i'll
    i we they he she it this that these those my our their his her its
    want need like know tell help make get give send show please thanks thank hello
    that's what's it's all everything nothing else sorry okay
    of and for with from about into on at by or but not no yes
    there here some any more much many also just only very really
    """.split()
)
# Words both sides use all the time ("me", "to", "is", "main", "hi", "do") and nouns
# Roman Urdu borrows ("website", "design", "price") never count.
# English words Roman Urdu speakers also answer with on their own: a bare "no" or "yes"
# is no sign of English, so the chat keeps its language.
BORROWED_ANSWERS = frozenset("no yes please thanks thank sorry okay".split())

URDU_LETTERS = re.compile(r"[ٹڈڑںےھہۓ]")
PERSIAN_LETTERS = re.compile(r"[پچگژک]")
ARABIC_SCRIPT = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
LATIN_WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")

NAMES = {
    "en": "English",
    "roman_ur": "Roman Urdu (Urdu/Hindi written in English letters)",
    "ar": "Arabic",
}


def english_greeting(text: str | None) -> bool:
    """A standalone English greeting, never the Urdu particle 'hi' inside a sentence."""
    return bool(
        re.fullmatch(
            r"[\W_]*(?:(?:hi|hello|hey)(?:\s+there)?|good\s+(?:morning|afternoon|evening))"
            r"[\W_]*",
            text or "",
            re.IGNORECASE,
        )
    )


SALAM = re.compile(
    r"^[\W_]*(?:assalam+(?:u|o|\s*o)?\s*(?:a|u)?(?:laikum|alaikum|alekum|alaykum)|salam+(?:\s+(?:bhai|sir|ji))?"
    r"|السلام عليكم|سلام|اسلام علیکم|السلام علیکم)[\W_]*$",
    re.IGNORECASE,
)
FESTIVAL_WISH = re.compile(
    r"^[\W_]*(?:(?:eid|ramadan|ramzan|ramazan)\s+(?:mubarak|kareem)|(?:happy|blessed)\s+(?:eid|ramadan)"
    r"|عيد مبارك|رمضان كريم|رمضان مبارك|عید مبارک)[\W_]*$",
    re.IGNORECASE,
)


def salam(text: str | None) -> bool:
    """A bare "Assalam o alaikum" (R-LANG-08): pi answers "Wa alaikum assalam"."""
    return bool(SALAM.fullmatch((text or "").strip()))


def festival_wish(text: str | None) -> bool:
    """A bare Eid or Ramadan greeting (R-LANG-08): pi answers it in one line."""
    return bool(FESTIVAL_WISH.fullmatch((text or "").strip()))


AMOUNT = re.compile(
    r"(?P<n>\d+(?:[.,]\d+)?)\s*(?P<unit>crore|karor|lakh|lac|lakhs|hazar|hazaar|thousand|k|million|m)?\b",
    re.IGNORECASE,
)
UNITS = {
    "crore": 10_000_000,
    "karor": 10_000_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "hazar": 1_000,
    "hazaar": 1_000,
    "thousand": 1_000,
    "k": 1_000,
    "million": 1_000_000,
    "m": 1_000_000,
}


def amount_value(text: str | None) -> int | None:
    """The number in "5 lakh" (500,000), "2 crore" (20,000,000), "50 hazar", "3.5k" or "1,200", or
    None when there is no number (R-LANG-04). The person's own words are kept next to it."""
    found = AMOUNT.search(text or "")
    if found is None:
        return None
    raw = found.group("n")
    number = float(raw.replace(",", ""))  # a comma is a thousands separator
    unit = (found.group("unit") or "").lower()
    value = number * UNITS.get(unit, 1)
    return int(round(value)) if value >= 1 else None


RELATIVE_DAYS = {
    # word: (days from today, sure?) - "kal" is yesterday or tomorrow, "parson" the day before
    # yesterday or after tomorrow (R-LANG-06): ask only when it matters, never guess aloud.
    "aaj": (0, True),
    "today": (0, True),
    "yesterday": (-1, True),
    "tomorrow": (1, True),
    "kal": (1, False),
    "parson": (2, False),
    "parsoon": (2, False),
}


def date_estimate(text: str | None, today: Any) -> dict[str, Any]:
    """The stated words plus a best-effort ISO date and how sure it is (R-LANG-06). Religious
    seasons ("Ramzan", "Eid ke baad", Muharram) have no fixed day: no date, low confidence."""
    from datetime import timedelta

    said = " ".join((text or "").lower().split())
    found = next((w for w in RELATIVE_DAYS if re.search(rf"\b{w}\b", said)), None)
    if found is not None:
        days, sure = RELATIVE_DAYS[found]
        return {
            "text": said[:120],
            "date": (today + timedelta(days=days)).isoformat(),
            "confidence": "high" if sure else "low",
            "ambiguous": not sure,
        }
    season = re.search(r"\b(?:ramzan|ramadan|muharram|eid|shab[- ]e[- ]barat|rabi)\b", said)
    return {"text": said[:120], "date": None, "confidence": "low", "season": bool(season)}


def returning_greeting(text: str | None) -> bool:
    """ "hi again", "hello again": a greeting from someone who has been here before (brain mode)."""
    return bool(re.fullmatch(r"[\W_]*(?:hi|hello|hey)\s+again[\W_]*", text or "", re.IGNORECASE))


def detect_language(text: str | None) -> str | None:
    """'en', 'roman_ur' or 'ar' when the text clearly shows one, otherwise None.
    Urdu or Hindi written in its own script is 'roman_ur': pi answers those in Roman
    Urdu/Hindi (see the service prompt)."""
    text = (text or "").strip()
    if not text:
        return None
    if english_greeting(text):
        return "en"
    arabic = len(ARABIC_SCRIPT.findall(text))
    devanagari = len(DEVANAGARI.findall(text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if devanagari > latin and devanagari >= arabic:
        return "roman_ur"
    if arabic > latin:
        if URDU_LETTERS.search(text):
            return "roman_ur"
        return None if PERSIAN_LETTERS.search(text) else "ar"
    words = LATIN_WORD.findall(text.lower())
    if len(words) <= 2 and set(words) <= BORROWED_ANSWERS:
        return None  # "no", "yes please", "thanks": the chat keeps its language
    urdu = sum(word in ROMAN_URDU for word in words)
    english = sum(word in ENGLISH for word in words)
    if urdu > english:
        return "roman_ur"
    if english > urdu:
        return "en"
    # As much English as Urdu ("bas yehi, that's all"): English, the main language.
    return ("en" if english else "roman_ur") if urdu else None


def clearly_other(reply: str, expected: str) -> str | None:
    """The language a drafted reply is clearly written in when it isn't the expected one.
    Strict on purpose: a reply needs a clear majority (two marker words more) to count as
    the wrong language, so names and product words in English never trigger a rewrite."""
    if expected not in ("en", "roman_ur"):
        return None
    words = LATIN_WORD.findall((reply or "").lower())
    urdu = sum(word in ROMAN_URDU for word in words)
    english = sum(word in ENGLISH for word in words)
    if expected == "en" and urdu >= english + 2:
        return "roman_ur"
    if expected == "roman_ur" and english >= urdu + 2 and urdu <= 1:
        return "en"
    return None


HANDOFF_NOTICES = {
    "en": "Thanks for your message. A member of our team will reply here shortly.",
    "roman_ur": "Aap ke message ka shukriya. Hamari team jald hi yahan aap ko jawab degi.",
    "ar": "شكرًا لرسالتك. سيرد عليك أحد أعضاء فريقنا هنا قريبًا.",
}
# Brain mode, spec 2.4: no "shortly" and no promised time unless a real SLA exists.
BRAIN_HANDOFF_NOTICES = {
    "en": "Thanks for your message. A member of the Workzap team will reply here.",
    "roman_ur": "Aap ke message ka shukriya. Workzap ki team ka koi member yahin jawab dega.",
    "ar": "شكرًا لرسالتك. سيرد عليك أحد أعضاء فريق Workzap هنا.",
}
BRAIN_TEAM_CHECK_NOTICES = {
    "en": "Noted. I'm checking this with the Workzap team, and they'll confirm here.",
    "roman_ur": "Noted. Ise Workzap ki team se check kiya ja raha hai, wo yahin tasdeeq karein ge.",
    "ar": "تم. أتحقق من ذلك مع فريق Workzap وسيؤكدون لك هنا.",
}
MEDIA_NOTICES = {
    "en": "Thanks for the attachment. A member of our team will review it and reply here.",
    "roman_ur": "Attachment bhejne ka shukriya. Hamari team ise dekh kar yahan jawab degi.",
    "ar": "شكرًا على المرفق. سيراجعه أحد أعضاء فريقنا ويرد عليك هنا.",
}
# pi keeps the chat while the team checks something (no handoff).
TEAM_CHECK_NOTICES = {
    "en": "Noted. I'm checking this with the team and will confirm here shortly.",
    "roman_ur": "Noted. Team se confirm karke yahin jaldi update milega.",
    "ar": "تم. سأتحقق من ذلك مع الفريق وأؤكد لك هنا قريبًا.",
}
# Brain mode, spec 6.11: when the model or a tool fails, say exactly that (no promise of a time).
TECH_DOWN_NOTICES = {
    "en": "pi is having trouble right now. Your messages are saved, "
    "and pi will reply as soon as it can.",
    "roman_ur": "pi mein abhi masla hai. Aap ke paigham mehfooz hain, "
    "aur pi jaise hi ho sake jawab dega.",
    "ar": "pi يواجه مشكلة الآن. رسائلك محفوظة وسيرد pi حالما يستطيع.",
}
TOOL_FAIL_NOTICES = {
    "en": "I couldn't save that just now. Could you send it again in a moment?",
    "roman_ur": "Main abhi ise save nahi kar saka. Kya aap thori der baad dobara bhej sakte hain?",
    "ar": "لم أتمكن من حفظ ذلك الآن. هل يمكنك إرساله مرة أخرى بعد قليل؟",
}
# Brain mode, spec 6.10: a video pi cannot process.
VIDEO_UNREADABLE_NOTICES = {
    "en": "I can't watch videos here. Could you tell me in a line what it shows?",
    "roman_ur": "Main yahan videos nahi dekh sakta. "
    "Kya aap ek line mein bata sakte hain ke is mein kya hai?",
    "ar": "لا أستطيع مشاهدة الفيديو هنا. هل يمكنك أن تخبرني بسطر واحد عمّا يظهر فيه؟",
}
# Brain mode, R-LANG-07: a voice note pi could not make out.
VOICE_UNREADABLE_NOTICES = {
    "en": "I couldn't make out all of that voice note. Could you type the main problem in a line?",
    "roman_ur": "Mujhe is voice note ki poori baat samajh nahi aayi. "
    "Kya aap mukhya masla ek line mein likh sakte hain?",
    "ar": "لم أتمكن من فهم الرسالة الصوتية كاملة. هل يمكنك كتابة المشكلة الرئيسية في سطر واحد؟",
}
# A file pi couldn't open: ask for another way, keep the chat.
MEDIA_UNREADABLE_NOTICES = {
    "en": "Thanks. I couldn't open that file here, and I've passed it to the team. "
    "Could you describe it in a few words, or send it as a PDF or a screenshot?",
    "roman_ur": "Shukriya. Yeh file yahan open nahi ho saki, aur maine team ko bhej di hai. "
    "Kya aap thora sa likh kar bata sakte hain, ya PDF/screenshot bhej dein?",
    "ar": "شكرًا. لم أتمكن من فتح هذا الملف هنا، وقد أرسلته إلى الفريق. "
    "هل يمكنك وصفه باختصار أو إرساله كملف PDF أو لقطة شاشة؟",
}
MEETING_NOTICES = {
    "en": "Happy to set up a meeting. Which days and times suit you? "
    "Our team will confirm a time here.",
    "roman_ur": "Zaroor, meeting rakh lete hain. Aap ko kaun se din aur waqt theek rahenge? "
    "Hamari team yahan waqt confirm kar degi.",
    "ar": "يسعدنا ترتيب اجتماع. ما الأيام والأوقات المناسبة لك؟ سيؤكد فريقنا الموعد هنا.",
}


def notice_in(notices: dict[str, str], language: str | None) -> str:
    return notices.get(language or "en", notices["en"])
