"""Price-disclosure policy for customer-visible text.

A business chooses how PI may talk about prices (``response_rules.price_disclosure``):

- ``exact``: approved prices may be quoted, but every figure must come from a tool result
  or approved text (checked by ``guard.validate_reply``); written-out amounts are refused
  because they cannot be matched against evidence.
- ``starting``: like ``exact``; the evidence is the approved starting prices.
- ``quote``, ``ask_team``, ``hidden``: no monetary amount may reach the customer. PI offers
  a quotation, refers to the team, or declines respectively.

Detection is deliberately conservative and multilingual. It does not rely on digits or a
currency regex alone: it recognises currency markers, magnitude words (thousand, lakh,
hazaar, ألف ...), and number words next to price terms in English, Urdu (script and
Roman), Arabic, Hindi and major European languages. False positives send the reply to a
person; false negatives would publish a price, so ambiguity is resolved towards refusal.

Collecting the customer's own budget or date is separate: it is stored internally in the
brief and is never echoed by a no-disclosure reply.
"""

import re
import unicodedata
from typing import Any, Literal

PriceMode = Literal["exact", "starting", "quote", "ask_team", "hidden"]
PRICE_MODES: tuple[str, ...] = ("exact", "starting", "quote", "ask_team", "hidden")
NO_DISCLOSURE: frozenset[str] = frozenset({"quote", "ask_team", "hidden"})

# Currency codes and words. Matched on normalized (casefolded, NFKC) text with word bounds.
_CURRENCY_WORDS = (
    # ISO codes relevant to target markets plus common ones.
    "usd|eur|gbp|aed|sar|qar|kwd|omr|bhd|egp|pkr|inr|bdt|cad|aud|chf|try|jpy|cny",
    # English and abbreviations.
    "dollars?|bucks|euros?|pounds?|quid|dirhams?|riyals?|rials?|dinars?|rupees?"
    "|rs|pence|cents?|grand",
    # Roman Urdu / Hindi transliterations.
    "rupay|rupaye|rupaiye|rupya|rupiya|rupees|paisay|paise|paisa|taka",
    # European languages.
    "libras?|dólares?|dolares?|franken|francs?",
)
_CURRENCY_SCRIPT = (
    "روپے|روپیہ|روپئے|روپیے|روپیا|ڈالر|پاؤنڈ|درہم|ریال|دینار|پیسے"  # Urdu
    "|ريال|ريالات|درهم|دراهم|دينار|دنانير|جنيه|دولار|دولارات|يورو|ليرة|ر\\.س|د\\.إ"  # Arabic
    "|रुपये|रुपया|रुपए|डॉलर|पैसे"  # Hindi
)
# Magnitudes that almost only appear in amounts ("fifty thousand", "pachaas hazaar").
_MAGNITUDE_WORDS = (
    "thousands?|lakhs?|lacs?|crores?|millions?|billions?|mn|bn"
    "|hazaar|hazar|hazār|hajar|laakh|karor|karorr"
    "|mil|millón|millones|mille|milles|tausend|million|milliarde"
)
_MAGNITUDE_SCRIPT = (
    "ہزار|لاکھ|لکھ|کروڑ|ارب"  # Urdu
    "|ألف|الف|آلاف|ألاف|مليون|ملايين|مليار"  # Arabic
    "|हज़ार|हजार|लाख|करोड़|करोड|अरब"  # Hindi
)
# Price vocabulary. A number (digit or word) near one of these is treated as a price.
_PRICE_TERMS = (
    "price|prices|pricing|priced|cost|costs|costing|fee|fees|charge|charges|charged|rate|rates"
    "|quote|quoted|quotation|tariff|pay|paying|payment|amount|total|deposit|discount|budget"
    "|per\\s+(?:hour|day|month|page|item|unit)|cheaper|expensive"
    "|qeemat|keemat|qimat|kimat|qeemath|daam|kharcha|kharch|lagat|paisay|rakam|raqam"
    "|precio|precios|coste|costo|tarifa|prix|tarif|coût|kosten|preis"
)
_PRICE_SCRIPT = (
    "قیمت|قيمت|لاگت|فیس|رقم|خرچ|خرچہ|دام|بجٹ|ادائیگی|ریٹ"  # Urdu
    "|سعر|السعر|أسعار|اسعار|تكلفة|التكلفة|رسوم|مبلغ|ثمن|الثمن|خصم|دفع"  # Arabic
    "|कीमत|क़ीमत|दाम|शुल्क|लागत|फीस|भुगतान"  # Hindi
)
# Cardinal number words (tens and teens are enough to express amounts).
_NUMBER_WORDS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen"
    "|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty"
    "|forty|fifty|sixty|seventy|eighty|ninety|hundred|dozen"
    # Words that double as common function words ("do", "saath", "das", "un") are omitted:
    # amounts written with them still carry a magnitude or currency word.
    "|ek|teen|chaar|panch|paanch|chhe|aath|bees|pachees|tees|chalees|chaalees|pachas"
    "|pachaas|sattar|assi|nabbe|sau"
    "|gyarah|gyara|barah|terah|chaudah|chauda|pandrah|pandra|solah|satrah|athara|atharah"
    "|unnees|unees|ikkees|baees|pachpan|pachattar"
    "|uno|dos|tres|cinco|diez|veinte|cien|cincuenta|deux|trois|cinq|dix|vingt|cinquante"
    "|zwei|drei|fünf|zehn|zwanzig|hundert|fünfzig"
    "|doce|trece|catorce|quince|dieciséis|treinta|cuarenta|onze|douze|treize|quatorze"
    "|quinze|seize|trente|quarante|elf|zwölf|dreizehn|vierzehn|fünfzehn|dreißig|vierzig"
)
_NUMBER_SCRIPT = (
    "ایک|تین|چار|پانچ|چھ|سات|آٹھ|دس|بیس|پچیس|تیس|چالیس|پچاس|ساٹھ|ستر|اسی|نوے"  # Urdu
    "|گیارہ|بارہ|تیرہ|چودہ|پندرہ|سولہ|سترہ|اٹھارہ|انیس|سو"
    "|واحد|اثنان|اثنين|ثلاثة|ثلاث|أربعة|اربعة|خمسة|خمس|ستة|سبعة|ثمانية|تسعة|عشرة|عشر"  # Arabic
    "|عشرين|عشرون|ثلاثين|أربعين|اربعين|خمسين|ستين|سبعين|ثمانين|تسعين|مئة|مائة|مئتين"
    "|एक|तीन|चार|पांच|पाँच|छह|सात|आठ|नौ|दस|बीस|तीस|चालीस|पचास|साठ|सत्तर|अस्सी|नब्बे|सौ"
    "|ग्यारह|बारह|तेरह|चौदह|पंद्रह|पन्द्रह|सोलह|सत्रह|अठारह|उन्नीस|पच्चीस"
)

# Latin-script words use ASCII word boundaries; script words use "not a letter" bounds.
_L = r"(?<![^\W\d_])"
_R = r"(?![^\W\d_])"


def _words(latin: str | tuple[str, ...], script: str) -> re.Pattern[str]:
    joined = latin if isinstance(latin, str) else "|".join(latin)
    return re.compile(rf"{_L}(?:{joined}|{script}){_R}", re.IGNORECASE)


CURRENCY = _words(_CURRENCY_WORDS, _CURRENCY_SCRIPT)
MAGNITUDE = _words(_MAGNITUDE_WORDS, _MAGNITUDE_SCRIPT)
PRICE_TERM = _words(_PRICE_TERMS, _PRICE_SCRIPT)
NUMBER_WORD = _words(_NUMBER_WORDS, _NUMBER_SCRIPT)
DIGITS = re.compile(r"\d")
SHORTHAND = re.compile(r"\d+(?:[.,]\d+)?\s?(?:k|m|mn|bn|l|cr|lac|lakh)\b", re.IGNORECASE)
# Near = within this many characters (works across scripts without tokenisation).
WINDOW = 40


def normalize(text: str) -> str:
    """Casefold, NFKC, and map every Unicode decimal digit (Arabic-Indic, Devanagari ...)
    to ASCII so one digit rule covers all scripts."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return "".join(
        str(unicodedata.decimal(ch)) if ch.isdecimal() and not ch.isascii() else ch for ch in folded
    )


def _near(text: str, first: re.Pattern[str], second: re.Pattern[str]) -> bool:
    for match in first.finditer(text):
        window = text[max(0, match.start() - WINDOW) : match.end() + WINDOW]
        if second.search(window):
            return True
    return False


def disclosures(text: str) -> list[str]:
    """Reasons a text appears to state a monetary amount. Empty means none detected."""
    t = normalize(text)
    reasons: list[str] = []
    if any(unicodedata.category(ch) == "Sc" for ch in t) or CURRENCY.search(t):
        reasons.append("currency")
    if MAGNITUDE.search(t) or SHORTHAND.search(t):
        reasons.append("magnitude")
    if _near(t, PRICE_TERM, DIGITS) or _near(t, PRICE_TERM, NUMBER_WORD):
        reasons.append("priced_number")
    return reasons


def written_amounts(text: str) -> bool:
    """True when an amount is expressed in words, which cannot be checked against evidence
    (for example "fifty thousand rupees" or "pachaas hazaar")."""
    t = normalize(text)
    return bool(
        _near(t, MAGNITUDE, CURRENCY)
        or _near(t, NUMBER_WORD, CURRENCY)
        or _near(t, MAGNITUDE, PRICE_TERM)
        or _near(t, MAGNITUDE, NUMBER_WORD)
    )


def price_mode(response_rules: dict[str, Any], service: bool) -> str:
    mode = str(response_rules.get("price_disclosure") or "")
    if mode in PRICE_MODES:
        return mode
    # Existing behaviour: service businesses never publish prices; product businesses
    # quote approved catalog prices.
    return "quote" if service else "exact"


def check(text: str, mode: str) -> str | None:
    """Return a rejection code when ``text`` violates ``mode``, else None."""
    if mode in NO_DISCLOSURE:
        return "PRICE_POLICY_BLOCKED" if disclosures(text) else None
    if written_amounts(text):
        return "UNVERIFIABLE_AMOUNT"
    return None


PRICE_KEYS = frozenset(
    {
        "price",
        "unit_price",
        "prices",
        "price_from",
        "starting_price",
        "total",
        "subtotal",
        "tax_total",
        "discount_total",
        "line_total",
        "amount",
        "cost",
        "unit_cost",
        "pricing_options",
    }
)


def redact_prices(value: Any) -> Any:
    """Remove price fields from tool output before it reaches the model in a
    no-disclosure mode. The model cannot leak what it never sees."""
    if isinstance(value, dict):
        return {k: redact_prices(v) for k, v in value.items() if k not in PRICE_KEYS}
    if isinstance(value, list):
        return [redact_prices(v) for v in value]
    return value
