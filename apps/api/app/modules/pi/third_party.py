"""Q6-2: a third party's name is not kept in the words an open item stores.

`safety.redact_pii` removes card, ID and account numbers, third parties' phone numbers and e-mail
addresses, and a name that follows a role word with a capitalised Latin-script name. This module
adds context: a name that is introduced by an honorific or a relationship word, or that stands
next to a verb of reporting, in English, Roman Urdu, Urdu script and Arabic. It keeps the role and
drops the name ("my brother Ahmed" becomes "my brother"; "Ahmed said" becomes "someone said").

It is NOT a privacy boundary. Honest limits, in both directions:
* False negatives (a name stays): a bare name with nothing around it ("Ahmed did not send the
  receipt"); a name that is not capitalised in Latin script ("ahmed ne kaha"); a name after a
  title word that is not listed, or an honorific placed BEFORE a Roman Urdu name ("bhai Ahmed"); a
  name next to a stop word ("Monday Ahmed said", "Yesterday Bilal said": every capitalised word of
  the match must be a non-stop word); a name with a verb that is not a reporting verb ("Ahmed took
  the stock"); a name in a language not listed here.
* False positives (a word is replaced): a capitalised word that is neither a name nor in the stop
  lists, standing before a reporting verb or after "called/told/asked/phoned/texted/messaged/
  emailed/warned", becomes "someone" ("I called Careem", "Uber said"). The check is ONE merged
  one: a word on any stop list (English, Roman Urdu, Urdu or Arabic) is never read as a name, in
  any pattern, so "Ammi said", "Bhai said", "Abbu called", "told Baji" and "called Sahab" keep their
  word. The lists hold pronouns, possessives, greetings, time words, relatives, trades and roles
  (mom, dad, brother, boss, friend, agent, tailor, rider, courier, cashier ...), places, well-known
  brands and technical words; a role or relative that is not in them is treated as a name
  ("Plumber said" is kept only because plumber is listed; "Glazier said" is not). All-capital
  words (API, SB) are never read as an honorific.
* Words that are also given names. On a list, so a real name survives where a pattern fits (a
  false negative): Salam, Kal, Malik, Abu, Ami, Mai (and Beta, Dada, Nana, Ji, Good, Now). On no
  list, so they are replaced where a pattern fits (the intended effect for a name, a loss when it
  is a common word): Mark, Will, Bill, Rose, Grace, May, Sunny, Amber.
* A relative with a name keeps the relative and drops the name ("Uncle Ahmed said" becomes "Uncle
  said"; "my uncle Ahmed" becomes "my uncle").
What is stored is still the owner's own text, erased with the customer; this only lowers how much
of a third party's identity sits in it. The owner's own contact details, given to be reached, are
not touched here (`safety.OWN_NUMBER` decides that).
"""

import re
from collections.abc import Callable

SOMEONE = {"en": "someone", "roman_ur": "kisi", "ur": "کسی", "ar": "شخص"}

# Words that are never a person's name, whatever their case or place in the sentence. Every word of
# a matched name is checked, so one of these inside the match keeps the whole match as written.
NOT_NAMES = frozenset(
    {
        # pronouns, determiners, possessives, politeness, connectives
        "i", "we", "he", "she", "they", "it", "you", "the", "this", "that", "these", "those", "a",
        "an", "my", "our", "his", "her", "their", "your", "dear", "sir", "madam", "mr", "mrs", "ms",
        "miss", "yes", "no", "ok", "okay", "sorry", "please", "thanks", "thank", "hello", "hi",
        "also", "then", "and", "but", "so", "if", "when", "because", "however", "finally", "first",
        "next", "last", "someone", "everyone", "nobody", "anyone", "nothing", "everything",
        # roles and groups
        "delivery", "driver", "courier", "rider", "cashier", "support", "care", "service",
        "services", "manager", "owner", "staff", "customer", "customers", "client", "clients",
        "supplier", "suppliers", "vendor", "team", "bank", "police", "doctor", "people", "office",
        "shop", "store", "sales", "accountant", "partner", "landlord", "employee", "salesman",
        # things a sentence starts with
        "payment", "payments", "order", "orders", "stock", "price", "prices", "invoice",
        "invoices", "parcel", "package", "shipment", "today", "yesterday", "tomorrow", "tonight",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "eid",
        "ramadan",
        # places and brands
        "pakistan", "lahore", "karachi", "islamabad", "dubai", "workzap", "pi", "whatsapp",
        "facebook", "instagram", "google", "shopify", "tiktok", "youtube", "amazon", "daraz",
        "easypaisa", "jazzcash", "meezan", "hbl", "ubl", "alfalah", "foodpanda", "bykea", "tcs",
        "leopards", "trax", "postex",
        # relatives and trades
        "boss", "ustad", "mom", "mum", "dad", "mother", "father", "brother", "sister", "friend",
        "agent", "tailor", "uncle", "aunt", "aunty", "auntie", "cousin", "neighbour", "neighbor",
        "wife", "husband", "son", "daughter", "nephew", "niece", "grandfather", "grandmother",
        "grandma", "grandpa", "teacher", "plumber", "electrician", "mechanic", "designer",
        "developer", "engineer", "lawyer", "supervisor", "receptionist", "secretary", "waiter",
        "chef", "guard", "worker", "representative", "assistant", "salesperson",
        # greetings and time words
        "assalam", "salam", "kal", "aaj", "shukriya", "jazakallah", "welcome", "good",
        "morning", "evening", "night", "afternoon", "now", "later",
        # technical words and products
        "api", "rest", "stripe", "zapier", "sdk", "aws", "azure", "graphql", "webhook",
        "wordpress", "woocommerce", "odoo", "quickbooks", "tally", "excel", "sheets", "zoom",
        "slack", "github", "oauth", "json", "sql", "crm", "erp", "ai", "paypal", "visa",
        "mastercard", "gmail", "outlook",
    }
)  # fmt: skip
# Roman Urdu: pronouns, possessives, function words, honorific words and roles (plus NOT_NAMES).
NOT_NAMES_RU = frozenset(
    {
        "us", "usne", "un", "unhon", "unhone", "main", "mein", "mai", "hum", "ham", "tum", "aap",
        "yeh", "ye", "woh", "wo", "is", "uss", "kisi", "koi", "sab", "mera", "meri", "mere",
        "hamara", "hamari", "hamare", "tumhara", "tumhari", "aapka", "aapki", "aapke", "uska",
        "uski", "uske", "ka", "ki", "ke", "ko", "se", "ne", "hai", "hain", "tha", "thi",
        "dukandar", "dukan", "malik", "log", "bhai", "bhaiya", "baji", "api", "apa", "sahab",
        "sahib", "saab", "khala", "chacha", "mamu", "uncle", "aunty", "madam", "bhabhi", "bhabi",
        "dost",
        "ammi", "ami", "abbu", "abu", "behan", "bahan", "beta", "beti", "biwi", "shauhar",
        "phuphi", "nana", "nani", "dada", "dadi", "darzi", "ustad", "assalam", "salam", "kal",
        "aaj", "shukriya", "ji", "jee", "haan", "theek", "acha", "achha",
    }
)  # fmt: skip
NOT_NAMES_ARABIC_SCRIPT = frozenset(
    {
        # Urdu: pronouns, possessives, function words
        "اس", "اُس", "انہوں", "میں", "ہم", "آپ", "کسی", "کوئی", "سب", "نے", "کو", "سے", "کا",
        "کی", "کے", "اور", "نہیں", "ہے", "کہ", "یہ", "وہ", "میرا", "میری", "میرے", "ہمارا",
        "ہماری", "ہمارے", "تمہارا", "تمہاری", "تمہارے", "اپنا", "اپنی", "اپنے", "آپکا", "آپکی",
        "آپکے", "ان", "اب", "پھر", "بھی",
        # Urdu: honorifics and roles
        "بھائی", "باجی", "صاحب", "آپا", "بہن", "چچا", "ماموں", "خالہ", "بھابھی", "میڈم", "سر",
        "جناب", "محترم", "محترمہ", "دکاندار", "ڈرائیور", "رائیڈر", "رائڈر", "کوریئر", "کیشیئر",
        "سپورٹ", "ڈیلیوری", "مینیجر", "منیجر", "مالک", "سٹاف", "بنک", "بینک", "کسٹمر", "گاہک",
        "سپلائر", "ٹیم", "پولیس", "ہسپتال", "ڈاکٹر", "دوست", "ایزی", "پیسہ", "جاز", "کیش",
        # Arabic: pronouns, function words, prepositions
        "هو", "هي", "أنا", "نحن", "أنت", "لي", "لنا", "له", "لها", "لهم", "أن", "إن", "بأن",
        "إنه", "أنه", "انه", "ما", "لا", "لم", "لن", "قد", "كان", "لقد", "هل", "كل",
        "بعد", "قبل", "عند", "هنا", "هناك", "حتى", "لكن", "او", "أو", "يا", "في", "من", "على",
        "و", "ثم", "الذي", "هذا", "هذه", "ذلك", "بي", "به", "بها", "بهم", "لك", "مع", "عن",
        "إلى", "الى", "إلي",
        # Arabic: relations, titles and roles
        "أخي", "أختي", "صديقي", "صديقتي", "زميلي", "جاري", "مديري", "عمي", "خالي", "مندوب",
        "سائق", "كاشير", "دعم", "خدمة", "بنك", "مدير", "موظف", "مالك", "فريق", "شرطة",
        "مستشفى", "طبيب",
        # Urdu and Arabic: relatives, trades, greetings, time words
        "ماں", "امی", "ابو", "والد", "والدہ", "باس", "ایجنٹ", "درزی", "استاد", "پھوپھی",
        "بیوی", "شوہر", "بیٹا", "بیٹی", "جی", "شکریہ", "کل", "آج", "سلام", "السلام", "ہاں",
        "اچھا", "ٹھیک", "أمي", "أبي", "رئيسي", "وكيل", "خياط", "معلم", "شكرا", "أمس", "اليوم",
        "غدا", "مرحبا",
        # Arabic: the reporting verbs themselves are never a name
        "قال", "قالت", "أخبرني", "اتصل", "كلمني", "أرسل", "رفض", "وعد", "سرق",
    }
)  # fmt: skip
ALL_STOP = NOT_NAMES | NOT_NAMES_RU | NOT_NAMES_ARABIC_SCRIPT  # one check for every pattern

NAME = r"[A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20}){0,2}"
HONORIFIC = r"(?:Mr|Mrs|Ms|Miss|Mister|Dr|Prof|Sir|Madam|Madame)\.?"
RELATION = (
    r"(?:brother|sister|uncle|aunt|aunty|auntie|cousin|father|mother|dad|mum|mom|wife|husband"
    r"|son|daughter|friend|neighbou?r|boss|manager|colleague|supplier|vendor|customer|client"
    r"|cashier|driver|accountant|partner|landlord|employee|salesman|salesperson|nephew|niece)"
)
# Only verbs that say what a person SAID or DID to the owner; "took", "sent", "paid" and the like
# also follow places and brands, so they are not used.
REPORT_AFTER = (
    r"said|says|told|asked|called|phoned|texted|messaged|emailed|promised|refused|replied"
    r"|mentioned|warned"
)
REPORT_BEFORE = r"told|asked|called|phoned|texted|messaged|emailed|warned"

EN_HONORIFIC = re.compile(rf"\b({HONORIFIC})\s+({NAME})")
EN_TITLE_RELATION = re.compile(
    rf"\b(Uncle|Aunt|Aunty|Auntie|Brother|Sister|Cousin|Boss|Ustad|Teacher)\s+({NAME})"
)
EN_RELATION = re.compile(rf"\b((?i:my|our|his|her|their|the)\s+(?i:{RELATION}))\s+({NAME})")
EN_NAME_THEN_VERB = re.compile(rf"\b({NAME})\s+(?=(?i:{REPORT_AFTER})\b)")
EN_VERB_THEN_NAME = re.compile(rf"\b((?i:{REPORT_BEFORE}))\s+({NAME})")
HONORIFIC_ROLE = {"dr": "a doctor", "prof": "a professor"}

# A Roman Urdu name is a capitalised Latin word: a lower-case word is a word, not a name.
RU_NAME = r"[A-Z][A-Za-z']{1,15}"
RU_HONORIFIC_WORD = (
    r"bhai|bhaiya|bhai\s+jaan|baji|api|apa|sahab|sahib|saab|sb|khala|chacha|mamu|uncle|aunty"
    r"|madam|sir|bhabhi|bhabi|dost"
)
RU_VERBS = (
    r"kaha|bola|bataya|batayi|mana|phone|call|message|paise|bheja|diya|liya|kiya|aaya|gaya"
    r"|dhoka|chori"
)
RU_NAME_HONORIFIC = re.compile(rf"\b({RU_NAME})\s+((?i:{RU_HONORIFIC_WORD}))\b")
RU_NAME_NE = re.compile(rf"\b({RU_NAME})\s+((?i:ne|ko)\s+(?i:{RU_VERBS}))\b")

# Letters of the Arabic script as used for Arabic and Urdu: no punctuation (، ؛ ؟ ۔), no digits,
# no diacritics, so a match can never swallow or move a sentence mark.
LETTER = r"[ء-ؿف-يٮ-ۓەۺ-ۼۿ]"
TOKEN = rf"{LETTER}{{2,15}}"
START = rf"(?<!{LETTER})"
END = rf"(?!{LETTER})"
UR_HONORIFIC_WORD = r"بھائی|باجی|صاحب|آپا|بہن|چچا|ماموں|خالہ|بھابھی|میڈم|سر"
UR_VERBS = r"کہا|بتایا|بولا|دیا|کیا|بھیجا|لیا|منع|فون|پیسے"
UR_NAME_HONORIFIC = re.compile(rf"{START}({TOKEN})\s+({UR_HONORIFIC_WORD}){END}")
UR_NAME_NE = re.compile(rf"{START}({TOKEN})\s+(نے\s+(?:{UR_VERBS})){END}")
UR_TITLE_NAME = re.compile(rf"{START}(جناب|محترم|محترمہ|مسٹر|مسز|ڈاکٹر)\s+({TOKEN}){END}")

AR_TITLE = (
    r"السيد|السيدة|الأستاذ|الأستاذة|الدكتور|الدكتورة|الشيخ|أخي|أختي|صديقي|صديقتي|زميلي|جاري"
    r"|مديري|عمي|خالي"
)
AR_VERBS = r"قال|قالت|أخبرني|اتصل|كلمني|أرسل|رفض|وعد|سرق"
AR_TITLE_NAME = re.compile(rf"{START}({AR_TITLE})\s+({TOKEN}){END}")
AR_VERB_NAME = re.compile(rf"{START}({AR_VERBS})\s+({TOKEN}){END}")
AR_NAME_VERB = re.compile(rf"{START}({TOKEN})\s+({AR_VERBS}){END}")


def _is_name(token: str) -> bool:
    """Every word of the match must be a possible name (none on any stop list)."""
    return all(word.lower() not in ALL_STOP for word in token.split())


def _is_name_ru(token: str) -> bool:
    return _is_name(token)


def _script_name(token: str) -> bool:
    return token not in NOT_NAMES_ARABIC_SCRIPT and not token.startswith("ال")


def _honorific(match: re.Match[str]) -> str:
    if not _is_name(match.group(2)):
        return match.group(0)
    return HONORIFIC_ROLE.get(match.group(1).rstrip(".").lower(), "a person")


def _relation(match: re.Match[str]) -> str:
    return match.group(1) if _is_name(match.group(2)) else match.group(0)


def _title_relation(match: re.Match[str]) -> str:
    return match.group(1) if _is_name(match.group(2)) else match.group(0)


def _name_then_verb(match: re.Match[str]) -> str:
    return f"{SOMEONE['en']} " if _is_name(match.group(1)) else match.group(0)


def _verb_then_name(match: re.Match[str]) -> str:
    return f"{match.group(1)} {SOMEONE['en']}" if _is_name(match.group(2)) else match.group(0)


def _ru_honorific(match: re.Match[str]) -> str:
    if match.group(2).isupper():  # API, SB: a technical word, not an honorific
        return match.group(0)
    return match.group(2) if _is_name_ru(match.group(1)) else match.group(0)


def _ru_ne(match: re.Match[str]) -> str:
    if not _is_name_ru(match.group(1)):
        return match.group(0)
    return f"{SOMEONE['roman_ur']} {match.group(2)}"


def _swap(pattern: re.Pattern[str], text: str, build: Callable[[re.Match[str]], str | None]) -> str:
    """Replace each match by what `build` returns; None keeps the match as written."""

    def one(match: re.Match[str]) -> str:
        built = build(match)
        return match.group(0) if built is None else built

    return pattern.sub(one, text)


def protect(text: str) -> str:
    """The text with third parties' names taken out where the words around them give them away."""
    out = text or ""
    out = EN_HONORIFIC.sub(_honorific, out)
    out = EN_RELATION.sub(_relation, out)
    out = EN_TITLE_RELATION.sub(_title_relation, out)
    out = EN_NAME_THEN_VERB.sub(_name_then_verb, out)
    out = EN_VERB_THEN_NAME.sub(_verb_then_name, out)
    out = RU_NAME_HONORIFIC.sub(_ru_honorific, out)
    out = RU_NAME_NE.sub(_ru_ne, out)
    out = _swap(UR_TITLE_NAME, out, lambda m: m.group(1) if _script_name(m.group(2)) else None)
    out = _swap(UR_NAME_HONORIFIC, out, lambda m: m.group(2) if _script_name(m.group(1)) else None)
    out = _swap(
        UR_NAME_NE,
        out,
        lambda m: f"{SOMEONE['ur']} {m.group(2)}" if _script_name(m.group(1)) else None,
    )
    out = _swap(AR_TITLE_NAME, out, lambda m: m.group(1) if _script_name(m.group(2)) else None)
    out = _swap(
        AR_VERB_NAME,
        out,
        lambda m: f"{m.group(1)} {SOMEONE['ar']}" if _script_name(m.group(2)) else None,
    )
    out = _swap(
        AR_NAME_VERB,
        out,
        lambda m: f"{SOMEONE['ar']} {m.group(2)}" if _script_name(m.group(1)) else None,
    )
    return out
