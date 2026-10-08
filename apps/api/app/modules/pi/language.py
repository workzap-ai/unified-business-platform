"""Which language a customer wrote in, decided by code, not the model.

pi must answer in the language of the customer's latest words. Models drift toward the
conversation's earlier language, so the system detects it here and the reply is checked
against it. Only clear signals count; anything unclear returns None and the caller falls
back to the conversation's last known language.
"""

import re

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
    of and for with from about into on at by or but not no yes
    there here some any more much many also just only very really
    """.split()
)
# Words both sides use all the time ("me", "to", "is", "main", "hi", "do") and nouns
# Roman Urdu borrows ("website", "design", "price") never count.

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


def detect_language(text: str | None) -> str | None:
    """'en', 'roman_ur' or 'ar' when the text clearly shows one, otherwise None.
    Urdu or Hindi written in its own script is 'roman_ur': pi answers those in Roman
    Urdu/Hindi (see the service prompt)."""
    text = (text or "").strip()
    if not text:
        return None
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
    urdu = sum(word in ROMAN_URDU for word in words)
    english = sum(word in ENGLISH for word in words)
    if urdu > english:
        return "roman_ur"
    if english > urdu:
        return "en"
    return "roman_ur" if urdu else None


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
MEDIA_NOTICES = {
    "en": "Thanks for the attachment. A member of our team will review it and reply here.",
    "roman_ur": "Attachment bhejne ka shukriya. Hamari team ise dekh kar yahan jawab degi.",
    "ar": "شكرًا على المرفق. سيراجعه أحد أعضاء فريقنا ويرد عليك هنا.",
}


def notice_in(notices: dict[str, str], language: str | None) -> str:
    return notices.get(language or "en", notices["en"])
