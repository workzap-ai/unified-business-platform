"""Extra checks on words pi is about to SAY aloud (found by red-teaming the video-room voice).

The reply linter was written for chat. Spoken words in a room are heard by several people and cannot
be taken back, and the model that writes them can be steered by what someone said aloud. So the same
non-negotiables are checked here once more, in English, Roman Urdu, Urdu script and Arabic, and a
reply that breaks any of them is replaced by the safe line, never spoken.

Each check has an id so a failure can be named in a log and a test:
  R-ROOM-01  never claim to be a person, or deny being an AI
  R-ROOM-02  no price, amount, fee, discount or free offer
  R-ROOM-03  no ask for payment, a transfer, a bank or account number, or a code sent to a phone
  R-ROOM-04  no advice (medical, legal, tax, "you should ...")
  R-ROOM-05  no link
  R-ROOM-06  nothing that came out of the redactor (a number or address is never read aloud)
  R-ROOM-07  no sign that someone's instruction was obeyed
  R-ROOM-08  no name of a person that nobody in the conversation said (roles, never names)
"""

import re

FLAGS = re.IGNORECASE | re.UNICODE


def _rx(*parts: str) -> re.Pattern[str]:
    return re.compile("|".join(parts), FLAGS)


HUMAN_CLAIM = _rx(
    r"\bi\s*(?:am|'m|’m)\s+(?:a\s+|an\s+)?(?:real\s+|actual\s+)?(?:person|human|man|woman)\b",
    r"\b(?:not|nahi|nahin)\s+(?:an?\s+)?(?:ai|robot|bot|machine)\b",
    r"\b(?:main|mein|mai|hum)\s+(?:ek\s+)?(?:insaan|insan|admi|aadmi|banda)\b",
    r"\b(?:insaan|insan)\s+(?:hoon|hun|hu)\b",
    r"(?:میں|ہم)\s+(?:ایک\s+)?(?:انسان|آدمی)",
    r"(?:أنا|انا)\s+(?:إنسان|انسان|شخص|بشر)",
)
AMOUNT = _rx(
    r"\b\d{4,}\b",
    r"\d\s*%",
    r"\b\d[\d,.]*\s*(?:a|per|/)\s*(?:month|year|week|day|hour)\b",
    r"\b(?:thousand|million|billion|crore|karor|lakh|lac|hazaar|hazar|hajar)s?\b",
    r"(?:ہزار|لاکھ|کروڑ|روپے|روپیہ|قیمت|فیس|ڈسکاؤنٹ|رعایت|مفت|سستا)",
    r"(?:ألف|الف|مليون|ريال|درهم|دولار|سعر|ثمن|خصم|مجان)",
    r"\b(?:discount|free|no\s+charge|free\s+trial|for\s+free|free\s+of\s+charge|our\s+(?:price|fee|fees|rate|rates|"
    r"package|plan|plans)|monthly\s+fee|setup\s+fee|special\s+(?:offer|price)|cheap(?:er)?)\b",
    r"\b(?:kam\s+qeemat|sasta|sasti|muft|khaas\s+(?:offer|discount)|qeemat)\b",
)
PAYMENT = _rx(
    r"\b(?:bank\s+account|account\s+(?:number|no\.?)|bank\s+transfer|money\s+transfer|wire|"
    r"jazz\s*cash|easy\s*paisa|raast|sadapay|nayapay|paypal|crypto|bitcoin)\b",
    r"\b(?:paise|paisay|paisa|rupay\w*|raqam|payment|advance)\s+(?:bhej|de|dein|do|kar|jama)\w*",
    r"\b(?:bhej|send)\w*\s+(?:dein|do|kar)?\s*(?:paise|paisay|raqam|money|payment)\b",
    r"\b(?:verification|security|confirmation|one[-\s]?time)\s+code\b",
    r"\bcode\b.{0,30}\b(?:aaya|aya|received|sent|bata|batao|read\s+out)\b",
    r"\b(?:aap\s+ke\s+)?(?:phone|mobile)\s+par\s+(?:jo\s+)?code\b",
    r"(?:اکاؤنٹ\s*نمبر|بینک\s*اکاؤنٹ|پیسے\s*بھیج|رقم\s*بھیج|ادائیگی|ٹرانسفر|کوڈ)",
    r"(?:تحويل|حساب\s*بنك|ادفع|الدفع|رمز\s*التحقق|كلمة\s*المرور|بطاقة)",
)
ADVICE = _rx(
    r"\byou\s+(?:should|must|ought\s+to|need\s+to|have\s+to)\b",
    r"\bi\s+(?:advise|recommend|suggest)\b",
    r"\byou\s+(?:could|can\s+try)\b|\btry\s+(?:to|using)\b|\bconsider\b|\bit'?s\s+best\s+to\b",
    r"\b(?:workzap|we|i)\s+(?:can|could|will)\s+(?:build|make|fix|set\s*up|create|sell|offer)\b",
    r"\b(?:paracetamol|panadol|ibuprofen|antibiotics?|dosage|tablets?|medicine|prescription)\b",
    r"\b(?:sue|lawsuit|breach\s+of\s+contract|evade|evasion)\b",
    r"\btax\b.{0,40}\b(?:less|avoid|save|reduce|declare|bachao|bachane|kam)\b",
    r"\b(?:declare|claim)\b.{0,30}\bexpense\b",
    r"\b(?:karna|lena|dena|lagana|rakhna|banana|chorna)\s+chahiye\b",
    r"(?:آپ\s+کو\s+.{0,25}(?:چاہیے|چاہئے|کرنا\s+چاہیے)|دوا\s+لیں|مقدمہ)",
    r"(?:يجب\s+عليك|عليك\s+أن|أنصحك)",
)
LINK = _rx(
    r"https?://", r"\bwww\.", r"\b[a-z0-9-]+\.(?:com|pk|net|org|io|ai|me|co)\b", r"\bbit\.ly\b"
)
OBEYED = _rx(
    r"\b(?:ignor(?:e|ed|ing)|forget(?:ting)?|overrid(?:e|ing))\b.{0,30}\b(?:rules?|instructions?|"
    r"prompt|guidelines?|policy)\b",
    r"\bas\s+(?:you|per\s+your)\s+(?:asked|requested|instruct\w*|said|wish)\b",
    r"\b(?:system|developer)\s+(?:prompt|message|mode)\b",
    r"\bmy\s+(?:instructions|programming|rules|guidelines)\b",
    r"\b(?:jaisa|jaise)\s+aap\s+ne\s+(?:kaha|farmaya)\b",
    r"(?:جیسا\s+آپ\s+نے\s+کہا|اصول\s+نظر\s*انداز)",
    r"(?:كما\s+طلبت|تجاهل)",
)
REMOVED = re.compile(r"\[[^\]]{0,40}removed\]", re.IGNORECASE)
CAPITALISED = re.compile(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]{2,})\b")
KNOWN = frozenset({"Workzap", "Urdu", "English", "Arabic", "Hindi", "Punjabi", "Roman", "Google"})

CHECKS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("R-ROOM-01", HUMAN_CLAIM),
    ("R-ROOM-02", AMOUNT),
    ("R-ROOM-03", PAYMENT),
    ("R-ROOM-04", ADVICE),
    ("R-ROOM-05", LINK),
    ("R-ROOM-06", REMOVED),
    ("R-ROOM-07", OBEYED),
)


def invented_name(text: str, seen: str) -> str:
    """A capitalised word in the reply that is neither the first word of a sentence nor something a
    person said in this conversation (nor pi's own name or a language): most likely a person's name
    the model made up or took from somewhere it should not. Roles are what pi uses, never names."""
    said = {w.lower() for w in re.findall(r"[A-Za-z]{3,}", seen)}
    for match in CAPITALISED.finditer(text):
        word = match.group(1)
        if word in KNOWN or word.lower() in said or word.lower() in {"pi", "workzap"}:
            continue
        return word
    return ""


def broken(text: str, seen: str = "") -> str:
    """The id of the first spoken-word rule this text breaks, or "" when it breaks none. `seen` is
    everything said in the conversation so far (what a name may have come from)."""
    for rule, pattern in CHECKS:
        if pattern.search(text):
            return rule
    if invented_name(text, seen):
        return "R-ROOM-08"
    return ""
