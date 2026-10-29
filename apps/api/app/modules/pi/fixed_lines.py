# ruff: noqa: E501  (one fixed line per row reads better than wrapped text)
"""The fixed lines pi sends without asking a model, in the eight priority languages (owner order:
English, Roman Urdu, Urdu, Arabic, Hindi, French, Persian, Spanish). A fixed line is the safe
fallback when a rewrite fails, so for these languages it must never be English: the opening, the AI
answer, the offer, the card and ID reminders, the emergency answer and the cost answer.

The Hindi, French, Persian and Spanish wording was approved by the owner on 2026-10-26; the Urdu and
Arabic lines were written from the Roman Urdu and English ones in the same files. Anything a language
has no line for here comes from the older per-file tables, and from English last."""

import re
from typing import Any

PRIORITY = ("en", "roman_ur", "ur", "ar", "fr", "fa", "es")
CODES = {"Persian": "fa", "French": "fr", "Spanish": "es", "Urdu": "ur"}

LINES: dict[str, dict[str, str]] = {
    "opening": {
        "en": "Hi, I'm pi, an AI from Workzap.",
        "roman_ur": "Hi, main pi hoon, Workzap ka AI.",
        "ur": "ہیلو، میں pi ہوں، Workzap کی طرف سے ایک مصنوعی ذہانت۔",
        "ar": "مرحباً، أنا pi، ذكاء اصطناعي من Workzap.",
        "fr": "Bonjour, je suis pi, une IA de Workzap.",
        "fa": "سلام، من pi هستم، یک هوش مصنوعی از Workzap.",
        "es": "Hola, soy pi, una IA de Workzap.",
    },
    "ai_answer": {
        "en": "I'm an AI, not a person. I'm pi, from Workzap.",
        "roman_ur": "Main AI hoon, insaan nahi. Main pi hoon, Workzap se.",
        "ur": "میں ایک مصنوعی ذہانت ہوں، انسان نہیں۔ میں pi ہوں، Workzap سے۔",
        "ar": "أنا ذكاء اصطناعي، ولست إنساناً. أنا pi من Workzap.",
        "fr": "Je suis une IA, pas une personne. Je suis pi, de Workzap.",
        "fa": "من یک هوش مصنوعی هستم، نه یک انسان. من pi از Workzap هستم.",
        "es": "Soy una IA, no una persona. Soy pi, de Workzap.",
    },
    "offer": {
        "en": "Shall I get one solution document and a quote made for all of these together?",
        "roman_ur": "Kya main in sab ke liye ek solution document aur quote banwa doon?",
        "ur": "کیا میں ان سب کے لیے ایک حل کی دستاویز اور کوٹیشن بنوا دوں؟",
        "ar": "هل أجهّز لكل هذه المشكلات وثيقة حل واحدة وعرض سعر؟",
        "fr": "Souhaitez-vous que je fasse préparer un seul document de solution et un devis pour l'ensemble ?",
        "fa": "آیا مایلید برای همه این‌ها یک سند راه‌حل و یک پیش‌فاکتور آماده کنم؟",
        "es": "¿Quiere que prepare un documento de solución y un presupuesto para todo esto junto?",
    },
    "card": {
        "en": "Please don't send card numbers here. I never need them, and payment never happens in this chat. I've left that out of my notes.",
        "roman_ur": "Meherbani karke yahan card number na bhejein. Mujhe in ki zaroorat nahi, aur payment is chat mein kabhi nahi hoti. Maine ise apne notes se nikaal diya hai.",
        "ur": "براہِ مہربانی یہاں کارڈ نمبر نہ بھیجیں۔ مجھے ان کی ضرورت نہیں، اور ادائیگی اس چیٹ میں کبھی نہیں ہوتی۔ میں نے اسے اپنے نوٹس سے نکال دیا ہے۔",
        "ar": "يرجى عدم إرسال أرقام البطاقات هنا. لا أحتاج إليها أبدًا، والدفع لا يتم أبدًا في هذه المحادثة. لقد أبقيتها خارج ملاحظاتي.",
        "fr": "Merci de ne pas envoyer de numéros de carte ici. Je n'en ai jamais besoin, et le paiement ne se fait jamais dans ce chat. Je l'ai laissé de côté dans mes notes.",
        "fa": "لطفاً شماره کارت را اینجا نفرستید. من هرگز به آن نیاز ندارم و پرداخت هیچ‌گاه در این گفتگو انجام نمی‌شود. آن را از یادداشت‌هایم کنار گذاشته‌ام.",
        "es": "Por favor, no envíe números de tarjeta aquí. Nunca los necesito, y el pago nunca se hace en este chat. Lo he dejado fuera de mis notas.",
    },
    "id": {
        "en": "Please don't send ID numbers here. I don't need them. I've left that out of my notes.",
        "roman_ur": "Meherbani karke yahan ID number na bhejein. Mujhe in ki zaroorat nahi. Maine ise apne notes se nikaal diya hai.",
        "ur": "براہِ مہربانی یہاں شناختی نمبر نہ بھیجیں۔ مجھے ان کی ضرورت نہیں۔ میں نے اسے اپنے نوٹس سے نکال دیا ہے۔",
        "ar": "يرجى عدم إرسال أرقام الهوية هنا. لا أحتاج إليها. لقد أبقيتها خارج ملاحظاتي.",
        "fr": "Merci de ne pas envoyer de numéros de pièce d'identité ici. Je n'en ai pas besoin. Je l'ai laissé de côté dans mes notes.",
        "fa": "لطفاً شماره مدارک شناسایی را اینجا نفرستید. به آن نیازی ندارم. آن را از یادداشت‌هایم کنار گذاشته‌ام.",
        "es": "Por favor, no envíe números de documentos de identidad aquí. No los necesito. Lo he dejado fuera de mis notas.",
    },
    "cost": {
        "en": "The cost depends on what would be built. It is written on the quote before you decide, and the quote is free, not a charge.",
        "roman_ur": "Kharcha is par depend karta hai ke kya banaya jaye. Woh quote par likha hota hai, aap ke faisle se pehle, aur quote muft hai, koi charge nahi.",
        "ur": "لاگت اس پر منحصر ہے کہ کیا بنایا جائے۔ وہ آپ کے فیصلے سے پہلے کوٹیشن پر لکھی ہوتی ہے، اور کوٹیشن مفت ہے، کوئی چارج نہیں۔",
        "ar": "تعتمد التكلفة على ما سيتم بناؤه. تُكتب في عرض السعر قبل أن تقرر، وعرض السعر مجاني وليس رسمًا.",
        "fr": "Le coût dépend de ce qui serait construit. Il est écrit sur le devis avant que vous décidiez, et le devis est gratuit, ce n'est pas un paiement.",
        "fa": "هزینه به این بستگی دارد که چه چیزی ساخته شود. پیش از تصمیم شما روی پیش‌فاکتور نوشته می‌شود و پیش‌فاکتور رایگان است، نه یک هزینه.",
        "es": "El coste depende de lo que se construiría. Está escrito en el presupuesto antes de que usted decida, y el presupuesto es gratis, no es un cobro.",
    },
}

# The emergency answers for the new languages. {fire}, {ambulance} and {police} are filled with the
# person's local numbers by safety.emergency_reply. Self-harm and safeguarding keep their longer
# older lines (English, then the translation step) until the owner has seen a wording for them.
EMERGENCY: dict[str, dict[str, str]] = {
    "ur": {
        "fire": "ہنگامی صورتحال میں مدد کرنا میرے بس میں نہیں۔ براہِ مہربانی ابھی {fire} پر کال کریں۔",
        "medical": "ہنگامی صورتحال میں مدد کرنا میرے بس میں نہیں۔ براہِ مہربانی ایمبولینس کے لیے ابھی {ambulance} پر کال کریں۔",
        "violence": "ہنگامی صورتحال میں مدد کرنا میرے بس میں نہیں۔ براہِ مہربانی ابھی {police} پر کال کریں اور محفوظ جگہ پر چلے جائیں۔",
        "generic": "ہنگامی صورتحال میں مدد کرنا میرے بس میں نہیں۔ براہِ مہربانی ابھی {police} پر کال کریں۔",
    },
    "hi": {
        "fire": "आपात स्थिति में मदद करना मेरे बस में नहीं है। कृपया अभी {fire} पर कॉल करें।",
        "medical": "आपात स्थिति में मदद करना मेरे बस में नहीं है। कृपया एम्बुलेंस के लिए अभी {ambulance} पर कॉल करें।",
        "violence": "आपात स्थिति में मदद करना मेरे बस में नहीं है। कृपया अभी {police} पर कॉल करें और सुरक्षित जगह पर चले जाएँ।",
        "generic": "आपात स्थिति में मदद करना मेरे बस में नहीं है। कृपया अभी {police} पर कॉल करें।",
    },
    "fr": {
        "fire": "Je ne peux pas aider en cas d'urgence. Veuillez appeler {fire} maintenant.",
        "medical": "Je ne peux pas aider en cas d'urgence. Veuillez appeler {ambulance} pour une ambulance maintenant.",
        "violence": "Je ne peux pas aider en cas d'urgence. Veuillez appeler {police} maintenant et vous mettre en sécurité.",
        "generic": "Je ne peux pas aider en cas d'urgence. Veuillez appeler {police} maintenant.",
    },
    "fa": {
        "fire": "من نمی‌توانم در موارد اضطراری کمک کنم. لطفاً همین حالا با {fire} تماس بگیرید.",
        "medical": "من نمی‌توانم در موارد اضطراری کمک کنم. لطفاً همین حالا برای آمبولانس با {ambulance} تماس بگیرید.",
        "violence": "من نمی‌توانم در موارد اضطراری کمک کنم. لطفاً همین حالا با {police} تماس بگیرید و به جای امن بروید.",
        "generic": "من نمی‌توانم در موارد اضطراری کمک کنم. لطفاً همین حالا با {police} تماس بگیرید.",
    },
    "es": {
        "fire": "No puedo ayudar con emergencias. Por favor, llame ahora al {fire}.",
        "medical": "No puedo ayudar con emergencias. Por favor, llame ahora al {ambulance} para pedir una ambulancia.",
        "violence": "No puedo ayudar con emergencias. Por favor, llame ahora al {police} y póngase a salvo.",
        "generic": "No puedo ayudar con emergencias. Por favor, llame ahora al {police}.",
    },
}
# What stands for "the number" when the person's country is unknown, in their language
LOCAL_NUMBER = {
    "ur": "آپ کا مقامی ہنگامی نمبر ({numbers})",
    "ar": "رقم الطوارئ المحلي ({numbers})",
    "hi": "आपका स्थानीय आपातकालीन नंबर ({numbers})",
    "fr": "votre numéro d'urgence local ({numbers})",
    "fa": "شماره اورژانس محلی شما ({numbers})",
    "es": "su número de emergencia local ({numbers})",
}

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
ARABIC = re.compile(r"[؀-ۿ]")
URDU_ONLY = re.compile(r"[ٹڈڑںھہےۓ]")
PERSIAN_ONLY = re.compile(r"[پچژگکی]")


def code_of_text(text: str | None, base: str | None = None, *, script: bool = False) -> str:
    """The fixed-line language of what the person wrote. Devanagari (Hindi) and Urdu script are
    answered in Roman Urdu like the rest of that chat (the chat's reply language is `roman_ur`, so
    one chat never mixes scripts); with `script=True` they keep their own script ("hi", "ur"), which
    only safety lines use. Persian or Arabic script is told by its letters, French and Spanish by
    their own words, else `base` (the chat's language) or English."""
    from app.modules.pi.language import latin_other

    text = text or ""
    latin = len(re.findall(r"[A-Za-z]", text))
    if len(DEVANAGARI.findall(text)) > latin:
        return "hi" if script else "roman_ur"
    if len(ARABIC.findall(text)) > latin:
        if URDU_ONLY.search(text):
            return "ur" if script else "roman_ur"
        return "fa" if PERSIAN_ONLY.search(text) else "ar"
    other = latin_other(text)
    if other == "French":
        return "fr"
    if other == "Spanish":
        return "es"
    return base if base in LINES["opening"] else "en"


def code(context: dict[str, Any], *, script: bool = False) -> str:
    """The language the fixed lines of this turn go out in: the language the person asked for or
    wrote ("reply_language_other"), else the script and words of their latest message, else the
    chat's language. Hindi and Urdu script give Roman Urdu unless `script=True` (emergency lines
    stay in the person's own script: they are safety-critical)."""
    other = CODES.get(str(context.get("reply_language_other") or ""))
    if other:
        return other
    base = str(context.get("reply_language") or "en")
    return code_of_text(str(context.get("latest_customer_message") or ""), base, script=script)


def table_language(language: str | None, have: Any, *, persian: bool = False) -> str:
    """The key to use in a table that only has some languages. Urdu and Hindi chats are answered
    in Roman Urdu (`persian=True` adds Persian, for the follow-up tables); anything else the table
    has no entry for falls back to English."""
    key = (language or "en").split("-")[0]
    if key in ("ur", "hi") or (persian and key == "fa"):
        key = "roman_ur"
    return key if key in have else "en"


def line(key: str, language: str | None, default: str | None = None) -> str:
    """One fixed line in that language, else `default`, else English."""
    table = LINES[key]
    return table.get(language or "en") or default or table["en"]
