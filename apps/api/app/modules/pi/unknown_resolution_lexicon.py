"""PS-5: fixed wording for the unknown-resolution selector. Data only: no logic that decides
anything.

Every question is a short fixed template in four languages (English, Roman Urdu, Urdu script,
Arabic). Hindi falls back to English. A template has exactly one question mark and ends with it, has
no digit, and carries no solution, price, quote, offer, payment or promise word. The owner's own
words may be put in one slot (`tried_outcome`) only after `safe_slot`.

Written by one author, not reviewed by a native speaker of Urdu or Arabic: the lint in
`unknown_resolution.lint_question` checks the form, not the quality of the language.
"""

import re

LANGUAGES = ("en", "roman_ur", "ur", "ar")

# key -> language -> template (a "{what}" slot only where a slot template exists)
QUESTIONS: dict[str, dict[str, str]] = {
    "budget_ceiling": {
        "en": "What is the most you could put towards this?",
        "roman_ur": "Is kaam par aap zyada se zyada kitna kharch kar sakte hain?",
        "ur": "اس کام پر آپ زیادہ سے زیادہ کتنا خرچ کر سکتے ہیں؟",
        "ar": "ما هو أقصى مبلغ يمكنك إنفاقه على هذا الأمر؟",
    },
    "budget_currency_period": {
        "en": "Is that budget per month or a one-off amount, and in which currency?",
        "roman_ur": "Ye budget har mahine ka hai ya ek hi baar ka, aur kis currency mein?",
        "ur": "کیا یہ بجٹ ہر مہینے کا ہے یا ایک ہی بار کا، اور کس کرنسی میں؟",
        "ar": "هل هذه الميزانية شهرية أم مرة واحدة، وبأي عملة؟",
    },
    "staff_headcount": {
        "en": "How many extra people could you take on for this, if any?",
        "roman_ur": "Is kaam ke liye aap kitne aur log rakh sakte hain, agar rakh sakte hain?",
        "ur": "اس کام کے لیے آپ کتنے مزید لوگ رکھ سکتے ہیں، اگر رکھ سکتے ہیں؟",
        "ar": "كم شخصاً إضافياً يمكنك توظيفه لهذا الأمر، إن أمكن؟",
    },
    "deadline_duration": {
        "en": "How soon does this need to be working, for example in how many days or weeks?",
        "roman_ur": "Ye kaam kab tak chalna chahiye, jaise kitne din ya hafton mein?",
        "ur": "یہ کام کب تک چلنا چاہیے، مثلاً کتنے دن یا ہفتوں میں؟",
        "ar": "متى يجب أن يعمل هذا، مثلاً خلال كم يوماً أو أسبوعاً؟",
    },
    "cannot_change_detail": {
        "en": "What exactly is it that you cannot change or cannot do, in a few plain words?",
        "roman_ur": (
            "Wo kya cheez hai jo aap nahi badal sakte ya nahi kar sakte, thode saaf lafzon mein?"
        ),
        "ur": "وہ کیا چیز ہے جو آپ بدل نہیں سکتے یا نہیں کر سکتے، چند سادہ لفظوں میں؟",
        "ar": "ما الذي لا يمكنك تغييره أو فعله بالتحديد، بكلمات بسيطة؟",
    },
    "tried_outcome": {
        "en": "When you tried that before, did it help or not?",
        "roman_ur": "Jab aap ne pehle ye aazmaya, to kya is se faida hua ya nahi?",
        "ur": "جب آپ نے پہلے یہ آزمایا تو کیا اس سے فائدہ ہوا یا نہیں؟",
        "ar": "عندما جرّبت ذلك سابقاً، هل ساعدك أم لا؟",
    },
    "tried_detail": {
        "en": "What exactly did you try before?",
        "roman_ur": "Aap ne pehle kya aazmaya tha?",
        "ur": "آپ نے پہلے کیا آزمایا تھا؟",
        "ar": "ماذا جرّبت سابقاً بالتحديد؟",
    },
    "place_allowed": {
        "en": "Which places or areas can you work in?",
        "roman_ur": "Aap kin jagahon ya ilaqon mein kaam kar sakte hain?",
        "ur": "آپ کن جگہوں یا علاقوں میں کام کر سکتے ہیں؟",
        "ar": "في أي أماكن أو مناطق يمكنك العمل؟",
    },
    "tools_resources": {
        "en": "What tools or equipment do you already have for this?",
        "roman_ur": "Is kaam ke liye aap ke paas pehle se kaun se tools ya saman hain?",
        "ur": "اس کام کے لیے آپ کے پاس پہلے سے کون سے اوزار یا سامان ہیں؟",
        "ar": "ما الأدوات أو المعدات التي لديك بالفعل لهذا الأمر؟",
    },
    "expected_outcome": {
        "en": "What would a good result look like for you, in plain words?",
        "roman_ur": "Aap ke liye achha nateeja kaisa hoga, saaf lafzon mein?",
        "ur": "آپ کے لیے اچھا نتیجہ کیسا ہوگا، سادہ لفظوں میں؟",
        "ar": "كيف تبدو النتيجة الجيدة بالنسبة لك، بكلمات بسيطة؟",
    },
}

# the one template with the owner's own words in it
QUESTIONS_WITH_WHAT: dict[str, dict[str, str]] = {
    "tried_outcome": {
        "en": 'When you tried "{what}" before, did it help or not?',
        "roman_ur": 'Jab aap ne pehle "{what}" aazmaya, to kya is se faida hua ya nahi?',
        "ur": 'جب آپ نے پہلے "{what}" آزمایا تو کیا اس سے فائدہ ہوا یا نہیں؟',
        "ar": 'عندما جرّبت "{what}" سابقاً، هل ساعدك أم لا؟',
    },
}

# said before a repeated question: a rough answer is enough (never ends with a question mark)
REASK_PREFIX = {
    "en": "A rough answer is fine. ",
    "roman_ur": "Andaza bhi theek hai. ",
    "ur": "اندازہ بھی ٹھیک ہے۔ ",
    "ar": "إجابة تقريبية تكفي. ",
}

# words no question may contain (solution, price, quote, offer, payment, promise, secrets)
BANNED_WORDS = frozenset(
    """price prices pricing quote quotes quotation offer offers guarantee guaranteed promise
    promised discount free buy purchase package invoice pay payment card password otp pin cnic
    qeemat qimat wada waada muft gareeb guarantee""".split()
)
BANNED_SUBSTRINGS = (
    "قیمت",
    "وعدہ",
    "مفت",
    "گارنٹی",
    "ادائیگی",
    "پاس ورڈ",
    "سعر",
    "وعد",
    "مجاني",
    "ضمان",
    "دفع",
    "كلمة المرور",
    "عرض",
)
AMERICAN_SPELLINGS = frozenset(
    """color colors center centers organize organizes analyze analyzes favor favors license
    labor behavior neighbor catalog program realize recognize optimize prioritize
    customize minimize maximize""".split()
)
AMERICAN_ENDING = re.compile(r"\b[a-z]{3,}iz(?:e|es|ed|ing|ation)\b")

# a reply that gives nothing: kept as unknown, never read as a value
NON_ANSWER_CUES = (
    r"\b(?:maybe|perhaps|not sure|unsure|no idea|i do not know|i don'?t know|dont know|don'?t know|"
    r"do not know|let me think|let me check|will see|we will see|we'll see|not now|later|"
    r"i will tell you|i'll tell you|can'?t say|cannot say|hmm+|umm+|ok|okay|fine|sure|yes|"
    r"no|nope|pata nahi|pata nhi|maloom nahi|maloom nhi|shayad|dekhte hain|dekhenge|dekh lete hain|"
    r"sochna hai|soch lete hain|baad mein|abhi nahi|kuch kah nahi sakta|kuch keh nahi sakta|"
    r"nahi pata|bata dunga|bata dungi|haan|han|ji|jee|nahi|nhi|theek hai|thik hai|acha|accha)\b"
)
NON_ANSWER_OTHER = (
    "پتہ نہیں",
    "پتا نہیں",
    "معلوم نہیں",
    "شاید",
    "دیکھتے ہیں",
    "دیکھیں گے",
    "سوچنا ہے",
    "بعد میں",
    "ابھی نہیں",
    "ٹھیک ہے",
    "جی",
    "ہاں",
    "نہیں",
    "لا أعرف",
    "لا ادري",
    "لا أدري",
    "ربما",
    "لست متأكد",
    "لست متأكدا",
    "سنرى",
    "لاحقاً",
    "لاحقا",
    "ليس الآن",
    "حسناً",
    "حسنا",
    "نعم",
    "لا",
    "ठीक है",
    "पता नहीं",
    "शायद",
    "देखते हैं",
)
# a hedge before a value makes the value uncertain ("maybe 50k"): kept unknown, not read
HEDGE_CUES = (
    r"\b(?:maybe|perhaps|might|could be|not sure|i guess|i think|shayad|ho sakta|pata nahi|"
    r"dekhte hain)\b"
)
HEDGE_OTHER = ("شاید", "ربما", "ممکن ہے", "ممكن", "लगभग नहीं", "शायद")
# two values joined by "or": the owner has not decided ("2 or 3 people")
EITHER_OR = re.compile(r"\d\D{0,16}?(?<!\w)(?:or|ya|ya phir|یا|أو|او)(?!\w)\s*\d")

# a figure is only a budget when the message talks about money limits
BUDGET_CUES = (
    r"\b(?:budget|afford|spend|spending|spent|cost|costs|money|funds?|can pay|put towards|"
    r"kharch|kharcha|kharcha|bajet|paisa|paise|rupay|rupees?)\b"
)
BUDGET_CUES_OTHER = (
    "بجٹ",
    "خرچ",
    "پیسے",
    "روپے",
    "ميزانية",
    "ميزانيه",
    "تنفق",
    "أنفق",
    "مبلغ",
    "ریال",
)
DEADLINE_CUES = (
    r"\b(?:deadline|due|by|within|before|need it|needs to|must be|chahiye|tak|mein|me)\b"
)
DEADLINE_CUES_OTHER = ("ڈیڈ لائن", "تک", "کے اندر", "موعد", "خلال", "قبل")

CURRENCIES = {
    "pkr": "PKR",
    "rs": "PKR",
    "rupee": "PKR",
    "rupees": "PKR",
    "rupay": "PKR",
    "rupaye": "PKR",
    "روپے": "PKR",
    "روپیہ": "PKR",
    "inr": "INR",
    "usd": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "$": "USD",
    "ڈالر": "USD",
    "دولار": "USD",
    "aed": "AED",
    "dirham": "AED",
    "dirhams": "AED",
    "درهم": "AED",
    "sar": "SAR",
    "riyal": "SAR",
    "riyals": "SAR",
    "ریال": "SAR",
    "ريال": "SAR",
    "gbp": "GBP",
    "pound": "GBP",
    "pounds": "GBP",
    "£": "GBP",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "€": "EUR",
}
PERIODS = {
    "month": "month",
    "monthly": "month",
    "mahina": "month",
    "mahine": "month",
    "mahana": "month",
    "mahanah": "month",
    "ماہانہ": "month",
    "مہینہ": "month",
    "مہینے": "month",
    "شهري": "month",
    "شهريا": "month",
    "شهر": "month",
    "year": "year",
    "yearly": "year",
    "annual": "year",
    "annually": "year",
    "saal": "year",
    "salana": "year",
    "سالانہ": "year",
    "سنوي": "year",
    "week": "week",
    "weekly": "week",
    "hafta": "week",
    "haftawar": "week",
    "ہفتہ": "week",
    "اسبوع": "week",
    "أسبوعي": "week",
}
ONE_OFF = re.compile(
    r"\b(?:one[- ]?off|one time|once|in total|total|overall|lump ?sum|ek baar|ek hi baar|"
    r"sirf ek baar)\b"
)
ONE_OFF_OTHER = ("ایک بار", "ایک ہی بار", "مرة واحدة", "دفعة واحدة", "إجمالي", "کل")

WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?", re.UNICODE)

# words that may stand next to a bare headcount ("3 people", "5 log")
STAFF_FILLER = frozenset(
    """people person persons log aadmi banda bande staff extra more additional employees members
    workers aur hands""".split()
)
