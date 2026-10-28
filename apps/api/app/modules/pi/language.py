# ruff: noqa: E501
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
PERSIAN_LETTERS = re.compile("[پچگژکی]")
ARABIC_SCRIPT = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
LATIN_WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")

# Scripts pi has no fixed notices for: the reply is written by the model in the same language
# (Chinese, Japanese, Korean, Russian...), never in the language the chat used before.
OTHER_SCRIPTS: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("Japanese", re.compile(r"[぀-ヿ]")),
    ("Korean", re.compile(r"[가-힯]")),
    ("Chinese (Simplified)", re.compile(r"[㐀-鿿]")),
    ("Russian", re.compile(r"[Ѐ-ӿ]")),
    ("Thai", re.compile(r"[฀-๿]")),
    ("Hebrew", re.compile(r"[֐-׿]")),
    ("Greek", re.compile(r"[Ͱ-Ͽ]")),
    ("Punjabi (Gurmukhi)", re.compile(r"[਀-੿]")),
)


def other_script(text: str | None) -> str | None:
    """The language name when the text is mostly in a script pi keeps no fixed notices for."""
    text = text or ""
    latin = len(re.findall(r"[A-Za-z]", text))
    arabic = len(ARABIC_SCRIPT.findall(text))
    if (
        arabic >= max(2, latin // 3)
        and PERSIAN_LETTERS.search(text)
        and not URDU_LETTERS.search(text)
    ):
        return "Persian"  # Persian and Dari (Arabic script with Persian letters, no Urdu ones)
    for name, pattern in OTHER_SCRIPTS:
        if len(pattern.findall(text)) >= max(2, latin // 3):
            return name
    return None


# Latin-script languages pi keeps no fixed notices for, told apart by their own small words. The
# model writes the reply in the same language; these only say which one the person is using.
LATIN_OTHER: dict[str, frozenset[str]] = {
    "Indonesian": frozenset(
        "yang dan aku saya kamu anda tidak gak ga tolong pakai bahasa indonesia indonesian apa ini itu"
        " bisa mau kenapa dengan untuk sama kalau buat bukan sudah belum juga dong sih punya usaha"
        " jualan lagi ada masalah sering keliru siapa nomor mohon terima kasih halo selamat pagi"
        " bagaimana tapi karena atau jadi lebih sangat banget aja deh".split()
    ),
    "Turkish": frozenset(
        "ama ben benim bir bu cok degil değil evet hayir hayır icin isletme için işletme karışıyor lutfen lütfen mağaza mağazam merhaba müşteri nasil nasıl olur sen senin sipariş siparişler sorun sık tamam teşekkürler var ve yardım yok çok".split()
    ),
    "French": frozenset(
        "aide avec besoin bonjour boutique c'est client clients commandes comment d'accord dans de des du elle entreprise est et il j'ai je la le les leur ma magasin mais merci mes mon ne non nous oui pas pour problème que qui s'il ses souvent suis sur svp toujours très tu un une vous".split()
    ),
    "Spanish": frozenset(
        "ayuda cada clientes como con cómo de el en favor frecuencia gracias hola la las los mes mi mis muy necesito negocio no para pedidos pero por problema que quiero qué sí tengo tienda un una vale y".split()
    ),
    "German": frozenset(
        "aber bestellungen bin bitte danke das der die ein eine einen geschäft gut habe hallo hilfe ich ist ja kunden laden mein meine nein nicht oft problem sehr sie sind und verwechselt wie wir".split()
    ),
}


def latin_hits(text: str | None, name: str) -> int:
    words = set(re.findall(r"[^\W\d_]+", (text or "").lower()))
    return len(words & LATIN_OTHER[name])


def latin_other(text: str | None) -> str | None:
    """A Latin-script language pi has no fixed notices for, when its own words clearly outnumber
    the English and Roman Urdu ones ("Pakai bahasa Indonesia ya")."""
    words = set(re.findall(r"[^\W\d_]+", (text or "").lower()))
    rival = len(words & ROMAN_URDU) + len(words & ENGLISH)
    best_name, best = None, 0
    for name, vocabulary in LATIN_OTHER.items():
        hits = len(words & vocabulary)
        if hits > best:
            best_name, best = name, hits
    if best >= 2 and best > rival:
        return best_name
    return None


def in_language(text: str | None, name: str) -> bool:
    """The reply is already in that language: its script, or enough of its own words."""
    if name in LATIN_OTHER:
        return latin_hits(text, name) >= 2
    return in_script(text, name)


ASKED_LANGUAGE = re.compile(
    r"\b(?:in|speak|talk|reply|write|answer|use|pakai|gunakan|berbahasa|translate(?:\s+to)?|auf|en)\s+(?:to me\s+)?(?:in\s+)?"
    r"(?:bahasa\s+)?(indonesian?|indonesia|malay|turkish|french|spanish|german|persian|farsi|dari|"
    r"pashto|swahili|portuguese|italian|russian|chinese|japanese|korean)\b",
    re.IGNORECASE,
)
ASKED_NAMES = {
    "indonesian": "Indonesian",
    "indonesia": "Indonesian",
    "malay": "Malay",
    "turkish": "Turkish",
    "french": "French",
    "spanish": "Spanish",
    "german": "German",
    "persian": "Persian",
    "farsi": "Persian",
    "dari": "Persian",
    "pashto": "Pashto",
    "swahili": "Swahili",
    "portuguese": "Portuguese",
    "italian": "Italian",
    "russian": "Russian",
    "chinese": "Chinese (Simplified)",
    "japanese": "Japanese",
    "korean": "Korean",
}


def asked_language(text: str | None) -> str | None:
    """A language the person asks pi to use ("Pakai bahasa Indonesia", "reply in French")."""
    found = ASKED_LANGUAGE.search(text or "")
    return ASKED_NAMES.get(found.group(1).lower()) if found else None


def in_script(text: str | None, name: str) -> bool:
    """The text is written mostly in that other language's script (a reply is checked with this)."""
    pattern = dict(OTHER_SCRIPTS).get(name)
    letters = len(re.findall(r"[^\W\d_]", text or ""))
    return pattern is not None and len(pattern.findall(text or "")) * 2 >= letters


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
    "en": "I'm checking this with the Workzap team, and they'll confirm here.",
    "roman_ur": "Ise Workzap ki team se check kiya ja raha hai, wo yahin tasdeeq karein ge.",
    "ar": "تم. أتحقق من ذلك مع فريق Workzap وسيؤكدون لك هنا.",
}
BRAIN_ACK_NOTICES = {
    "en": "Thanks, I've got that.",
    "roman_ur": "Shukriya, ye baat mere paas hai.",
    "ar": "شكرًا، وصلتني الفكرة.",
}
MEDIA_NOTICES = {
    "en": "Thanks for the attachment. A member of our team will review it and reply here.",
    "roman_ur": "Attachment bhejne ka shukriya. Hamari team ise dekh kar yahan jawab degi.",
    "ar": "شكرًا على المرفق. سيراجعه أحد أعضاء فريقنا ويرد عليك هنا.",
}
# pi keeps the chat while the team checks something (no handoff).
TEAM_CHECK_NOTICES = {
    "en": "I'm checking this with the team and will confirm here shortly.",
    "roman_ur": "Team se confirm karke yahin jaldi update milega.",
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


# The same notices in Urdu script, Hindi, Persian, French and Spanish, so a chat in those languages
# never gets an English line (Part 14, language lock). Urdu and Hindi wording avoids gendered verbs.
# Native-speaker review is still wanted before wide use.
_MORE_NOTICES: dict[str, dict[str, str]] = {
    "ur": {
        "handoff": "آپ کے پیغام کا شکریہ۔ ہماری ٹیم جلد ہی یہاں آپ کو جواب دے گی۔",
        "brain_handoff": "آپ کے پیغام کا شکریہ۔ Workzap کی ٹیم کا کوئی رکن یہیں جواب دے گا۔",
        "brain_team_check": "اسے Workzap کی ٹیم سے چیک کیا جا رہا ہے، وہ یہیں تصدیق کریں گے۔",
        "brain_ack": "شکریہ، یہ بات میرے پاس ہے۔",
        "media": "اٹیچمنٹ بھیجنے کا شکریہ۔ ہماری ٹیم اسے دیکھ کر یہاں جواب دے گی۔",
        "team_check": "ٹیم سے تصدیق کر کے یہیں جلد اپ ڈیٹ ملے گا۔",
        "tech_down": "pi میں ابھی مسئلہ ہے۔ آپ کے پیغامات محفوظ ہیں، اور pi جیسے ہی ممکن ہوا جواب دے گا۔",
        "tool_fail": "ابھی اسے محفوظ نہیں کیا جا سکا۔ کیا آپ تھوڑی دیر بعد دوبارہ بھیج سکتے ہیں؟",
        "video": "یہاں ویڈیو دیکھنا ممکن نہیں۔ کیا آپ ایک لائن میں بتا سکتے ہیں کہ اس میں کیا ہے؟",
        "voice": "اس وائس نوٹ کی پوری بات سمجھ نہیں آئی۔ کیا آپ بنیادی مسئلہ ایک لائن میں لکھ سکتے ہیں؟",
        "media_unreadable": "شکریہ۔ یہ فائل یہاں کھل نہیں سکی، اور اسے ٹیم کو بھیج دیا گیا ہے۔ "
        "کیا آپ مختصر لکھ کر بتا سکتے ہیں، یا PDF یا اسکرین شاٹ بھیج دیں؟",
        "meeting": "ضرور، میٹنگ رکھ لیتے ہیں۔ آپ کو کون سے دن اور وقت ٹھیک رہیں گے؟ "
        "ہماری ٹیم یہاں وقت کی تصدیق کر دے گی۔",
    },
    "hi": {
        "handoff": "आपके संदेश के लिए धन्यवाद। हमारी टीम जल्द ही यहीं आपको जवाब देगी।",
        "brain_handoff": "आपके संदेश के लिए धन्यवाद। Workzap टीम का कोई सदस्य यहीं जवाब देगा।",
        "brain_team_check": "इसे Workzap टीम से जाँचा जा रहा है, वे यहीं पुष्टि करेंगे।",
        "brain_ack": "धन्यवाद, यह बात मेरे पास है।",
        "media": "अटैचमेंट भेजने के लिए धन्यवाद। हमारी टीम इसे देखकर यहीं जवाब देगी।",
        "team_check": "टीम से पुष्टि करके यहीं जल्द अपडेट मिलेगा।",
        "tech_down": "pi में अभी समस्या है। आपके संदेश सुरक्षित हैं, और pi जैसे ही संभव होगा जवाब देगा।",
        "tool_fail": "इसे अभी सहेजा नहीं जा सका। क्या आप थोड़ी देर बाद दोबारा भेज सकते हैं?",
        "video": "यहाँ वीडियो देखना संभव नहीं है। क्या आप एक लाइन में बता सकते हैं कि इसमें क्या है?",
        "voice": "इस वॉइस नोट की पूरी बात समझ नहीं आई। क्या आप मुख्य समस्या एक लाइन में लिख सकते हैं?",
        "media_unreadable": "धन्यवाद। यह फ़ाइल यहाँ खुल नहीं सकी, और इसे टीम को भेज दिया गया है। "
        "क्या आप थोड़े शब्दों में बता सकते हैं, या PDF या स्क्रीनशॉट भेज सकते हैं?",
        "meeting": "ज़रूर, मीटिंग रख लेते हैं। आपको कौन से दिन और समय ठीक रहेंगे? "
        "हमारी टीम यहीं समय की पुष्टि कर देगी।",
    },
    "fa": {
        "handoff": "از پیام شما سپاسگزاریم. یکی از اعضای تیم ما به‌زودی همین‌جا پاسخ می‌دهد.",
        "brain_handoff": "از پیام شما سپاسگزاریم. یکی از اعضای تیم Workzap همین‌جا پاسخ می‌دهد.",
        "brain_team_check": "این موضوع با تیم Workzap بررسی می‌شود و همین‌جا تأیید خواهند کرد.",
        "brain_ack": "ممنون، این موضوع را دریافت کردم.",
        "media": "از ارسال فایل سپاسگزاریم. تیم ما آن را بررسی می‌کند و همین‌جا پاسخ می‌دهد.",
        "team_check": "با تیم هماهنگ می‌کنم و به‌زودی همین‌جا خبر می‌دهم.",
        "tech_down": "pi اکنون با مشکل روبه‌رو است. پیام‌های شما ذخیره شده‌اند و pi به محض امکان پاسخ می‌دهد.",
        "tool_fail": "الان نتوانستم این را ذخیره کنم. می‌شود کمی بعد دوباره بفرستید؟",
        "video": "نمی‌توانم اینجا ویدیو ببینم. می‌شود در یک خط بگویید چه چیزی در آن است؟",
        "voice": "همه‌ی پیام صوتی را متوجه نشدم. می‌شود مشکل اصلی را در یک خط بنویسید؟",
        "media_unreadable": "ممنون. نتوانستم این فایل را اینجا باز کنم و آن را برای تیم فرستادم. "
        "می‌شود کوتاه توضیح دهید یا آن را به‌صورت PDF یا اسکرین‌شات بفرستید؟",
        "meeting": "با کمال میل جلسه می‌گذاریم. چه روزها و ساعت‌هایی برای شما مناسب است؟ "
        "تیم ما زمان را همین‌جا تأیید می‌کند.",
    },
    "fr": {
        "handoff": "Merci pour votre message. Un membre de notre équipe vous répondra ici sous peu.",
        "brain_handoff": "Merci pour votre message. Un membre de l'équipe Workzap vous répondra ici.",
        "brain_team_check": "Je vérifie cela avec l'équipe Workzap, qui confirmera ici.",
        "brain_ack": "Merci, j'ai bien reçu cela.",
        "media": "Merci pour la pièce jointe. Un membre de notre équipe l'examinera et vous répondra ici.",
        "team_check": "Je vérifie cela avec l'équipe et je confirme ici sous peu.",
        "tech_down": "pi rencontre un problème en ce moment. Vos messages sont enregistrés, "
        "et pi répondra dès que possible.",
        "tool_fail": "Je n'ai pas pu enregistrer cela à l'instant. Pourriez-vous le renvoyer dans un moment ?",
        "video": "Je ne peux pas regarder de vidéos ici. Pourriez-vous me dire en une ligne ce qu'elle montre ?",
        "voice": "Je n'ai pas bien compris ce message vocal. "
        "Pourriez-vous écrire le problème principal en une ligne ?",
        "media_unreadable": "Merci. Je n'ai pas pu ouvrir ce fichier ici et je l'ai transmis à l'équipe. "
        "Pourriez-vous le décrire en quelques mots, ou l'envoyer en PDF ou en capture d'écran ?",
        "meeting": "Avec plaisir, organisons une réunion. Quels jours et horaires vous conviennent ? "
        "Notre équipe confirmera l'horaire ici.",
    },
    "es": {
        "handoff": "Gracias por su mensaje. Un miembro de nuestro equipo le responderá aquí en breve.",
        "brain_handoff": "Gracias por su mensaje. Un miembro del equipo de Workzap le responderá aquí.",
        "brain_team_check": "Lo estoy revisando con el equipo de Workzap, que lo confirmará aquí.",
        "brain_ack": "Gracias, lo he recibido.",
        "media": "Gracias por el archivo adjunto. Un miembro de nuestro equipo lo revisará y le responderá aquí.",
        "team_check": "Lo estoy confirmando con el equipo y le aviso aquí en breve.",
        "tech_down": "pi tiene un problema en este momento. Sus mensajes están guardados "
        "y pi responderá en cuanto pueda.",
        "tool_fail": "No pude guardarlo ahora mismo. ¿Podría enviarlo de nuevo en un momento?",
        "video": "No puedo ver vídeos aquí. ¿Podría decirme en una línea qué muestra?",
        "voice": "No logré entender todo el mensaje de voz. ¿Podría escribir el problema principal en una línea?",
        "media_unreadable": "Gracias. No pude abrir ese archivo aquí y lo he pasado al equipo. "
        "¿Podría describirlo en pocas palabras, o enviarlo como PDF o captura de pantalla?",
        "meeting": "Con gusto organizamos una reunión. ¿Qué días y horarios le convienen? "
        "Nuestro equipo confirmará la hora aquí.",
    },
}
for _lang, _lines in _MORE_NOTICES.items():
    for _table, _key in (
        (HANDOFF_NOTICES, "handoff"),
        (BRAIN_HANDOFF_NOTICES, "brain_handoff"),
        (BRAIN_TEAM_CHECK_NOTICES, "brain_team_check"),
        (BRAIN_ACK_NOTICES, "brain_ack"),
        (MEDIA_NOTICES, "media"),
        (TEAM_CHECK_NOTICES, "team_check"),
        (TECH_DOWN_NOTICES, "tech_down"),
        (TOOL_FAIL_NOTICES, "tool_fail"),
        (VIDEO_UNREADABLE_NOTICES, "video"),
        (VOICE_UNREADABLE_NOTICES, "voice"),
        (MEDIA_UNREADABLE_NOTICES, "media_unreadable"),
        (MEETING_NOTICES, "meeting"),
    ):
        _table[_lang] = _lines[_key]


def notice_in(notices: dict[str, str], language: str | None) -> str:
    return notices.get(language or "en", notices["en"])
