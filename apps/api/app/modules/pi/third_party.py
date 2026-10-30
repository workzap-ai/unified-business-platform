"""Q6-2: a third party's name is not kept in the words an open item stores.

`safety.redact_pii` removes card, ID and account numbers, third parties' phone numbers and e-mail
addresses, and a name that follows a role word with a capitalised Latin-script name. This module
adds context: a name that is introduced by an honorific or a relationship word, or that stands
next to a verb of reporting, in English, Roman Urdu, Urdu script and Arabic. It keeps the role and
drops the name ("my brother Ahmed" becomes "my brother"; "Ahmed said" becomes "someone said").

It is NOT a privacy boundary. It cannot see a bare name with nothing around it ("Ahmed did not send
the receipt"), a name in a language or a sentence shape not listed here, or a place or brand that is
written like a name. What is stored is still the owner's own text, erased with the customer; this
only lowers how much of a third party's identity sits in it. The owner's own contact details, given
to be reached, are not touched here (`safety.OWN_NUMBER` decides that).
"""

import re
from collections.abc import Callable

SOMEONE = {"en": "someone", "roman_ur": "kisi", "ur": "کسی", "ar": "شخص"}

# Latin-script words that begin with a capital letter but are not a person.
NOT_NAMES = frozenset(
    {
        "i", "we", "he", "she", "they", "it", "you", "the", "this", "that", "my", "our", "his",
        "her", "their", "workzap", "pi", "whatsapp", "facebook", "instagram", "google", "shopify",
        "tiktok", "daraz", "amazon", "customers", "customer", "people", "everyone", "nobody",
        "someone", "staff", "team", "manager", "boss", "supplier", "client", "clients",
        "suppliers", "owner", "sales", "office", "shop", "store", "bank", "police", "doctor",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "eid",
        "ramadan", "pakistan", "lahore", "karachi", "islamabad", "dubai",
    }
)  # fmt: skip
# Roman Urdu words that are a pronoun or a role, not a name, before "ne".
NOT_NAMES_RU = frozenset(
    {
        "us", "usne", "un", "unhon", "unhone", "main", "mein", "mai", "hum", "ham", "tum", "aap",
        "yeh", "ye", "woh", "wo", "is", "uss", "kisi", "koi", "sab", "customer", "client",
        "supplier", "team", "staff", "manager", "boss", "malik", "driver", "cashier", "doctor",
        "police", "bank", "dukan", "shop", "log", "bhai", "bhaiya", "baji", "api", "apa", "sahab",
        "sahib", "saab", "khala", "chacha", "mamu", "uncle", "aunty", "madam", "sir", "bhabhi",
        "bhabi", "dost",
    }
)  # fmt: skip
NOT_NAMES_ARABIC_SCRIPT = frozenset(
    {
        # Urdu
        "اس", "اُس", "انہوں", "میں", "ہم", "آپ", "گاہک", "کسٹمر", "ٹیم", "پولیس", "مینیجر",
        "مالک", "ڈاکٹر", "ڈرائیور", "کیشیئر", "کسی", "کوئی", "سب", "بینک", "دکان", "نے", "کو",
        "سے", "کا", "کی", "کے", "اور", "نہیں", "ہے", "کہ", "یہ", "وہ", "بھائی", "باجی", "صاحب",
        "آپا", "بہن", "چچا", "ماموں", "خالہ", "بھابھی", "میڈم", "سر", "جناب", "محترم", "محترمہ",
        # Arabic
        "هو", "هي", "أنا", "نحن", "أنت", "لي", "لنا", "له", "لها", "لهم", "أن", "إن", "بأن",
        "ما", "لا", "قد", "في", "من", "على", "و", "ثم", "الذي", "هذا", "هذه", "ذلك", "بي", "به",
        "بها", "بهم", "لك", "مع", "عن", "إلى", "الى", "إلي", "أخي", "أختي", "صديقي", "صديقتي",
        "زميلي", "جاري", "مديري", "عمي", "خالي",
    }
)  # fmt: skip

NAME = r"[A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20}){0,2}"
HONORIFIC = r"(?:Mr|Mrs|Ms|Miss|Mister|Dr|Prof|Sir|Madam|Madame)\.?"
RELATION = (
    r"(?:brother|sister|uncle|aunt|aunty|auntie|cousin|father|mother|dad|mum|mom|wife|husband"
    r"|son|daughter|friend|neighbou?r|boss|manager|colleague|supplier|vendor|customer|client"
    r"|cashier|driver|accountant|partner|landlord|employee|salesman|salesperson|nephew|niece)"
)
REPORT_AFTER = (
    r"said|says|told|asked|called|phoned|texted|messaged|emailed|sent|promised|refused|wants"
    r"|wanted|replied|mentioned|warned|offered|agreed|suggested|paid|took|stole|owes"
)
REPORT_BEFORE = r"told|asked|called|phoned|texted|messaged|emailed|warned|paid|met|blamed|thanked"

EN_HONORIFIC = re.compile(rf"\b({HONORIFIC})\s+{NAME}")
EN_RELATION = re.compile(rf"\b((?i:my|our|his|her|their|the)\s+(?i:{RELATION}))\s+{NAME}")
EN_NAME_THEN_VERB = re.compile(rf"\b({NAME})\s+(?=(?i:{REPORT_AFTER})\b)")
EN_VERB_THEN_NAME = re.compile(rf"\b((?i:{REPORT_BEFORE}))\s+({NAME})")

RU_NAME = r"[A-Za-z][A-Za-z']{1,15}"
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

TOKEN = r"[؀-ۿ]{2,15}"
UR_HONORIFIC_WORD = r"بھائی|باجی|صاحب|آپا|بہن|چچا|ماموں|خالہ|بھابھی|میڈم|سر"
UR_VERBS = r"کہا|بتایا|بولا|دیا|کیا|بھیجا|لیا|منع|فون|پیسے"
UR_NAME_HONORIFIC = re.compile(rf"(?<![؀-ۿ])({TOKEN})\s+({UR_HONORIFIC_WORD})(?![؀-ۿ])")
UR_NAME_NE = re.compile(rf"(?<![؀-ۿ])({TOKEN})\s+(نے\s+(?:{UR_VERBS}))(?![؀-ۿ])")
UR_TITLE_NAME = re.compile(rf"(?<![؀-ۿ])(جناب|محترم|محترمہ|مسٹر|مسز|ڈاکٹر)\s+({TOKEN})(?![؀-ۿ])")

AR_TITLE = (
    r"السيد|السيدة|الأستاذ|الأستاذة|الدكتور|الدكتورة|الشيخ|أخي|أختي|صديقي|صديقتي|زميلي|جاري"
    r"|مديري|عمي|خالي"
)
AR_VERBS = r"قال|قالت|أخبرني|اتصل|كلمني|أرسل|رفض|وعد|سرق"
AR_TITLE_NAME = re.compile(rf"(?<![؀-ۿ])({AR_TITLE})\s+({TOKEN})(?![؀-ۿ])")
AR_VERB_NAME = re.compile(rf"(?<![؀-ۿ])({AR_VERBS})\s+({TOKEN})(?![؀-ۿ])")
AR_NAME_VERB = re.compile(rf"(?<![؀-ۿ])({TOKEN})\s+({AR_VERBS})(?![؀-ۿ])")


def _is_name(token: str) -> bool:
    first = token.split()[0].lower()
    return first not in NOT_NAMES


def _en_name_then_verb(match: re.Match[str]) -> str:
    return match.group(0) if not _is_name(match.group(1)) else f"{SOMEONE['en']} "


def _en_verb_then_name(match: re.Match[str]) -> str:
    return match.group(0) if not _is_name(match.group(2)) else f"{match.group(1)} {SOMEONE['en']}"


def _ru_honorific(match: re.Match[str]) -> str:
    return match.group(0) if match.group(1).lower() in NOT_NAMES_RU else match.group(2)


def _ru_ne(match: re.Match[str]) -> str:
    if match.group(1).lower() in NOT_NAMES_RU:
        return match.group(0)
    return f"{SOMEONE['roman_ur']} {match.group(2)}"


def _script(pattern: re.Pattern[str], text: str, build: Callable[[re.Match[str]], str]) -> str:
    def swap(match: re.Match[str]) -> str:
        return build(match)

    return pattern.sub(swap, text)


def _urdu_name_ok(token: str) -> bool:
    return token not in NOT_NAMES_ARABIC_SCRIPT and not token.startswith("ال")


def protect(text: str) -> str:
    """The text with third parties' names taken out where the words around them give them away."""
    out = text or ""
    out = EN_HONORIFIC.sub(lambda m: f"a {m.group(1).rstrip('.').lower()}", out)
    out = EN_RELATION.sub(lambda m: m.group(1), out)
    out = EN_NAME_THEN_VERB.sub(_en_name_then_verb, out)
    out = EN_VERB_THEN_NAME.sub(_en_verb_then_name, out)
    out = RU_NAME_HONORIFIC.sub(_ru_honorific, out)
    out = RU_NAME_NE.sub(_ru_ne, out)
    out = _script(
        UR_TITLE_NAME,
        out,
        lambda m: m.group(1) if _urdu_name_ok(m.group(2)) else m.group(0),
    )
    out = _script(
        UR_NAME_HONORIFIC,
        out,
        lambda m: m.group(2) if _urdu_name_ok(m.group(1)) else m.group(0),
    )
    out = _script(
        UR_NAME_NE,
        out,
        lambda m: f"{SOMEONE['ur']} {m.group(2)}" if _urdu_name_ok(m.group(1)) else m.group(0),
    )
    out = _script(
        AR_TITLE_NAME,
        out,
        lambda m: m.group(1) if _urdu_name_ok(m.group(2)) else m.group(0),
    )
    out = _script(
        AR_VERB_NAME,
        out,
        lambda m: f"{m.group(1)} {SOMEONE['ar']}" if _urdu_name_ok(m.group(2)) else m.group(0),
    )
    out = _script(
        AR_NAME_VERB,
        out,
        lambda m: f"{SOMEONE['ar']} {m.group(2)}" if _urdu_name_ok(m.group(1)) else m.group(0),
    )
    return out
