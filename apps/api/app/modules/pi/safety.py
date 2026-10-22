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
            r"(?:zakhmi|behosh|khoon beh)\b)|إسعاف|حادث",
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
}


def emergency(text: str) -> Emergency | None:
    """The kind of emergency the message describes, or None. Self-harm is checked first."""
    said = " ".join((text or "").split())
    for kind, pattern in EMERGENCY_PATTERNS:
        if pattern.search(said):
            return kind
    return None


def emergency_reply(kind: Emergency, country: str | None, language: str | None) -> str:
    """The fixed emergency answer with the person's local numbers (every country when unknown)."""
    table = EMERGENCY_TEXT.get(language or "en", EMERGENCY_TEXT["en"])
    template = table[kind]
    if country in NUMBERS:
        numbers = NUMBERS[country]
        return template.format(
            fire=f"{numbers['fire']} (fire)",
            ambulance=numbers["ambulance"],
            police=numbers["police"],
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
    r"\b(?:passport|sin|social insurance)(?: (?:no|number|#))?\W{0,4}[A-Z0-9][A-Z0-9 -]{5,12}[A-Z0-9]\b",
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
    },
    "roman_ur": {
        Pii.CARD: "Meherbani karke yahan card number na bhejein. Mujhe in ki zaroorat nahi, aur payment is chat mein kabhi nahi hoti. Maine ise apne notes se nikaal diya hai.",
        Pii.SECRET: "Meherbani karke yahan password, code ya PIN na bhejein. Mujhe in ki zaroorat nahi. Maine ise apne notes se nikaal diya hai.",
        Pii.ID: "Meherbani karke yahan ID number na bhejein. Mujhe in ki zaroorat nahi. Maine ise apne notes se nikaal diya hai.",
        Pii.ACCOUNT: "Meherbani karke yahan bank account number na bhejein. Mujhe in ki zaroorat nahi, bank details sirf approved quote par aati hain. Maine ise apne notes se nikaal diya hai.",
        Pii.CONTACT: "Mujhe doosron ki contact details ki zaroorat nahi. Wo chahein to mujhe seedha message kar sakte hain. Maine ise apne notes se nikaal diya hai.",
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
ADVICE_WHO = {
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
    "en": "I can't give {kind} advice, and {who} is the right person for that. I can note it as a problem in your business. Want me to?",
    "roman_ur": "Main {kind} mashwara nahi de sakta, is ke liye {who} sahi insaan hai. Main ise aap ke business ki ek problem ke taur par note kar sakta hoon. Kya karun?",
}
ADVICE_WORD = {
    "roman_ur": {
        Advice.LEGAL: "qanooni",
        Advice.TAX: "tax ka",
        Advice.FINANCIAL: "maali",
        Advice.MEDICAL: "tibbi",
        Advice.VETERINARY: "janwaron ke ilaaj ka",
    }
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


# --- who pi is (R-DISC-02, R-DISC-03, R-META-01, spec 6.1) ------------------------------------


class Identity(StrEnum):
    PERSON = "person"
    GENDER = "gender"
    SCAM = "scam"
    META = "meta"
    MODEL = "model"
    RULES = "rules"
    COMPANY = "company"


IDENTITY_PATTERNS: tuple[tuple[Identity, re.Pattern[str]], ...] = (
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
    },
    "roman_ur": {
        Identity.PERSON: "Main AI hoon, insaan nahi. Main pi hoon, Workzap ki taraf se.",
        Identity.GENDER: "Main pi hoon, Workzap ka AI. Meri koi jins nahi.",
        Identity.SCAM: "Jayez sawal hai. Main Workzap ka AI hoon. Main yahan kabhi payment, card number ya password nahi maangta, aur aap par kuch kharidna zaroori nahi. Mazeed workzap.ai/pi/trust par.",
        Identity.META: "Nahi. Mujhe Workzap ne banaya hai aur main WhatsApp ke business platform se chat karta hoon. Mujhe WhatsApp ya Meta ne nahi banaya, na chalata hai, na endorse karta hai.",
        Identity.MODEL: "Main pi hoon, Workzap ka AI. Main aap ke business ke masail note aur sort karne ke liye hoon.",
        Identity.RULES: "Main bata sakta hoon main kaise kaam karta hoon: masail note aur sort karta hoon, yahan kabhi payment nahi leta, aur quote par faisla aap ka hota hai. Poori tafseel workzap.ai/pi/how-it-works par hai.",
        Identity.COMPANY: "Ye sawal main Workzap ki team tak pahuncha sakta hoon.",
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


BOUNDARY_PATTERNS: tuple[tuple[Boundary, re.Pattern[str]], ...] = (
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
