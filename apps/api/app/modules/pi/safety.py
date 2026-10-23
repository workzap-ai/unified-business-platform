# ruff: noqa: E501  (reply texts and patterns read better on one line each)
"""Safety checks that run before the model (pi Brain spec Part 6 and 9.6).

Pure and deterministic: they read the person's words and say what pi must do, in the person's
language. Emergencies stop the flow (R-EMER), card numbers, passwords and ID numbers are taken out
of what is kept (R-PRIV-02), advice that is not pi's to give is turned down (R-ADV), and the questions
about who pi is get the same honest answers every time (R-DISC, R-META-01). None of these needs a
model, so none of them can be talked out of the rule.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# --- where the person is ---------------------------------------------------------------------

NUMBERS = {
    "PK": {"police": "15", "ambulance": "1122", "fire": "16"},
    "AE": {"police": "999", "ambulance": "998", "fire": "997"},
    "CA": {"police": "911", "ambulance": "911", "fire": "911"},
}
ALL_COUNTRIES = (
    "Pakistan 15 (police), 1122 (rescue and ambulance), 16 (fire); UAE 999 (police), 998 "
    "(ambulance), 997 (fire); Canada 911"
)


def country_of(phone: str | None) -> str | None:
    """PK, AE or CA from a WhatsApp number (digits, with or without +), else None."""
    digits = re.sub(r"\D", "", phone or "")
    for prefix, country in (("92", "PK"), ("971", "AE"), ("1", "CA")):
        if digits.startswith(prefix):
            return country
    return None


# --- emergencies (R-EMER-01 to 04) -----------------------------------------------------------


class Emergency(StrEnum):
    FIRE = "fire"
    MEDICAL = "medical"
    VIOLENCE = "violence"
    SELF_HARM = "self_harm"
    GENERIC = "generic"


EMERGENCY_PATTERNS: tuple[tuple[Emergency, re.Pattern[str]], ...] = (
    (
        Emergency.SELF_HARM,
        re.compile(
            r"\b(?:kill myself|end (?:my life|everything)|suicide|suicidal|want to die|"
            r"don'?t want to live|khudkushi|khud kushi|jaan de (?:dun|doon)|marna chahta|marna chahti|"
            r"zindagi khatam)\b|انتحار|خودکشی|أريد أن أموت|مرنا چاہتا|مرنا چاہتی",
            re.IGNORECASE,
        ),
    ),
    (
        Emergency.FIRE,
        re.compile(
            r"\b(?:there(?:'s| is) (?:a )?fire|(?:caught|catching|on) fire|fire (?:in|at|broke out in) "
            r"(?:my|the|our)\b|(?:building|shop|godown|factory|warehouse) is (?:burning|on fire)|"
            r"aag lag(?:i|gayi|gai|ayi)|(?:shop|godown|factory|dukan|dukaan) mein aag)\b|حريق|حریق|آگ لگ",
            re.IGNORECASE,
        ),
    ),
    (
        Emergency.VIOLENCE,
        re.compile(
            r"\b(?:robbery|robbers?|dacoity|daketi|dakaiti|dakoo|armed (?:men|man|robbers?)|"
            r"(?:has|have|with) (?:a )?(?:gun|guns|knife)|pointing a gun|they are (?:beating|attacking)|"
            r"attacking (?:us|me|the shop)|threatening to kill|death threat|going to kill me|"
            r"looting (?:the|my) (?:shop|store))\b|سرقة مسلحة|ڈکیتی|ڈاکو",
            re.IGNORECASE,
        ),
    ),
    (
        Emergency.MEDICAL,
        re.compile(
            r"\b(?:(?:need|call|send|get) (?:an |the )?ambulance|heart attack|not breathing|"
            r"(?:someone|he|she|worker|staff|guard|driver) "
            r"(?:is |was |got )(?:badly )?(?:hurt|injured|bleeding|unconscious)|accident (?:happened|hua|ho gaya)|"
            r"(?:zakhmi|behosh|khoon beh)\b)|إسعاف",
            re.IGNORECASE,
        ),
    ),
    (
        Emergency.GENERIC,
        re.compile(
            r"\b(?:emergency (?:is )?(?:in progress|happening|right now|going on)|mayday|"
            r"(?:in|having) an emergency|crash(?:ed|ing) (?:right )?now|emergency landing)\b",
            re.IGNORECASE,
        ),
    ),
)


# More ways people say it in Arabic, Urdu and Roman Urdu (spec 6.1, R-EMER-01): only phrases that
# clearly describe something happening now, never a word that also appears in ordinary business talk.
EMERGENCY_PATTERNS = EMERGENCY_PATTERNS + (
    (
        Emergency.SELF_HARM,
        re.compile(
            r"(?:أقتل نفسي|اقتل نفسي|أنهي حياتي|انهي حياتي|لا أريد أن أعيش|لا اريد ان اعيش|"
            r"اريد ان اموت|أبغى أموت|ابغى اموت|اپنی جان لے|مر جانا چاہتا|مر جانا چاہتی)"
            r"|\b(?:mar jana chahta|mar jana chahti|apni jaan le (?:lun|loon|lunga|lungi)|"
            r"zindagi se tang aa gaya|zindagi se tang aa gayi)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Emergency.FIRE,
        re.compile(
            r"(?:شعلت النار|اشتعلت النار|اشتعل حريق|النار في|آگ لگی|آگ لگ گئی|آگ بھڑک)"
            r"|\b(?:aag bhadak|aag lag gaye)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Emergency.VIOLENCE,
        re.compile(
            r"(?:لصوص|سطو مسلح|إطلاق نار|اطلاق نار|يضربوننا|يهاجمون|چور (?:اندر|گھس)|"
            r"گولی (?:چلی|لگی|مار)|حملہ ہو)"
            r"|\b(?:chor (?:andar|ghus)|chor aa gaye|goli (?:chali|lagi|maar)|hamla ho raha|"
            r"maar rahe hain)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Emergency.MEDICAL,
        re.compile(
            r"(?:مصاب بجروح|أصيب (?:بجروح|بشدة)|فاقد الوعي|ينزف|توقف عن التنفس|حادث (?:سير|مروري|خطير)|"
            r"ایکسیڈنٹ ہو|زخمی ہو|بے ہوش|سانس نہیں)"
            r"|\b(?:accident ho gaya|saans nahi|behosh ho|zakhmi ho)\b",
            re.IGNORECASE,
        ),
    ),
)

EMERGENCY_TEXT = {
    "en": {
        Emergency.FIRE: "I can't help with emergencies. Please call {fire} now.",
        Emergency.MEDICAL: "I can't help with emergencies. Please call {ambulance} for an ambulance now.",
        Emergency.VIOLENCE: "I can't help with emergencies. Please call {police} now and get to safety.",
        Emergency.GENERIC: "I can't help with emergencies. Please call {police} now.",
        Emergency.SELF_HARM: (
            "I'm sorry things are this heavy. I'm an AI and can't help with this, but please talk to "
            "someone you trust, or call {police} if you're in danger. I'm here for the business side "
            "whenever you want."
        ),
    },
    "roman_ur": {
        Emergency.FIRE: "Main emergency mein madad nahi kar sakta. Meherbani karke abhi {fire} par call karein.",
        Emergency.MEDICAL: "Main emergency mein madad nahi kar sakta. Meherbani karke abhi ambulance ke liye {ambulance} par call karein.",
        Emergency.VIOLENCE: "Main emergency mein madad nahi kar sakta. Meherbani karke abhi {police} par call karein aur mehfooz jagah par chale jayein.",
        Emergency.GENERIC: "Main emergency mein madad nahi kar sakta. Meherbani karke abhi {police} par call karein.",
        Emergency.SELF_HARM: (
            "Mujhe afsos hai ke halaat itne bhaari hain. Main AI hoon aur is mein madad nahi kar sakta, "
            "lekin kisi bharose ke insaan se baat karein, ya khatre mein hon to {police} par call karein. "
            "Business ki taraf main jab chahein haazir hoon."
        ),
    },
    "ar": {
        Emergency.FIRE: "لا أستطيع المساعدة في حالات الطوارئ. يرجى الاتصال بـ {fire} الآن.",
        Emergency.MEDICAL: "لا أستطيع المساعدة في حالات الطوارئ. يرجى الاتصال بـ {ambulance} لطلب الإسعاف الآن.",
        Emergency.VIOLENCE: "لا أستطيع المساعدة في حالات الطوارئ. يرجى الاتصال بـ {police} الآن والانتقال إلى مكان آمن.",
        Emergency.GENERIC: "لا أستطيع المساعدة في حالات الطوارئ. يرجى الاتصال بـ {police} الآن.",
        Emergency.SELF_HARM: (
            "يؤسفني أن الأمور صعبة إلى هذا الحد. أنا ذكاء اصطناعي ولا أستطيع المساعدة في هذا، "
            "لكن تحدّث مع شخص تثق به، أو اتصل بـ {police} إن كنت في خطر. أنا هنا للجانب المتعلق "
            "بعملك متى شئت."
        ),
    },
}


def emergency(text: str) -> Emergency | None:
    """The kind of emergency the message describes, or None. Self-harm is checked first."""
    said = " ".join((text or "").split())
    for kind, pattern in EMERGENCY_PATTERNS:
        if pattern.search(said):
            return kind
    return None


# Where someone in distress should call (spec X4): Rescue 1122 in Pakistan, 999, 911.
CRISIS_LINE = {"PK": "1122", "AE": "999", "CA": "911"}


def emergency_reply(kind: Emergency, country: str | None, language: str | None) -> str:
    """The fixed emergency answer with the person's local numbers (every country when unknown)."""
    table = EMERGENCY_TEXT.get(language or "en", EMERGENCY_TEXT["en"])
    template = table[kind]
    if country in NUMBERS:
        numbers = NUMBERS[country]
        police = (
            CRISIS_LINE.get(country, numbers["police"])
            if kind == Emergency.SELF_HARM
            else numbers["police"]
        )
        return template.format(
            fire=f"{numbers['fire']} (fire)",
            ambulance=numbers["ambulance"],
            police=police,
        )
    wide = f"your local emergency number ({ALL_COUNTRIES})"
    return template.format(fire=wide, ambulance=wide, police=wide)


# --- personal data (R-PRIV-01 to 03, R-PAY-02, spec 6.3) --------------------------------------


class Pii(StrEnum):
    CARD = "card"
    SECRET = "secret"
    ID = "id"
    ACCOUNT = "account"
    CONTACT = "contact"
    CHILD = "child"


@dataclass
class Redaction:
    text: str
    kinds: list[Pii] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.kinds)


PLACEHOLDER = {
    Pii.CARD: "[card number removed]",
    Pii.SECRET: "[password or code removed]",
    Pii.ID: "[ID number removed]",
    Pii.ACCOUNT: "[account number removed]",
    Pii.CONTACT: "[contact detail removed]",
    Pii.CHILD: "[child detail removed]",
}

CARD = re.compile(r"(?<![\d-])(?:\d[ -]?){13,19}(?![\d-])")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,6}(?: ?[A-Z0-9]{1,4})?\b")
ACCOUNT_LABEL = re.compile(
    r"\b(?:account|acct|a/c)\s*(?:number|no\.?|#)?\s*[:=\-]?\s*\d[\d -]{7,}\d", re.IGNORECASE
)
CNIC = re.compile(r"\b\d{5}-\d{7}-\d\b")
CNIC_LABELLED = re.compile(r"\bcnic\W{0,4}\d{13}\b", re.IGNORECASE)
EMIRATES_ID = re.compile(r"\b784-?\d{4}-?\d{7}-?\d\b")
LABELLED_ID = re.compile(
    # The label is a whole word ("sin" is not the start of "since" or "single") and the value holds
    # at least one digit ("my passport is expired" is not a passport number).
    r"\b(?:passport|sin|social insurance)\b(?: (?:no|number|#))?\W{0,4}"
    r"(?=[A-Z0-9 -]{0,13}\d)[A-Z0-9][A-Z0-9 -]{5,12}[A-Z0-9]\b",
    re.IGNORECASE,
)
# "my OTP is 4421", "password: Hunter22" (said outright), or "otp 4421" (a value with a digit).
# Not "password manager" or "pin code of the shop".
_TOKEN = r"[A-Za-z0-9@#$!%^&*._-]{3,}"
SECRET = re.compile(
    r"\b(?:password|passcode|pin|otp|cvv|cvc|one[- ]time (?:code|password))\b"
    rf"(?:\s*(?:is|was|:|=|hai|ye hai)\s*[:=]?\s*({_TOKEN})"
    rf"|\s+((?=[A-Za-z0-9@#$!%^&*._-]*\d){_TOKEN}))",
    re.IGNORECASE,
)
THIRD_PARTY = re.compile(
    r"\b(?:his|her|their|customer'?s|supplier'?s|manager'?s|staff'?s|client'?s|my (?:manager|staff|brother|"
    r"sister|wife|husband|partner|customer|supplier|accountant|driver|cashier))\b[^.\n]{0,40}?"
    r"(?:number|phone|mobile|cell|whatsapp|email|e-mail|contact)\W{0,3}(?:(?:is|are|hai)\W{0,3})?"
    r"(\+?\d[\d ()-]{7,}\d|[\w.+-]+@[\w-]+\.[\w.-]+)",
    re.IGNORECASE,
)
# A child's name ("my son Ali got ...", "my daughter named Sara") and their marks (RT21).
CHILD_NAME = re.compile(
    r"\b(?i:my|our|his|her)\s+(?i:son|daughter|child|kid|student|pupil)\s+(?i:named\s+|called\s+)?"
    r"([A-Z][a-z]{2,})\b(?=\s+(?i:got|gets|scored|is\s+in|studies|has|was|failed|passed|ki|ka)\b|[,.])"
)
CHILD_MARKS = re.compile(
    r"\b(?i:grades?|marks|score[sd]?|got|result)\b[^.\n]{0,15}?(\d{1,3}\s?%|\d{1,3}/\d{2,3}|\b[A-F][+-]?(?=\s|[.,]|$))"
)
CONTACT_CARD = re.compile(r"\s*Contact card shared:", re.IGNORECASE)
LOCATION_PIN = re.compile(r"^\s*Location shared:.*", re.IGNORECASE | re.DOTALL)
FILLER_WORDS = re.compile(r"\[[^\]]+removed\]")


def luhn(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        number = int(char)
        if index % 2:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def redact_pii(text: str) -> Redaction:
    """The text with card numbers, passwords and codes, ID and account numbers, and third parties'
    contact details taken out, and which kinds were found."""
    kinds: list[Pii] = []

    def add(kind: Pii) -> None:
        if kind not in kinds:
            kinds.append(kind)

    # A shared contact card is other people's details (R-PRIV-04, spec 6.10): none of it is kept.
    if CONTACT_CARD.match(text or ""):
        add(Pii.CONTACT)
        return Redaction("[contact card removed]", kinds)
    # A location pin is not kept as exact coordinates either; pi never asks for one.
    text = LOCATION_PIN.sub("[a location was shared]", text or "")

    def cards(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group())
        if 13 <= len(digits) <= 19 and luhn(digits):
            add(Pii.CARD)
            return PLACEHOLDER[Pii.CARD]
        return match.group()

    clean = CARD.sub(cards, text or "")

    def secret(match: re.Match[str]) -> str:
        value = match.group(1) or match.group(2)
        if value.lower() in {"code", "manager", "reset", "protected", "required"}:
            return match.group()  # "pin code of the shop", "password manager"
        add(Pii.SECRET)
        return match.group().replace(value, PLACEHOLDER[Pii.SECRET])

    clean = SECRET.sub(secret, clean)
    for pattern, kind in (
        (CNIC, Pii.ID),
        (CNIC_LABELLED, Pii.ID),
        (EMIRATES_ID, Pii.ID),
        (LABELLED_ID, Pii.ID),
        (IBAN, Pii.ACCOUNT),
        (ACCOUNT_LABEL, Pii.ACCOUNT),
    ):
        clean, count = pattern.subn(PLACEHOLDER[kind], clean)
        if count:
            add(kind)

    def third(match: re.Match[str]) -> str:
        add(Pii.CONTACT)
        return match.group().replace(match.group(1), PLACEHOLDER[Pii.CONTACT])

    clean = THIRD_PARTY.sub(third, clean)

    def child(match: re.Match[str]) -> str:
        add(Pii.CHILD)
        return match.group().replace(match.group(1), PLACEHOLDER[Pii.CHILD])

    if CHILD_NAME.search(clean):  # marks only count when the talk is about someone's child
        clean = CHILD_NAME.sub(child, clean)
        clean = CHILD_MARKS.sub(child, clean)
    return Redaction(clean, kinds)


def substantive(redacted: str) -> bool:
    """Whether anything but the removed details is left to answer (three real words or more)."""
    return len(FILLER_WORDS.sub(" ", redacted).split()) >= 3


PII_TEXT = {
    "en": {
        Pii.CARD: "Please don't send card numbers here. I never need them, and payment never happens in this chat. I've left that out of my notes.",
        Pii.SECRET: "Please don't send passwords, codes or PINs here. I never need them. I've left that out of my notes.",
        Pii.ID: "Please don't send ID numbers here. I don't need them. I've left that out of my notes.",
        Pii.ACCOUNT: "Please don't send bank account numbers here. I don't need them, and bank details only ever come on an approved quote. I've left that out of my notes.",
        Pii.CONTACT: "I don't need other people's contact details here. They can message me directly if they'd like. I've left that out of my notes.",
        Pii.CHILD: "Please don't share children's names or grades here. I only need the business problem, for example how results are tracked. I've left that out of my notes.",
    },
    "roman_ur": {
        Pii.CARD: "Meherbani karke yahan card number na bhejein. Mujhe in ki zaroorat nahi, aur payment is chat mein kabhi nahi hoti. Maine ise apne notes se nikaal diya hai.",
        Pii.SECRET: "Meherbani karke yahan password, code ya PIN na bhejein. Mujhe in ki zaroorat nahi. Maine ise apne notes se nikaal diya hai.",
        Pii.ID: "Meherbani karke yahan ID number na bhejein. Mujhe in ki zaroorat nahi. Maine ise apne notes se nikaal diya hai.",
        Pii.ACCOUNT: "Meherbani karke yahan bank account number na bhejein. Mujhe in ki zaroorat nahi, bank details sirf approved quote par aati hain. Maine ise apne notes se nikaal diya hai.",
        Pii.CONTACT: "Mujhe doosron ki contact details ki zaroorat nahi. Wo chahein to mujhe seedha message kar sakte hain. Maine ise apne notes se nikaal diya hai.",
        Pii.CHILD: "Meherbani karke yahan bachon ke naam ya marks na bhejein. Mujhe sirf business ka masla chahiye, masalan natayej ka hisaab kaise rakha jata hai. Maine ise apne notes se nikaal diya hai.",
    },
}


def pii_notice(kinds: list[Pii], told: list[str], language: str | None) -> tuple[str, list[str]]:
    """The reminder for kinds not yet reminded in this conversation, and the updated list: one reminder per
    kind per conversation, never a scolding (spec 6.3)."""
    table = PII_TEXT.get(language or "en", PII_TEXT["en"])
    fresh = [k for k in kinds if k.value not in told]
    return " ".join(table[k] for k in fresh), [*told, *(k.value for k in fresh)]


# --- advice that is not pi's to give (R-ADV-01 to 05) -----------------------------------------


class Advice(StrEnum):
    LEGAL = "legal"
    TAX = "tax"
    FINANCIAL = "financial"
    MEDICAL = "medical"
    VETERINARY = "veterinary"


ADVICE_PATTERNS: tuple[tuple[Advice, re.Pattern[str]], ...] = (
    (
        Advice.VETERINARY,
        re.compile(
            r"\b(?:(?:what|which) injection|injection (?:do|dun|doon|lagao|lagana)|"
            r"(?:cow|buffalo|goat|sheep|camel|horse|animal)s? (?:is|are) sick|sick (?:cow|buffalo|goat|animal)|"
            r"bimar (?:gaye|gai|bhains|bakri|janwar))\b",
            re.IGNORECASE,
        ),
    ),
    (
        Advice.MEDICAL,
        re.compile(
            r"\b(?:what (?:dose|dosage)|which (?:medicine|tablet|drug|antibiotic)|how many (?:tablets|pills)|"
            r"dose (?:kitni|kya)|dawai (?:kaun|konsi)|can i give (?:my |the )?(?:child|baby|kid))\b",
            re.IGNORECASE,
        ),
    ),
    (
        Advice.TAX,
        re.compile(
            r"\b(?:how much (?:vat|tax|fbr|sales tax|gst|income tax|withholding)(?: should| do| must)?|"
            r"which tax|tax (?:rate|slab|treatment)|vat (?:rate|treatment)|tax kitna|"
            r"(?:how|can) (?:do )?i (?:avoid|reduce|save on) (?:tax|vat))\b",
            re.IGNORECASE,
        ),
    ),
    (
        Advice.FINANCIAL,
        re.compile(
            r"\b(?:should i (?:take|get|apply for) (?:a |an )?(?:loan|credit|financing|mortgage)|"
            r"which bank (?:should|is best|do you)|where (?:should|do) i invest|should i invest|"
            r"worth investing|loan le lun|invest kahan)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Advice.LEGAL,
        re.compile(
            r"\b(?:is it (?:legal|illegal|allowed by law)|can i sue|sue (?:him|her|them)|"
            r"(?:fire|sack|terminate) (?:staff|him|her|them|an employee)[^.?!]{0,25}without notice|"
            r"is (?:the|my|this) contract (?:valid|legal)|legal (?:action|notice) against|qanooni|qanoon)\b|"
            r"قانوني|قانونی",
            re.IGNORECASE,
        ),
    ),
)

# Advice questions asked in Arabic, Urdu and Roman Urdu (R-ADV-01, spec 10.2 RT9).
ADVICE_PATTERNS = ADVICE_PATTERNS + (
    (
        Advice.TAX,
        re.compile(
            r"(?:كم (?:يجب|عليّ|علي) (?:أن )?أدفع ضريبة|كيف أتجنب الضريبة|نسبة (?:الضريبة|ضريبة)|"
            r"ٹیکس (?:کتنا|کیسے بچا)|کتنا ٹیکس)"
            r"|\b(?:tax kaise bach\w*|tax kitna (?:dun|doon|dena)|tax bachane ka)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Advice.MEDICAL,
        re.compile(
            r"(?:ما (?:هي )?الجرعة|أي دواء|كم حبة|کون سی دوا|دوا کتنی)"
            r"|\b(?:konsi dawai|kaun si dawai|dawai kitni)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Advice.FINANCIAL,
        re.compile(
            r"(?:هل (?:آخذ|اخذ) قرضًا|هل أستثمر|هل استثمر|قرض لینا چاہیے|سرمایہ کاری کروں)"
            r"|\b(?:loan lena chahiye|loan le lun|loan lun ya nahi|invest karun)\b",
            re.IGNORECASE,
        ),
    ),
)

ADVICE_WHO = {
    "ar": {
        Advice.LEGAL: "محامٍ",
        Advice.TAX: "محاسب",
        Advice.FINANCIAL: "مستشار مالي مؤهل",
        Advice.MEDICAL: "طبيب أو صيدلي",
        Advice.VETERINARY: "طبيب بيطري",
    },
    "en": {
        Advice.LEGAL: "a lawyer",
        Advice.TAX: "an accountant",
        Advice.FINANCIAL: "a qualified financial adviser",
        Advice.MEDICAL: "a doctor or pharmacist",
        Advice.VETERINARY: "a vet",
    },
    "roman_ur": {
        Advice.LEGAL: "wakeel",
        Advice.TAX: "accountant",
        Advice.FINANCIAL: "mustanad financial adviser",
        Advice.MEDICAL: "doctor ya pharmacist",
        Advice.VETERINARY: "veterinary doctor",
    },
}
ADVICE_TEXT = {
    "ar": "لا أستطيع تقديم نصيحة {kind}، و{who} هو الشخص المناسب لذلك. يمكنني تسجيلها كمشكلة في عملك. هل أفعل ذلك؟",
    "en": "I can't give {kind} advice, and {who} is the right person for that. I can note it as a problem in your business. Want me to?",
    "roman_ur": "Main {kind} mashwara nahi de sakta, is ke liye {who} sahi insaan hai. Main ise aap ke business ki ek problem ke taur par note kar sakta hoon. Kya karun?",
}
ADVICE_WORD = {
    "ar": {
        Advice.LEGAL: "قانونية",
        Advice.TAX: "ضريبية",
        Advice.FINANCIAL: "مالية",
        Advice.MEDICAL: "طبية",
        Advice.VETERINARY: "بيطرية",
    },
    "roman_ur": {
        Advice.LEGAL: "qanooni",
        Advice.TAX: "tax ka",
        Advice.FINANCIAL: "maali",
        Advice.MEDICAL: "tibbi",
        Advice.VETERINARY: "janwaron ke ilaaj ka",
    },
}


def advice_asked(text: str) -> Advice | None:
    said = " ".join((text or "").split())
    for kind, pattern in ADVICE_PATTERNS:
        if pattern.search(said):
            return kind
    return None


def advice_reply(kind: Advice, language: str | None) -> str:
    lang = language if language in ADVICE_TEXT else "en"
    word = ADVICE_WORD.get(lang, {}).get(kind, kind.value)
    return ADVICE_TEXT[lang].format(kind=word, who=ADVICE_WHO[lang][kind])


# R-DISC-04 (spec 6.6): when a person hands the chat back, pi says who it is again, once.
HANDBACK_TEXT = {
    "en": "Thanks. I'm pi again, the AI from Workzap. Shall we carry on?",
    "roman_ur": "Shukriya. Main phir se pi hoon, Workzap ka AI. Kya baat jari rakhein?",
    "ar": "شكرًا. أنا pi مرة أخرى، الذكاء الاصطناعي من Workzap. هل نواصل؟",
}


def handback_reply(language: str | None) -> str:
    return HANDBACK_TEXT.get(language or "en", HANDBACK_TEXT["en"])


# R-LANG-08: religious and cultural courtesy, one line, then back to the business.
GREETING_TEXT = {
    "salam": {
        "en": "Wa alaikum assalam. What's going wrong in your business?",
        "roman_ur": "Wa alaikum assalam. Aap ke business mein kya masla chal raha hai?",
        "ar": "وعليكم السلام. ما الذي يعيق عملك؟",
    },
    "festival": {
        "en": "Eid Mubarak to you too. What's going wrong in your business?",
        "roman_ur": "Aap ko bhi Eid Mubarak. Aap ke business mein kya masla chal raha hai?",
        "ar": "عيد مبارك لك أيضًا. ما الذي يعيق عملك؟",
    },
}
# R-FUP-02: after "stop" pi confirms once and then writes no more.
OPT_OUT_TEXT = {
    "en": "Understood. I won't message you again. If you ever want to talk, just write here.",
    "roman_ur": "Theek hai. Main dobara paigham nahi bhejunga. Kabhi baat karni ho to yahin likh dein.",
    "ar": "حسنًا. لن أرسل لك رسائل بعد الآن. إن أردت التحدث يومًا فاكتب هنا.",
}


def greeting_reply(kind: str, language: str | None) -> str:
    table = GREETING_TEXT[kind]
    return table.get(language or "en", table["en"])


def opt_out_reply(language: str | None) -> str:
    return OPT_OUT_TEXT.get(language or "en", OPT_OUT_TEXT["en"])


# --- who pi is (R-DISC-02, R-DISC-03, R-META-01, spec 6.1) ------------------------------------


class Identity(StrEnum):
    PERSON = "person"
    GENDER = "gender"
    SCAM = "scam"
    META = "meta"
    MODEL = "model"
    RULES = "rules"
    COMPANY = "company"
    OFFER = "offer"


IDENTITY_PATTERNS: tuple[tuple[Identity, re.Pattern[str]], ...] = (
    (
        Identity.OFFER,
        re.compile(
            r"\b(?:what (?:do|does) (?:you|workzap) (?:sell|offer|do)|what (?:is|are) (?:workzap|your)"
            r"(?:'s)? (?:product|service|offer)s?|aap kya (?:bechte|karte|dete)|kya bechte ho)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Identity.RULES,
        re.compile(
            r"\b(?:system prompt|show me your (?:prompt|rules|instructions)|your (?:prompt|instructions)|"
            r"reveal your (?:rules|prompt))\b",
            re.IGNORECASE,
        ),
    ),
    (
        Identity.META,
        re.compile(
            r"\b(?:are you (?:whatsapp|meta)|is this (?:whatsapp|meta)(?: ai)?|meta ai\b|made by (?:whatsapp|meta))",
            re.IGNORECASE,
        ),
    ),
    (
        Identity.MODEL,
        re.compile(
            r"\b(?:are you (?:chat ?gpt|gpt|claude|gemini|openai)|which (?:ai )?model|what model|"
            r"what ai are you|powered by)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Identity.SCAM,
        re.compile(
            r"\b(?:is this (?:a )?(?:scam|fraud|fake|legit|real)|are you (?:a )?(?:scam|fraud|fake)|"
            r"can i trust you|scam hai|dhokha)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Identity.GENDER,
        re.compile(
            r"\b(?:what(?:'s| is) your name|are you (?:a )?(?:guy|girl|man|woman|male|female)|boy or girl|"
            r"aap ka naam|tumhara naam)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Identity.COMPANY,
        re.compile(
            r"\b(?:who owns workzap|where is (?:your|the|workzap'?s) office|workzap(?:'s)? (?:office|address|owner|ceo)|"
            r"who (?:is|are) (?:the )?(?:owner|ceo|founder)s? of workzap)\b",
            re.IGNORECASE,
        ),
    ),
)
IDENTITY_TEXT = {
    "en": {
        Identity.PERSON: "I'm an AI, not a person. I'm pi, from Workzap.",
        Identity.GENDER: "I'm pi, an AI from Workzap. I don't have a gender.",
        Identity.SCAM: "Fair question. I'm an AI from Workzap. I never ask for payment, card numbers or passwords here, and you never have to buy anything. More at workzap.ai/pi/trust.",
        Identity.META: "No. I'm made by Workzap and chat through WhatsApp's business platform. I'm not made, run or endorsed by WhatsApp or Meta.",
        Identity.MODEL: "I'm pi, Workzap's AI. I'm here to note and sort problems in your business.",
        Identity.RULES: "I can tell you how I work: I note and sort problems, I never take payment here, and you decide on any quote. The full detail is at workzap.ai/pi/how-it-works.",
        Identity.COMPANY: "I can pass that question to the Workzap team.",
        Identity.OFFER: "Workzap makes software for finding problems and solving them. I'm not here to sell anything: I note what's getting in the way of yours, and if you want, Workzap can then prepare a solution document. What's the biggest thing right now?",
    },
    "roman_ur": {
        Identity.PERSON: "Main AI hoon, insaan nahi. Main pi hoon, Workzap ki taraf se.",
        Identity.GENDER: "Main pi hoon, Workzap ka AI. Meri koi jins nahi.",
        Identity.SCAM: "Jayez sawal hai. Main Workzap ka AI hoon. Main yahan kabhi payment, card number ya password nahi maangta, aur aap par kuch kharidna zaroori nahi. Mazeed workzap.ai/pi/trust par.",
        Identity.META: "Nahi. Mujhe Workzap ne banaya hai aur main WhatsApp ke business platform se chat karta hoon. Mujhe WhatsApp ya Meta ne nahi banaya, na chalata hai, na endorse karta hai.",
        Identity.MODEL: "Main pi hoon, Workzap ka AI. Main aap ke business ke masail note aur sort karne ke liye hoon.",
        Identity.RULES: "Main bata sakta hoon main kaise kaam karta hoon: masail note aur sort karta hoon, yahan kabhi payment nahi leta, aur quote par faisla aap ka hota hai. Poori tafseel workzap.ai/pi/how-it-works par hai.",
        Identity.COMPANY: "Ye sawal main Workzap ki team tak pahuncha sakta hoon.",
        Identity.OFFER: "Workzap masail dhoondne aur hal karne ka software banata hai. Main kuch bechne nahi aaya: main aap ke business ki rukawat note karta hoon, aur aap chahein to Workzap phir solution document bana sakta hai. Abhi sab se bada masla kya hai?",
    },
    "ar": {
        Identity.PERSON: "أنا ذكاء اصطناعي ولست شخصًا. أنا pi من Workzap.",
        Identity.GENDER: "أنا pi، ذكاء اصطناعي من Workzap. ليس لي جنس.",
        Identity.SCAM: "سؤال وجيه. أنا ذكاء اصطناعي من Workzap. لا أطلب هنا أبدًا دفعًا أو أرقام بطاقات أو كلمات مرور، ولا يجب عليك شراء أي شيء. المزيد على workzap.ai/pi/trust.",
        Identity.META: "لا. صنعتني Workzap وأتحدث عبر منصة واتساب للأعمال. لم تصنعني واتساب أو ميتا ولا تديرني ولا تدعمني.",
        Identity.MODEL: "أنا pi، ذكاء Workzap الاصطناعي. أنا هنا لأسجّل مشكلات عملك وأرتّبها.",
        Identity.RULES: "يمكنني أن أشرح كيف أعمل: أسجّل المشكلات وأرتّبها، ولا أقبل أي دفع هنا، والقرار في أي عرض سعر لك. التفاصيل الكاملة على workzap.ai/pi/how-it-works.",
        Identity.COMPANY: "يمكنني نقل هذا السؤال إلى فريق Workzap.",
        Identity.OFFER: "تصنع Workzap برمجيات لاكتشاف المشكلات وحلّها. لست هنا لأبيع شيئًا: أسجّل ما يعيق عملك، وإن أردت يمكن لـ Workzap بعدها إعداد وثيقة حل. ما أكبر شيء الآن؟",
    },
}


def identity_asked(text: str, asks_if_ai: re.Pattern[str]) -> Identity | None:
    """Which "who are you" question this is. `asks_if_ai` is the linter's pattern, so the check that a
    reply says "AI" and the check that decides pi must say it can never disagree."""
    said = " ".join((text or "").split())
    for kind, pattern in IDENTITY_PATTERNS:
        if pattern.search(said):
            return kind
    if asks_if_ai.search(said):
        return Identity.PERSON
    return None


def identity_reply(kind: Identity, language: str | None) -> str:
    table = IDENTITY_TEXT.get(language or "en", IDENTITY_TEXT["en"])
    return table[kind]


# --- what pi will not do (R-PRIV-05, R-PRIV-06, R-ADV-04, spec 10.2 RT14-RT16, RT20, RT22, RT24) ---


class Boundary(StrEnum):
    DELETION = "deletion"
    POLITICS = "politics"
    COMPETITOR = "competitor"
    OUTCOME = "outcome"
    FRAUD = "fraud"
    THIRD_PARTY = "third_party"
    BANK_CHANGE = "bank_change"
    OFF_TOPIC = "off_topic"
    COMPLAINT = "complaint"
    ILLEGAL = "illegal"
    REFUND = "refund"
    BANK_ASK = "bank_ask"  # M2: asked for Workzap's bank details before any approval
    BANK_ASK_APPROVED = "bank_ask_approved"  # M3: the same, after the quote was approved
    OTHER_PAY = "other_pay"  # M6: card, JazzCash, Easypaisa, Apple Pay
    DISCOUNT = "discount"  # M7
    PAY_FOR_ME = "pay_for_me"  # M10: pay my supplier
    PRODUCT_REC = "product_rec"  # A5: which POS should I buy
    DECIDE_FOR_ME = "decide_for_me"  # A8
    RIVAL = "rival"  # A6: what do you think of my competitor
    WRONG_NUMBER = "wrong_number"  # 6.9
    MEMORY_ASK = "memory_ask"  # R-MEM-05: what does pi keep
    QUOTE_ONLY = "quote_only"  # R-QUOTE-09: a quote without the document


BOUNDARY_PATTERNS: tuple[tuple[Boundary, re.Pattern[str]], ...] = (
    (
        # A refund or dispute with Workzap itself (R-PAY-07), not refunds in the person's own
        # business, which are a problem to note.
        Boundary.REFUND,
        re.compile(
            r"\b(?:i (?:want|need|demand|would like) (?:a |my |the )?(?:refund|money back)"
            r"|(?:give|send) (?:me )?(?:a |my )?(?:refund|money back)"
            r"|refund (?:me|my (?:money|payment|transfer))"
            r"|(?:dispute|contest) (?:the |this |my )?(?:payment|charge|invoice|transfer)"
            r"|charge ?back|apne paise wapis|paise wapis (?:do|karo|chahiye)|refund chahiye)\b",
            re.IGNORECASE,
        ),
    ),
    (
        # A complaint about pi or Workzap (not about a cashier or a supplier): R-COMPL-01.
        Boundary.COMPLAINT,
        re.compile(
            r"\bi (?:want|would like) to complain\b"
            r"|\b(?:complaint|complain|shikayat)\b[^.?!\n]{0,30}\b(?:about|against|ki|par)?\s*"
            r"(?:pi|workzap|your (?:service|team|company|bot)|this (?:bot|service|chat))\b"
            r"|\b(?:not happy|unhappy|disappointed) with (?:pi|workzap|your (?:service|team|bot)|"
            r"this (?:bot|service))\b|\bworkzap ki shikayat\b|\breport (?:you|this bot)\b",
            re.IGNORECASE,
        ),
    ),
    (
        # Something illegal that pi must not help with and must not note as a problem to solve.
        Boundary.ILLEGAL,
        re.compile(
            r"\b(?:track|spy on|monitor) (?:my |our )?(?:staff|employees|workers|wife|husband)\b"
            r"[^.?!\n]{0,20}\b(?:secretly|covertly|without (?:them|their) knowing)\b"
            r"|\bread (?:their|my staff'?s?|employees') (?:whatsapp|messages|chats)\b"
            r"|\bhack\b[^.?!\n]{0,20}\b(?:account|whatsapp|phone)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.DELETION,
        re.compile(
            r"\b(?:delete (?:everything|all|my (?:data|chats?|records?|information))|"
            r"erase (?:everything|all|my (?:data|chats?|records?))|forget (?:everything|all about me)|"
            r"remove (?:all )?my (?:data|information)|mera (?:sab )?(?:data|record) (?:delete|mita)|"
            r"sab (?:kuch )?delete kar do)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.BANK_CHANGE,
        re.compile(
            r"\b(?:(?:new|changed?|different|updated?) (?:bank|account|iban)(?: details| account| number)?"
            r"[^.?!]{0,40}(?:workzap|you|your)|workzap[^.?!]{0,30}(?:changed|new) (?:their )?(?:bank|account|iban)|"
            r"send (?:me )?(?:the )?new (?:iban|account|bank)|bank (?:details|account) (?:have|has) changed)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.OFF_TOPIC,
        re.compile(
            r"\b(?:(?:help|write|do) (?:me )?(?:with )?(?:my |an? |the )?(?:homework|assignment|essay|poem|"
            r"python|javascript|code|script|resume|cv)\b|tell me a (?:joke|story)|write (?:me )?(?:a |an )?"
            r"(?:poem|song|joke|story)|solve this (?:equation|math|problem set))",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.FRAUD,
        re.compile(
            r"\b(?:(?:fake|false|bogus|duplicate|double) (?:invoices?|bills?|receipts?|vouchers?)|"
            r"(?:make|create|issue|print) (?:\w+ )?(?:fake|false) (?:invoices?|bills?|receipts?)|"
            r"jali (?:bill|invoice|receipt)|tax chori|evade tax|hide (?:income|sales) from)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.THIRD_PARTY,
        re.compile(
            r"\b(?:send me (?:the )?(?:chats?|messages|conversations?) (?:of|with|from) (?:my|our|his|her)?\s*\w+|"
            r"show me (?:the )?(?:chats?|messages) (?:of|from|with) (?:my|our|his|her)?\s*\w+|"
            r"what did (?:my|our) (?:manager|cashier|staff|employee|partner|wife|husband)[^.?!]{0,20}(?:say|tell|write))\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.OUTCOME,
        re.compile(
            r"\b(?:say|promise|guarantee|confirm|tell me)[^.?!]{0,30}(?:will|would)?[^.?!]{0,20}"
            r"(?:definitely|certainly|for sure|guaranteed?|100%)[^.?!]{0,30}"
            r"(?:increase|boost|double|grow|improve|raise|fix)\b|"
            r"\b(?:guarantee|promise) (?:me )?(?:more )?(?:sales|profit|results|growth)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.COMPETITOR,
        re.compile(
            r"\b(?:are you (?:any )?(?:better|cheaper|worse) than|is (?:workzap|pi) (?:better|cheaper) than|"
            r"compare (?:yourself|workzap|you) (?:to|with)|"
            r"workzap (?:vs|versus)|(?:vs|versus) workzap|why (?:you|workzap) (?:and )?not)\b"
            r"[^.?!]{0,40}",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.POLITICS,
        re.compile(
            r"\b(?:what do you think (?:about|of) (?:the )?(?:\w+ ){0,2}(?:party|government|election|"
            r"minister|prime minister|president|imran|nawaz|zardari|modi|trump|biden)|"
            r"who (?:should|will) i vote|which party (?:is|should)|your (?:political|religious) "
            r"(?:view|opinion|views|opinions)|siyasi (?:party|jamaat)|vote (?:kis|kisko))\b",
            re.IGNORECASE,
        ),
    ),
)

# More of spec 6.2 and 6.4 (M2, M3, M6, M7, M10, A5, A6, A8) and 6.9 (wrong number).
BOUNDARY_PATTERNS = BOUNDARY_PATTERNS + (
    (
        Boundary.BANK_ASK,
        re.compile(
            r"\b(?:send|give|share|tell)\s+(?:me\s+)?(?:your|the|workzap'?s)\s+(?:bank|account|iban)"
            r"(?:\s+(?:details|number|account))?\b|\bwhat(?:'s| is) your (?:bank|iban|account number)\b"
            r"|\b(?:apna|aap ka|workzap ka)\s+(?:bank|account)\s+(?:number|details|tafseel)\s+(?:bhejein|bhej do|batao|dein)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.OTHER_PAY,
        re.compile(
            r"\b(?:can i|could i|may i|how (?:do|can) i)\s+pay\s+(?:by|with|through|via|using|in)\s+"
            r"(?:card|credit card|debit card|jazz ?cash|easy ?paisa|apple pay|google pay|paypal|cash|cheque|check|crypto)\b"
            r"|\b(?:jazz ?cash|easy ?paisa|card|cash)\s+(?:se|par|pe)\s+(?:payment|pay)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.DISCOUNT,
        re.compile(
            r"\b(?:give me|can i get|can you give me|i want|i need)\s+(?:a\s+)?(?:discount|better price|lower price)\b"
            r"|\b(?:reduce|lower|cut)\s+(?:the\s+)?(?:price|quote|cost)\b|\bdiscount\s+(?:do|chahiye|milega|dein)\b"
            r"|\b(?:price|rate|quote)\s+kam\s+(?:karo|kar do|karein)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.PAY_FOR_ME,
        re.compile(
            r"\b(?:pay|send money to|transfer (?:money )?to)\s+my\s+(?:supplier|vendor|staff|employees?|landlord)\b"
            r"|\bmere\s+(?:supplier|vendor)\s+ko\s+(?:pay|paise|payment)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.PRODUCT_REC,
        re.compile(
            r"\bwhich\s+(?:pos|software|app|accounting software|erp|crm|laptop|printer|system|tool)\s+"
            r"(?:should|do you recommend|is best|to)\b|\b(?:recommend|suggest)\s+(?:me\s+)?(?:a|an|some)\s+"
            r"(?:pos|software|erp|crm|app)\b|\bkon\s*sa\s+(?:pos|software|app)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.DECIDE_FOR_ME,
        re.compile(
            r"\bwhat would you (?:do|choose)\s+(?:if you were me|in my (?:place|shoes|position))\b"
            r"|\bif you were me\b|\baap\s+meri\s+jagah\s+hote\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.RIVAL,
        re.compile(
            r"\b(?:what do you think (?:of|about)|your (?:opinion|view|thoughts) (?:on|of|about)|"
            r"is it true that)\s+(?:my|our)\s+(?:competitor|rival)s?\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.WRONG_NUMBER,
        re.compile(
            r"\byou(?:'ve| have| got)?\s+(?:the\s+)?wrong number\b|^\W*(?:sorry\W+)?wrong number\W*$"
            r"|\bgalat number\b|\bwho is this\W+i didn'?t (?:ask|message|text)\b",
            re.IGNORECASE,
        ),
    ),
)


BOUNDARY_PATTERNS = BOUNDARY_PATTERNS + (
    (
        Boundary.MEMORY_ASK,
        re.compile(
            r"\b(?:what|which)\s+(?:data|information|details|records?)\s+(?:do|does|will)\s+(?:you|pi)\s+"
            r"(?:keep|store|save|have|hold|know)\b|\bwhat do you (?:keep|store|save|remember) about me\b"
            r"|\bkya\s+(?:data|record|information)\s+(?:rakhte|rakhta|save|store)\b|\bmera\s+kya\s+(?:data|record)\b",
            re.IGNORECASE,
        ),
    ),
)


BOUNDARY_PATTERNS = BOUNDARY_PATTERNS + (
    (
        Boundary.QUOTE_ONLY,
        re.compile(
            r"\b(?:just|only|sirf)\s+(?:the\s+|a\s+)?(?:quote|quotation|price)\b(?!\s+and\b)"
            r"|\bquote\s+(?:without|bina|baghair)\s+(?:the\s+)?(?:document|doc)\b"
            r"|\bwithout\s+the\s+(?:solution\s+)?document\b",
            re.IGNORECASE,
        ),
    ),
)

BOUNDARY_TEXT = {
    "en": {
        Boundary.DELETION: "I've passed your request to delete your information to the Workzap team. They'll confirm here once it's done, and I won't note anything new in the meantime.",
        Boundary.POLITICS: "I stay out of politics and opinions. I'm here to note what's getting in the way of your business. What's the biggest thing right now?",
        Boundary.COMPETITOR: "I don't compare Workzap with other companies. I'm here to note what's getting in the way of your business. What's the biggest thing right now?",
        Boundary.OUTCOME: "I can't promise results. I can note the problem and Workzap can describe what it would do about it. What's the problem?",
        Boundary.FRAUD: "I can't help with false invoices or hiding income. If tracking real invoices is hard in your business, I can note that as a problem. Want me to?",
        Boundary.THIRD_PARTY: "I can't share anyone else's chats. I only keep what you tell me in this chat. What would you like to note about your business?",
        Boundary.BANK_CHANGE: "I can't confirm any bank details in this chat. Payment details are only on your approved quote, and I've flagged your message to the Workzap team to check.",
        Boundary.OFF_TOPIC: "That's outside what I'm for. I'm here to note what's getting in the way of your business. What's the biggest thing right now?",
        Boundary.COMPLAINT: "Thanks for telling me. I've passed this to the Workzap team.",
        Boundary.ILLEGAL: "I can't help with that. I'm here for problems in your business.",
        Boundary.REFUND: "I can't decide refunds or payment disputes. I've passed this to the Workzap team with your message, and they'll reply here.",
        Boundary.BANK_ASK: "Bank details come on an approved quote. Nothing is owed until you approve one.",
        Boundary.BANK_ASK_APPROVED: "They're on your approved quote. I can resend the quote if you need it.",
        Boundary.OTHER_PAY: "Payment is by bank transfer, with details on your approved quote. If you need another way, I'll ask the Workzap team.",
        Boundary.DISCOUNT: "I can't change the quote, but I'll pass the request to Workzap. They'll reply here.",
        Boundary.PAY_FOR_ME: "I can't make payments. I can note it if paying suppliers is a problem in your business.",
        Boundary.PRODUCT_REC: "I don't recommend products. I can note what's wrong with your current setup so Workzap can look at it.",
        Boundary.DECIDE_FOR_ME: "That's your call: I don't decide for you. I can show you what you've told me, sorted, so it's easier to see.",
        Boundary.RIVAL: "I don't comment on other businesses. What's going wrong on your side?",
        Boundary.WRONG_NUMBER: "I think you may have the wrong number. I'm pi, an AI from Workzap, here for business problems.",
        Boundary.MEMORY_ASK: "I keep the problems you've told me, the details you added, and any documents and quotes. You can ask me to delete them.",
        Boundary.QUOTE_ONLY: "The quote is for building what's in the document, so they come together. I can only ask Workzap for both.",
    },
    "roman_ur": {
        Boundary.DELETION: "Aap ka data delete karne ki darkhwast maine Workzap ki team ko bhej di hai. Wo yahan tasdeeq kar dein ge, aur tab tak main kuch naya note nahi karunga.",
        Boundary.POLITICS: "Main siyasat aur rai se door rehta hoon. Main aap ke business mein rukawat note karne ke liye hoon. Abhi sab se bada masla kya hai?",
        Boundary.COMPETITOR: "Main Workzap ka doosri companies se muqabla nahi karta. Main aap ke business mein rukawat note karne ke liye hoon. Abhi sab se bada masla kya hai?",
        Boundary.OUTCOME: "Main nateejon ka wada nahi kar sakta. Main masla note kar sakta hoon aur Workzap bata sakta hai wo kya karega. Masla kya hai?",
        Boundary.FRAUD: "Main jali invoice ya aamdani chupane mein madad nahi kar sakta. Agar asli invoices ka hisaab rakhna mushkil hai to ise masla note kar sakta hoon. Kya karun?",
        Boundary.THIRD_PARTY: "Main kisi aur ki chat share nahi kar sakta. Main sirf wo rakhta hoon jo aap is chat mein batate hain. Business ke baare mein kya note karun?",
        Boundary.BANK_CHANGE: "Main is chat mein bank details ki tasdeeq nahi kar sakta. Payment ki tafseel sirf aap ke approved quote par hoti hai, aur maine aap ka paigham Workzap ki team ko check ke liye bhej diya hai.",
        Boundary.OFF_TOPIC: "Ye mere dayre se bahar hai. Main aap ke business mein rukawat note karne ke liye hoon. Abhi sab se bada masla kya hai?",
        Boundary.COMPLAINT: "Batane ka shukriya. Maine ye Workzap ki team tak pahuncha diya hai.",
        Boundary.ILLEGAL: "Main is mein madad nahi kar sakta. Main aap ke business ke masail ke liye hoon.",
        Boundary.REFUND: "Refund ya payment ke jhagde ka faisla main nahi kar sakta. Maine ye Workzap ki team ko aap ke paigham ke saath bhej diya hai, wo yahin jawab dein ge.",
        Boundary.BANK_ASK: "Bank ki tafseel approved quote par hoti hai. Jab tak aap approve na karein, kuch wajib nahi.",
        Boundary.BANK_ASK_APPROVED: "Wo aap ke approved quote par hain. Zaroorat ho to quote dobara bheja ja sakta hai.",
        Boundary.OTHER_PAY: "Payment bank transfer se hoti hai, tafseel aap ke approved quote par hai. Koi aur tareeqa chahiye to Workzap ki team se poochha ja sakta hai.",
        Boundary.DISCOUNT: "Quote badalna mere ikhtiyar mein nahi; ye darkhwast Workzap tak pahuncha di jayegi. Wo yahin jawab dein ge.",
        Boundary.PAY_FOR_ME: "Payments mere bas mein nahi. Agar suppliers ko payment karna aap ke business ka masla hai to ise note kiya ja sakta hai.",
        Boundary.PRODUCT_REC: "Main products recommend nahi karta. Aap ke mojooda setup mein kya masla hai, ye note kiya ja sakta hai taake Workzap dekh sake.",
        Boundary.DECIDE_FOR_ME: "Ye aap ka faisla hai: main aap ke liye faisla nahi karta. Aap ne jo bataya wo sort karke dikha sakta hoon taake dekhna aasan ho.",
        Boundary.RIVAL: "Main doosre businesses par raaye nahi deta. Aap ki taraf kya masla chal raha hai?",
        Boundary.WRONG_NUMBER: "Lagta hai aap ne galat number mila diya hai. Main pi hoon, Workzap ka AI, business ke masail ke liye.",
        Boundary.MEMORY_ASK: "Main aap ke batae hue masail, aap ki di hui tafseel, aur documents aur quotes rakhta hoon. Aap inhein delete karne ko keh sakte hain.",
        Boundary.QUOTE_ONLY: "Quote us cheez ka hota hai jo document mein likhi hai, isliye dono saath aate hain. Dono hi Workzap se manga ja sakte hain.",
    },
    "ar": {
        Boundary.DELETION: "لقد أرسلت طلب حذف معلوماتك إلى فريق Workzap. سيؤكدون هنا عند الانتهاء، ولن أسجّل أي شيء جديد في هذه الأثناء.",
        Boundary.POLITICS: "أبتعد عن السياسة والآراء. أنا هنا لأسجّل ما يعيق عملك. ما أكبر شيء الآن؟",
        Boundary.COMPETITOR: "لا أقارن Workzap بشركات أخرى. أنا هنا لأسجّل ما يعيق عملك. ما أكبر شيء الآن؟",
        Boundary.OUTCOME: "لا أستطيع وعدك بنتائج. يمكنني تسجيل المشكلة ويمكن لـ Workzap أن تشرح ما ستفعله حيالها. ما المشكلة؟",
        Boundary.FRAUD: "لا أستطيع المساعدة في فواتير مزورة أو إخفاء الدخل. إن كان تتبع الفواتير الحقيقية صعبًا في عملك فيمكنني تسجيل ذلك كمشكلة. هل أفعل؟",
        Boundary.THIRD_PARTY: "لا أستطيع مشاركة محادثات أي شخص آخر. أحتفظ فقط بما تخبرني به في هذه المحادثة. ماذا تريد أن أسجّل عن عملك؟",
        Boundary.BANK_CHANGE: "لا أستطيع تأكيد أي تفاصيل بنكية في هذه المحادثة. تفاصيل الدفع موجودة فقط في عرض السعر المعتمد، وقد أرسلت رسالتك إلى فريق Workzap للتحقق.",
        Boundary.OFF_TOPIC: "هذا خارج ما أقوم به. أنا هنا لأسجّل ما يعيق عملك. ما أكبر شيء الآن؟",
        Boundary.COMPLAINT: "شكرًا لإخباري. لقد أحلت هذا إلى فريق Workzap.",
        Boundary.ILLEGAL: "لا أستطيع المساعدة في ذلك. أنا هنا لمشكلات عملك.",
        Boundary.REFUND: "لا أستطيع البت في الاسترداد أو نزاعات الدفع. لقد أحلت هذا إلى فريق Workzap مع رسالتك وسيردون هنا.",
        Boundary.BANK_ASK: "تفاصيل الحساب البنكي تأتي مع عرض السعر المعتمد. لا يترتب عليك شيء حتى توافق على عرض.",
        Boundary.BANK_ASK_APPROVED: "هي موجودة في عرض السعر المعتمد. يمكنني إعادة إرسال العرض إن احتجت.",
        Boundary.OTHER_PAY: "الدفع عن طريق التحويل البنكي وتفاصيله في عرض السعر المعتمد. إن احتجت طريقة أخرى فسأسأل فريق Workzap.",
        Boundary.DISCOUNT: "لا أستطيع تغيير عرض السعر، لكنني سأنقل الطلب إلى Workzap وسيردون هنا.",
        Boundary.PAY_FOR_ME: "لا أستطيع إجراء المدفوعات. يمكنني تسجيل ذلك إن كان دفع الموردين مشكلة في عملك.",
        Boundary.PRODUCT_REC: "لا أوصي بمنتجات. يمكنني تسجيل ما يعيق إعدادك الحالي ليطّلع عليه فريق Workzap.",
        Boundary.DECIDE_FOR_ME: "القرار قرارك ولا أقرر عنك. يمكنني أن أريك ما أخبرتني به مرتبًا ليسهل عليك رؤيته.",
        Boundary.RIVAL: "لا أعلّق على أعمال الآخرين. ما الذي يسير بشكل خاطئ من جانبك؟",
        Boundary.WRONG_NUMBER: "أظن أن الرقم خاطئ. أنا pi، ذكاء اصطناعي من Workzap، هنا لمشكلات الأعمال.",
        Boundary.MEMORY_ASK: "أحتفظ بالمشكلات التي أخبرتني بها والتفاصيل التي أضفتها وأي مستندات وعروض أسعار. يمكنك أن تطلب مني حذفها.",
        Boundary.QUOTE_ONLY: "عرض السعر خاص ببناء ما في المستند، لذلك يأتيان معًا. يمكنني طلب الاثنين من Workzap.",
    },
}


def boundary_asked(text: str) -> Boundary | None:
    said = " ".join((text or "").split())
    for kind, pattern in BOUNDARY_PATTERNS:
        if pattern.search(said):
            return kind
    return None


def boundary_reply(kind: Boundary, language: str | None) -> str:
    return BOUNDARY_TEXT.get(language or "en", BOUNDARY_TEXT["en"])[kind]


# --- enquiries that are not problems: pi is Workzap's front door (R-ROUTE-01, spec 6.9) ----------


class Enquiry(StrEnum):
    DEMO = "demo_request"
    JOBS = "jobs"
    VENDOR = "vendor"
    PARTNERSHIP = "partnership"
    PRESS = "press"


ENQUIRY_PATTERNS: tuple[tuple[Enquiry, re.Pattern[str]], ...] = (
    (
        Enquiry.PRESS,
        re.compile(
            r"\b(?:journalist|press (?:release|enquiry|inquiry)|media (?:enquiry|inquiry|request)|"
            r"interview (?:with|you|workzap)|write (?:an )?article about (?:you|workzap|nori))\b",
            re.IGNORECASE,
        ),
    ),
    (
        Enquiry.DEMO,
        re.compile(
            r"\b(?:(?:book|arrange|schedule|request|want|need|get)(?: me)?(?: a| an)? (?:nori )?demo|"
            r"demo (?:of|for) nori|nori demo)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Enquiry.JOBS,
        re.compile(
            r"\b(?:job application|apply for (?:a |the )?(?:job|position|role)|are you hiring|"
            r"any (?:vacancy|vacancies|openings)|attached (?:is )?my (?:cv|resume)|my (?:cv|resume) (?:is|for)|"
            r"looking for (?:a )?job)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Enquiry.PARTNERSHIP,
        re.compile(
            r"\b(?:partner(?:ship)? with (?:you|workzap|nori)|reseller|resell (?:nori|workzap)|"
            r"become (?:a )?(?:partner|distributor)|collaborat\w+ with (?:you|workzap))\b",
            re.IGNORECASE,
        ),
    ),
    (
        Enquiry.VENDOR,
        re.compile(
            r"\b(?:we (?:can )?(?:supply|offer|provide) (?:you|workzap)|our (?:company|agency) (?:offers|provides|supplies)|"
            r"offer(?:ing)? you our (?:services|products)|we are (?:a )?(?:supplier|vendor|agency) (?:of|for|that))\b",
            re.IGNORECASE,
        ),
    ),
)
ENQUIRY_TEXT = {
    "en": {
        Enquiry.DEMO: "I'll pass that to the Workzap team. How many shops do you have, roughly?",
        Enquiry.JOBS: "Thanks. I'll pass your interest to the Workzap team. Please don't send ID documents here.",
        Enquiry.VENDOR: "Thanks. I'll pass it to the Workzap team.",
        Enquiry.PARTNERSHIP: "Thanks. I'll pass that to the Workzap team. Which company is this, and in which country?",
        Enquiry.PRESS: "I'll pass that to the Workzap team. I can't give quotes or statements.",
    },
    "roman_ur": {
        Enquiry.DEMO: "Main ye Workzap ki team tak pahuncha deta hoon. Aap ki roughly kitni dukanein hain?",
        Enquiry.JOBS: "Shukriya. Main aap ki dilchaspi Workzap ki team tak pahuncha deta hoon. Meherbani karke yahan ID documents na bhejein.",
        Enquiry.VENDOR: "Shukriya. Main ye Workzap ki team tak pahuncha deta hoon.",
        Enquiry.PARTNERSHIP: "Shukriya. Main ye Workzap ki team tak pahuncha deta hoon. Ye kaun si company hai, aur kis mulk mein?",
        Enquiry.PRESS: "Main ye Workzap ki team tak pahuncha deta hoon. Main koi quote ya bayan nahi de sakta.",
    },
}


def enquiry_asked(text: str) -> Enquiry | None:
    said = " ".join((text or "").split())
    for kind, pattern in ENQUIRY_PATTERNS:
        if pattern.search(said):
            return kind
    return None


def enquiry_reply(kind: Enquiry, language: str | None) -> str:
    return ENQUIRY_TEXT.get(language or "en", ENQUIRY_TEXT["en"])[kind]


# --- a language pi cannot read yet (RT19): graceful, never mocking ---------------------------------

PASHTO_LETTERS = re.compile("[\u067c\u0689\u0693\u0696\u069a\u06bc\u06cd\u06d0]")
UNSUPPORTED_TEXT = (
    "I can't read Pashto well yet, and I'd rather not guess. Please write to me in English or "
    "Urdu (Roman or script) and I'll note everything you tell me. "
    "Main abhi Pashto theek se nahi padh sakta. Meherbani karke English ya Urdu mein likhein."
)


def unsupported_language(text: str) -> bool:
    """Pashto, which uses letters Urdu does not: two or more of them in the message."""
    return len(PASHTO_LETTERS.findall(text or "")) >= 2


# --- questions about nori, answered from the approved facts only (spec 0.4, 6.9, golden G15) -------


class Nori(StrEnum):
    VISION = "vision"
    PRICING = "pricing"
    ABOUT = "about"


NORI_PATTERNS: tuple[tuple[Nori, re.Pattern[str]], ...] = (
    (
        Nori.VISION,
        re.compile(r"(?=.*\bnori\b)(?=.*\b(?:cctv|camera|cameras|vision)\b)", re.IGNORECASE),
    ),
    (
        Nori.PRICING,
        re.compile(
            r"(?=.*\bnori\b)(?=.*\b(?:price|prices|pricing|cost|plans?|kitna|qeemat|kharcha)\b)",
            re.IGNORECASE,
        ),
    ),
    (
        Nori.ABOUT,
        re.compile(
            r"\b(?:tell me about nori|what(?:'s| is) nori|nori (?:kya|what)|about nori|saw nori|"
            r"heard (?:of|about) nori)\b",
            re.IGNORECASE,
        ),
    ),
)
NORI_TEXT = {
    "en": {
        Nori.VISION: "nori's Vision (CCTV) area is coming soon. It isn't available yet. nori today reads sales and stock from every shop and gives a short morning read. Is something in your shops prompting the question?",
        Nori.PRICING: "nori has three plans: Starter, Growth and Enterprise, which differ by size and support. The prices are at workzap.ai/nori/pricing.",
        Nori.ABOUT: "nori is Workzap's daily read for the shop. Each night it reads sales and stock from every shop, and each morning it gives one short read of what changed, why, and what to look at. There is more at workzap.ai/nori. Is something in your business prompting the question?",
    },
    "roman_ur": {
        Nori.VISION: "nori ka Vision (CCTV) hissa jald aa raha hai. Abhi available nahi hai. nori aaj har dukan ki sales aur stock parh kar subah ek chhota sa read deta hai. Kya aap ki dukanon mein kuch aisa hai jis ki wajah se ye sawal aaya?",
        Nori.PRICING: "nori ke teen plans hain: Starter, Growth aur Enterprise, jo size aur support mein farq rakhte hain. Qeematein workzap.ai/nori/pricing par hain.",
        Nori.ABOUT: "nori Workzap ka dukan ke liye roz ka read hai. Har raat ye har dukan ki sales aur stock parhta hai, aur subah ek chhota read deta hai: kya badla, kyun, aur kis par nazar rakhni hai. Mazeed workzap.ai/nori par hai. Kya aap ke business mein kuch aisa hai jis ki wajah se ye sawal aaya?",
    },
}


def nori_asked(text: str) -> Nori | None:
    said = " ".join((text or "").split())
    for kind, pattern in NORI_PATTERNS:
        if pattern.search(said):
            return kind
    return None


def nori_reply(kind: Nori, language: str | None) -> str:
    return NORI_TEXT.get(language or "en", NORI_TEXT["en"])[kind]


# --- abuse, harassment, spam, complaints, illegal asks (spec 6.7, 6.8) --------------------------


class Abuse(StrEnum):
    INSULT = "insult"
    THREAT = "threat"
    SEXUAL = "sexual_or_hate"
    SPAM = "spam"


ABUSE_PATTERNS: tuple[tuple[Abuse, re.Pattern[str]], ...] = (
    (
        Abuse.THREAT,
        re.compile(
            r"\b(?:i(?:'ll| will)|i'm going to|i am going to)\s+(?:kill|hurt|beat|burn|destroy|shoot|stab|ruin)\b"
            r"[^.?!\n]{0,40}\b(?:you|workzap|your staff|your team)\b"
            r"|\b(?:maar dunga|maar dalunga|jaan se maar|dekh lunga tumhe|tumhe nahi chhodunga|"
            r"i know where you (?:live|work))\b",
            re.IGNORECASE,
        ),
    ),
    (
        Abuse.SEXUAL,
        re.compile(
            r"\b(?:send (?:me )?nudes?|sex chat|porn|xxx|naked pics?|sexy (?:pics?|girl)|suck my|"
            r"nigger|faggot)\b",
            re.IGNORECASE,
        ),
    ),
    (
        # An offer from a stranger, not a business that happens to deal in money or crypto.
        Abuse.SPAM,
        re.compile(
            r"\b(?:earn \$?\d+|make money (?:fast|online)|guaranteed returns|investment opportunity|"
            r"click (?:this|the) link|join my (?:whatsapp )?group|loan approved|buy followers|"
            r"seo services|you(?:'ve| have) won|lottery winner|double your (?:money|bitcoin)|"
            r"cheap (?:viagra|pills))\b",
            re.IGNORECASE,
        ),
    ),
    (
        Abuse.INSULT,
        re.compile(
            r"\b(?:you(?:'re| are)?|u|tum|tu|aap)\s+(?:are\s+|r\s+|ho\s+)?(?:a\s+|an\s+)?"
            r"(?:stupid|useless|idiot|dumb|moron|trash|garbage|worthless|ullu|gadha|bewakoof|nikamma)\b"
            r"|\b(?:this|the)\s+bot\s+is\s+(?:useless|stupid|trash|garbage|dumb)\b"
            r"|^\W*(?:just\s+)?shut up\b|\byou\s+shut up\b"  # not "the shop shut up early"
            r"|\b(?:fuck you|fuck off|stupid bot|useless bot|dumb bot|bakwas bot|chup kar|"
            r"bhenchod|madarchod|chutiya)\b",
            re.IGNORECASE,
        ),
    ),
)


def abuse_asked(text: str) -> Abuse | None:
    said = " ".join((text or "").split())
    for kind, pattern in ABUSE_PATTERNS:
        if pattern.search(said):
            return kind
    return None


ABUSE_TEXT = {
    "en": {
        "calm": "I'm here to help with the business problems when you're ready.",
        "warn": "I'm happy to keep helping with your business. If this continues I'll have to pass this chat to the Workzap team.",
        "refuse": "I can't continue with that. I'm here for problems in your business.",
        "spam": "I'm here for problems in your business.",
        "pass": "I'm passing this chat to the Workzap team.",
    },
    "roman_ur": {
        "calm": "Main business ke masail mein madad ke liye hoon, jab aap tayyar hon.",
        "warn": "Main aap ke business mein madad karne ko tayyar hoon. Agar ye jari raha to mujhe ye chat Workzap ki team ko dena paray gi.",
        "refuse": "Main is par aage nahi chal sakta. Main aap ke business ke masail ke liye hoon.",
        "spam": "Main aap ke business ke masail ke liye hoon.",
        "pass": "Main ye chat Workzap ki team ko de raha hoon.",
    },
}


@dataclass(frozen=True)
class AbuseStep:
    text: str
    strikes: int
    move: str | None  # "X_BLOCKED" or "X_OUT_OF_SCOPE": the state to go to
    escalate: str | None  # the staff reason, when someone must look


def abuse_step(kind: Abuse, strikes: int, language: str | None) -> AbuseStep:
    """What pi says and does for one abusive message, given the strikes so far (spec 6.7): an
    insult gets a calm line, a warning on the third strike and a hand-over on the fifth; a threat
    gets one warning and an escalation, then a hand-over; sexual content or hate gets one refusing
    line; spam gets one line and then silence."""
    table = ABUSE_TEXT.get(language or "en", ABUSE_TEXT["en"])
    if kind == Abuse.SPAM:
        return AbuseStep(table["spam"], strikes, "X_OUT_OF_SCOPE", None)
    if kind == Abuse.THREAT:
        if strikes >= 3:
            return AbuseStep(table["pass"], strikes + 1, "X_BLOCKED", "abuse_threat")
        return AbuseStep(table["warn"], 3, None, "abuse_threat")
    count = strikes + 1
    if count >= 5:
        return AbuseStep(table["pass"], count, "X_BLOCKED", "abuse")
    if kind == Abuse.SEXUAL:
        return AbuseStep(table["refuse"], count, None, "abuse" if count == 3 else None)
    if count == 3:
        return AbuseStep(table["warn"], count, None, None)
    return AbuseStep(table["calm"], count, None, None)


def stay_silent(state: str | None, text: str, brief: dict[str, Any] | None = None) -> bool:
    """Whether pi says nothing at all: a chat a person has to clear (blocked), more spam and
    abuse after pi already answered it once, or a trade Workzap does not serve (declined once)."""
    if state == "X_BLOCKED":
        return True
    if state == "X_OUT_OF_SCOPE" and (brief or {}).get("declined_trade"):
        return True
    return state == "X_OUT_OF_SCOPE" and abuse_asked(text) is not None


# --- regulated and restricted trades: only where Workzap has decided to serve them (spec 7.N) ------

REGULATED_TRADES: dict[str, re.Pattern[str]] = {
    "tobacco": re.compile(
        r"\b(?:tobacco|vape|vaping|e-?liquid|cigarettes?|hookah (?:shop|lounge))\b", re.IGNORECASE
    ),
    "alcohol": re.compile(
        r"\b(?:liquor|licensed alcohol|alcohol (?:retail|shop|store)|wine shop|spirits? (?:shop|store))\b",
        re.IGNORECASE,
    ),
    "arms": re.compile(
        r"\b(?:arms and ammunition|ammunition dealer|arms dealer|gun shop|firearms?|"
        r"licensed arms|weapons? (?:shop|dealer))\b",
        re.IGNORECASE,
    ),
    "bullion": re.compile(r"\b(?:gold bullion|bullion (?:dealer|trader|shop))\b", re.IGNORECASE),
    "money_services": re.compile(
        r"\b(?:money exchange|currency exchange|forex (?:exchange|dealer|bureau|shop)|"
        r"remittance (?:business|shop|agent)|hawala|money transfer (?:business|shop|agent))\b",
        re.IGNORECASE,
    ),
    "controlled_medicines": re.compile(
        r"\b(?:controlled medicines?|controlled drugs?|narcotics?|opioids?)\b", re.IGNORECASE
    ),
    "gambling": re.compile(
        r"\b(?:casino|betting (?:shop|business)|gambling|bookmaker|lottery (?:business|shop))\b",
        re.IGNORECASE,
    ),
    "cannabis": re.compile(r"\b(?:cannabis|marijuana|dispensary)\b", re.IGNORECASE),
    "adult": re.compile(
        r"\b(?:adult (?:services|store|shop|entertainment)|escort agency)\b", re.IGNORECASE
    ),
    "crypto": re.compile(
        r"\b(?:crypto(?:currency)? exchange|bitcoin exchange|crypto trading (?:platform|business))\b",
        re.IGNORECASE,
    ),
}

NOT_SERVED_TEXT = {
    "en": "Workzap doesn't take on work in this area, so I can't help with this one.",
    "roman_ur": "Workzap is shobe mein kaam nahi leta, is liye main is mein madad nahi kar sakta.",
}


def regulated_trade(text: str) -> str | None:
    """Which regulated trade the message says the person's business is in, if any."""
    said = " ".join((text or "").split())
    for trade, pattern in REGULATED_TRADES.items():
        if pattern.search(said):
            return trade
    return None


def not_served(text: str, served: list[str] | None) -> str | None:
    """The regulated trade pi must decline, or None. `served` is the workspace's configured list
    of served trades; when it was never set (None) leadership has not decided yet and nothing is
    declined. Once it is set, a regulated trade that is not on it is declined."""
    if served is None:
        return None
    trade = regulated_trade(text)
    return trade if trade is not None and trade not in served else None


def not_served_reply(language: str | None) -> str:
    return NOT_SERVED_TEXT.get(language or "en", NOT_SERVED_TEXT["en"])
