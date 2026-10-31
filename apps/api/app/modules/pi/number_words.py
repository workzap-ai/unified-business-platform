"""Amounts written as number words ("five hundred rupees", "panch sau", "a grand").

Used ONLY by the price check (``price_policy``). Digits, currency signs and magnitude words are
handled there already; this module adds number words (English, Roman Urdu, Urdu, Arabic, Hindi,
French, Spanish, a little German) in their spaced, hyphenated and glued spellings, and money
slang. It is deliberately conservative the other way round too: a number word is an amount only
when it is attached to money, so "two ideas", "ten minutes", "Step three" and "hundred percent
sure" keep passing.

A number phrase ("five hundred and fifty", "panch sau") is an amount when
  1. it is directly next to a currency word or sign ("sau rupay", "ten euros"), or
  2. it is next to a price word ("cost", "fee", "per month", "qeemat", "sasta") with only
     filler words between ("the price is just five hundred"), or
  3. it reaches a hundred or more and ends the clause or is followed by "and/or/for/ish"
     ("just five hundred.", "a hundred or so").
A lone "one"/"ek"/"do"/"a" is too ambiguous: it counts only straight before a currency word.
Money slang ("tenner", "fiver", "bucks", "a grand", "half a grand") counts on its own.
"""

import re
import unicodedata


def _fold_char(ch: str) -> str:
    code = ord(ch)
    if code < 0x250:  # Latin: pāñch -> panch, fünf -> funf
        return "".join(c for c in unicodedata.normalize("NFD", ch) if not unicodedata.combining(c))
    if 0x064B <= code <= 0x065F or code in (0x0670, 0x0640):  # Arabic marks and tatweel
        return ""
    return {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ی",
        "ي": "ی",
        "ك": "ک",
        "ة": "ه",
        "ھ": "ہ",
        "ە": "ہ",
        "ؤ": "و",
        "ئ": "ی",
        "ۓ": "ی",
        "ے": "ی",
        "ڑ": "ر",
    }.get(ch, ch)


def fold(text: str) -> str:
    """NFKC (superscript and circled digits become digits), casefold, drop Latin diacritics and
    Arabic marks, unify Arabic/Urdu letter shapes, and turn every Unicode digit into ASCII."""
    text = unicodedata.normalize("NFKC", text).casefold()
    out: list[str] = []
    for ch in text:
        if ch.isdecimal() and not ch.isascii():
            out.append(str(unicodedata.decimal(ch)))
        else:
            out.append(_fold_char(ch))
    return "".join(out)


# ---- vocabulary (written unfolded; folded when the tables are built) -----------------------------

_UNITS = {
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "dozen": 12,
    # Roman Urdu / Hindi
    "ek": 1, "aik": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "panch": 5, "paanch": 5,
    "pach": 5, "chhe": 6, "chay": 6, "chhah": 6, "saat": 7, "sat": 7, "aath": 8, "nau": 9,
    "das": 10, "gyarah": 11, "gyara": 11, "barah": 12, "terah": 13, "chaudah": 14,
    "chauda": 14, "pandrah": 15, "pandra": 15, "solah": 16, "satrah": 17, "athara": 18,
    "atharah": 18, "unnees": 19, "unees": 19, "bees": 20, "ikkees": 21, "baees": 22,
    "teis": 23, "chaubees": 24, "pachees": 25, "chhabbees": 26, "sattaees": 27,
    "atthaees": 28, "untees": 29, "tees": 30, "chalees": 40, "chaalees": 40,
    "pachas": 50, "pachaas": 50, "pachpan": 55, "saath": 60, "sattar": 70, "pachattar": 75,
    "assi": 80, "nabbe": 90, "dhai": 2, "derh": 1, "sadhe": 1,
    # Spanish
    "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
    "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14,
    "quince": 15, "dieciseis": 16, "veinte": 20, "treinta": 30, "cuarenta": 40,
    "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90,
    # French
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "sept": 7,
    "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14,
    "quinze": 15, "seize": 16, "vingt": 20, "trente": 30, "quarante": 40,
    "cinquante": 50, "soixante": 60,
    # German
    "ein": 1, "eins": 1, "zwei": 2, "drei": 3, "vier": 4, "funf": 5, "sechs": 6,
    "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "zwolf": 12, "zwanzig": 20,
    "dreissig": 30, "vierzig": 40, "funfzig": 50,
    # Urdu
    "ایک": 1, "دو": 2, "تین": 3, "چار": 4, "پانچ": 5, "چھ": 6, "سات": 7, "آٹھ": 8, "نو": 9,
    "دس": 10, "گیارہ": 11, "بارہ": 12, "تیرہ": 13, "چودہ": 14, "پندرہ": 15, "سولہ": 16,
    "سترہ": 17, "اٹھارہ": 18, "انیس": 19, "بیس": 20, "پچیس": 25, "تیس": 30, "چالیس": 40,
    "پچاس": 50, "ساٹھ": 60, "ستر": 70, "اسی": 80, "نوے": 90,
    # Arabic
    "واحد": 1, "اثنان": 2, "اثنین": 2, "ثلاثه": 3, "ثلاث": 3, "اربعه": 4, "خمسه": 5,
    "خمس": 5, "سته": 6, "سبعه": 7, "ثمانیه": 8, "تسعه": 9, "عشره": 10, "عشر": 10,
    "عشرین": 20, "عشرون": 20, "ثلاثین": 30, "اربعین": 40, "خمسین": 50, "ستین": 60,
    "سبعین": 70, "ثمانین": 80, "تسعین": 90,
    # Hindi
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "सात": 7,
    "आठ": 8, "नौ": 9, "दस": 10, "ग्यारह": 11, "बारह": 12, "तेरह": 13, "चौदह": 14,
    "पंद्रह": 15, "पन्द्रह": 15, "सोलह": 16, "सत्रह": 17, "अठारह": 18, "उन्नीस": 19,
    "बीस": 20, "पच्चीस": 25, "तीस": 30, "चालीस": 40, "पचास": 50, "साठ": 60, "सत्तर": 70,
    "अस्सी": 80, "नब्बे": 90,
}  # fmt: skip

# Hundred and above. "mil" (Spanish thousand) and "cent" (French hundred) are here too.
_SCALES = {
    "hundred": 100, "thousand": 1000, "million": 10**6, "billion": 10**9, "lakh": 10**5,
    "lac": 10**5, "laakh": 10**5, "crore": 10**7, "karor": 10**7, "sau": 100,
    "hazaar": 1000, "hazar": 1000, "hajar": 1000, "cien": 100, "ciento": 100,
    "doscientos": 200, "trescientos": 300, "cuatrocientos": 400, "quinientos": 500,
    "seiscientos": 600, "setecientos": 700, "ochocientos": 800, "novecientos": 900,
    "mil": 1000, "millon": 10**6, "millones": 10**6, "cent": 100, "cents": 100,
    "mille": 1000, "hundert": 100, "tausend": 1000,
    "ہزار": 1000, "لاکھ": 10**5, "کروڑ": 10**7, "سو": 100,
    "الف": 1000, "الاف": 1000, "مئه": 100, "مائه": 100, "مئتین": 200, "مائتین": 200,
    "خمسمائه": 500, "خمسمئه": 500, "ثلاثمائه": 300, "اربعمائه": 400, "ملیون": 10**6,
    "हज़ार": 1000, "हजार": 1000, "लाख": 10**5, "करोड़": 10**7, "सौ": 100,
}  # fmt: skip

# Words that are also ordinary words ("a", "do", "once", "sat", "sau" = Urdu "so"). Alone they are
# no amount; they count only straight before a currency word.
_WEAK = {
    "one", "ek", "aik", "do", "teen", "sat", "saath", "nau", "das", "char", "once", "un",
    "une", "ein", "eins", "uno", "dos", "tres", "mil", "cent", "cents", "dhai", "derh",
    "sadhe", "pach", "assi", "chay",
    "ایک", "دو", "نو", "اسی", "سو", "واحد", "एक", "दो", "नौ", "सौ",
}  # fmt: skip

_CONNECTORS = {"and", "aur", "y", "et", "und", "و", "اور", "और"}

# Currency words and signs: money by themselves when a number sits next to them.
_CURRENCY = {
    "usd", "eur", "gbp", "aed", "sar", "qar", "kwd", "omr", "bhd", "egp", "pkr", "inr", "bdt",
    "cad", "aud", "chf", "jpy", "cny", "dollar", "dollars", "buck", "bucks", "euro", "euros",
    "pound", "pounds", "quid", "dirham", "dirhams", "riyal", "riyals", "rial", "rials",
    "dinar", "dinars", "rupee", "rupees", "rs", "pence", "penny", "pennies", "rupay",
    "rupaye", "rupaiye", "rupya", "rupiya", "rupaya", "paisay", "paise", "paisa", "taka",
    "franc", "francs", "franken", "libra", "libras", "dolar", "dolares", "peso", "pesos",
    "yen", "yuan", "lira", "tenner", "fiver", "kr",
    "روپے", "روپیہ", "روپئے", "روپیے", "روپیا", "ڈالر", "پاؤنڈ", "درہم", "ریال", "دینار",
    "پیسے", "درهم", "دراهم", "دنانیر", "جنیه", "دولار", "دولارات", "یورو", "لیره",
    "रुपये", "रुपया", "रुपए", "डॉलर", "पैसे",
}  # fmt: skip

# Money slang that is an amount on its own, whatever stands next to it.
_SLANG = {"tenner", "fiver", "bucks", "quid"}

# Price words: an amount when only filler words stand between them and the number phrase.
_PRICE = {
    "price", "prices", "pricing", "priced", "cost", "costs", "costing", "fee", "fees",
    "charge", "charges", "charged", "rate", "rates", "quote", "quoted", "quotation", "pay",
    "paying", "paid", "payment", "amount", "total", "deposit", "discount", "budget", "cheap",
    "cheaper", "cheapest", "expensive", "monthly", "daily", "yearly", "weekly", "annual",
    "annually", "tariff", "sasta", "sasti", "mehnga", "mehngi", "qeemat", "keemat", "qimat",
    "kimat", "daam", "kharcha", "kharch", "lagat", "rakam", "raqam", "kiraya", "kirayah",
    "precio", "precios", "coste", "costo", "tarifa", "prix", "tarif", "cout", "kosten",
    "preis", "barato", "caro", "cher", "per_period", "kitne_ka",
    "قیمت", "لاگت", "فیس", "رقم", "خرچ", "خرچہ", "دام", "بجٹ", "ادائیگی", "ریٹ", "کرایہ",
    "سستا", "مہنگا", "سعر", "اسعار", "تکلفه", "رسوم", "مبلغ", "ثمن", "خصم", "دفع",
    "कीमत", "क़ीमत", "दाम", "शुल्क", "लागत", "फीस", "भुगतान",
}  # fmt: skip

# What may stand between a number phrase and its price word without breaking the link.
_FILLER = {
    "is", "are", "was", "be", "will", "would", "of", "for", "at", "it", "its", "it's", "the",
    "that", "this", "to", "only", "just", "about", "around", "roughly", "approximately",
    "approx", "in", "total", "comes", "come", "you", "us", "me", "a", "an", "each", "plus",
    "per", "or", "so", "ish", "nearly", "almost", "maybe", "like", "something",
    "ke", "ki", "ka", "ko", "ho", "hai", "hain", "hoga", "hogi", "sirf", "bas", "kareeb",
    "taqriban", "lagbhag", "tak", "se", "mein", "main", "ye", "yeh", "wo", "woh",
    "de", "la", "el", "es", "son", "est", "sont", "le", "les", "du",
    "ہے", "کے", "کا", "کی", "صرف", "تقریبا", "ہو", "ہوگا", "میں", "یہ", "وہ",
    "है", "का", "के", "की", "सिर्फ", "लगभग", "में",
}  # fmt: skip

# After a hundred-or-more phrase, these still read as the end of an amount ("a hundred or so").
_AFTER_AMOUNT = {
    "and", "or", "ish", "odd", "only", "each", "per", "for", "in", "plus", "minus", "more",
    "less", "to", "from", "up", "if", "but", "so", "total", "ke", "ki", "ka", "mein", "hai",
    "hain", "hoga", "se", "tak", "aur",
}  # fmt: skip

# A hundred or more directly after one of these is a label or a count, not money.
_LABEL_BEFORE = {
    "part", "step", "chapter", "number", "no", "num", "page", "question", "option", "level",
    "phase", "stage", "point", "item", "rule", "article", "section", "book", "tip", "idea",
    "problem", "line", "row", "figure", "room", "gate", "route", "bus", "flight", "nambar",
    "sawal", "masla", "hissa", "qadam", "marhala", "class", "grade", "version", "v",
    "نمبر", "حصہ", "قدم", "مرحلہ", "سوال", "مسئلہ", "صفحہ",
}  # fmt: skip


_BOUNDARY = "\x00"  # a clause boundary token


def _build(table: dict[str, int]) -> dict[str, int]:
    return {fold(k): v for k, v in table.items()}


_VALUE = {**_build(_UNITS), **_build(_SCALES)}
_SCALE_WORDS = frozenset(_build(_SCALES))
_WEAK_SET = frozenset(fold(w) for w in _WEAK)
_CONNECTOR_SET = frozenset(fold(w) for w in _CONNECTORS)
_CURRENCY_SET = frozenset(fold(w) for w in _CURRENCY)
_SLANG_SET = frozenset(fold(w) for w in _SLANG)
_PRICE_SET = frozenset(fold(w) for w in _PRICE)
_FILLER_SET = frozenset(fold(w) for w in _FILLER)
_AFTER_SET = frozenset(fold(w) for w in _AFTER_AMOUNT)
_LABEL_SET = frozenset(fold(w) for w in _LABEL_BEFORE)
_PERIOD_UNITS = frozenset(
    "hour day week month year item unit page person head user seat session visit".split()
)
# Glued words ("fivehundred", "panchsau"): only the safe (not weak, 3+ letter) words may join.
_GLUE = sorted(
    (w for w in _VALUE if w.isascii() and len(w) >= 3 and w not in _WEAK_SET),
    key=len,
    reverse=True,
)


def _tokens(text: str) -> list[str]:
    """Folded word tokens; clause ends become a boundary token; "per month" is one token."""
    raw: list[str] = []
    for part in re.finditer(r"[\wऀ-ॿ']+|[%.!?;:\n؟۔।]", fold(text)):
        piece = part.group(0)
        if piece in ".!?;:\n؟۔।":
            raw.append(_BOUNDARY)
        else:
            raw.extend(p for p in piece.replace("_", " ").split() if p)
    out: list[str] = []
    i = 0
    while i < len(raw):
        tok = raw[i]
        nxt = raw[i + 1] if i + 1 < len(raw) else ""
        if tok == "per" and nxt in _PERIOD_UNITS:
            out.append("per_period")
            i += 2
        elif tok == "per" and nxt == "cent":
            out.append("percent")
            i += 2
        elif tok == "kitne" and nxt in {"ka", "ke", "ki"}:
            out.append("kitne_ka")
            i += 2
        elif tok in _VALUE or tok.isdigit() or tok in _SLANG_SET:
            out.append(tok)
            i += 1
        else:
            glued = _split_glued(tok)
            out.extend(glued if glued else [tok])
            i += 1
    return out


def _split_glued(token: str) -> list[str] | None:
    """ "fivehundred" -> ["five", "hundred"] when the whole token is number words (2 or more)."""
    if not token.isascii() or len(token) < 6 or token in _VALUE:
        return None
    parts: list[str] = []
    rest = token
    while rest:
        for word in _GLUE:
            if rest.startswith(word):
                parts.append(word)
                rest = rest[len(word) :]
                break
        else:
            return None
    return parts if len(parts) >= 2 else None


def _is_number(tok: str) -> bool:
    return tok in _VALUE or tok.isdigit()


def _phrases(tokens: list[str]) -> list[tuple[int, int]]:
    """(start, end) spans of consecutive number tokens, "and" bridging two of them."""
    spans: list[tuple[int, int]] = []
    i = 0
    while i < len(tokens):
        if not _is_number(tokens[i]):
            i += 1
            continue
        j = i + 1
        while j < len(tokens):
            if _is_number(tokens[j]):
                j += 1
            elif tokens[j] in _CONNECTOR_SET and j + 1 < len(tokens) and _is_number(tokens[j + 1]):
                j += 2
            else:
                break
        spans.append((i, j))
        i = j
    return spans


# "which of these two costs you most": a price VERB straight after a count is not an amount.
_VERBS = frozenset({"cost", "costs", "costing", "charge", "charges", "pay", "pays", "matter"})


def _linked(tokens: list[str], start: int, end: int, targets: frozenset[str]) -> bool:
    """A target word within three filler-only tokens before ``start`` or after ``end``."""
    gap = 0
    for k in range(end, len(tokens)):
        if tokens[k] in targets and not (tokens[k] in _VERBS and k == end):
            return True
        if tokens[k] not in _FILLER_SET or (gap := gap + 1) > 3:
            break
    gap = 0
    for k in range(start - 1, -1, -1):
        if tokens[k] in targets:
            return True
        if tokens[k] not in _FILLER_SET or (gap := gap + 1) > 3:
            break
    return False


def _currency_adjacent(tokens: list[str], start: int, end: int) -> bool:
    after = tokens[end] if end < len(tokens) else ""
    before = tokens[start - 1] if start > 0 else ""
    return after in _CURRENCY_SET or before in _CURRENCY_SET


def _grand(tokens: list[str]) -> bool:
    """ "a grand", "half a grand", "two grand" as money, not "a grand idea"."""
    for i, tok in enumerate(tokens):
        if tok != "grand":
            continue
        before = tokens[i - 1] if i else ""
        nxt = tokens[i + 1] if i + 1 < len(tokens) else _BOUNDARY
        counted = before in {"a", "half", "few", "couple", "several", "another"} or _is_number(
            before
        )
        if counted and (nxt == _BOUNDARY or nxt in _AFTER_SET or nxt in _CURRENCY_SET):
            return True
    return False


def has_amount(text: str) -> bool:
    """True when ``text`` states an amount of money in number words or money slang."""
    tokens = _tokens(text)
    if any(tok in _SLANG_SET for tok in tokens) or _grand(tokens):
        return True
    for start, end in _phrases(tokens):
        words = tokens[start:end]
        if all(w.isdigit() for w in words):
            continue  # plain digits are the digit rules' business
        before = tokens[start - 1] if start else _BOUNDARY
        after = tokens[end] if end < len(tokens) else _BOUNDARY
        if before in _LABEL_SET:
            continue
        weak_only = all(w in _WEAK_SET or w.isdigit() for w in words)
        if _currency_adjacent(tokens, start, end):
            if weak_only and len(words) == 1 and after not in _CURRENCY_SET:
                continue  # "ek paise" after a number-less word: too ambiguous
            return True
        if weak_only:
            continue
        if _linked(tokens, start, end, _PRICE_SET):
            return True
        big = any(w in _SCALE_WORDS for w in words)
        if big and (after == _BOUNDARY or after in _AFTER_SET):
            return True
    return False


def variant_digits(text: str) -> bool:
    """Two or more superscript, circled or other compatibility digits in a row ("¹⁰⁰", "①⓪⓪")."""
    run = 0
    for ch in text:
        if (ch.isdigit() and not ch.isdecimal()) or (
            not ch.isascii()
            and not ch.isdecimal()
            and unicodedata.normalize("NFKC", ch).isdecimal()
        ):
            run += 1
            if run >= 2:
                return True
        else:
            run = 0
    return False
