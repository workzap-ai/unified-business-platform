"""L2-3: text folding and the patterns the blueprint rules scan with. Pure, no database.

The shared regexes (`constitution.PROMISE`, `brain_docs.MONEY_IN_TEXT`) are kept and still run, but
they miss ordinary spellings: letters spaced out, zero-width characters, look-alike letters, digits
in another script, a currency glued to its figure, numbers written as words. This module folds the
text first and adds patterns in English, Roman Urdu, Urdu, Hindi and Arabic. It only ever widens
what is caught; a text the old patterns catch is still caught.

`views(text)` gives the text as written, folded, and folded with spaced-out letters or digits
joined. A pattern matches if it matches any view.
"""

from __future__ import annotations

import math
import re
import unicodedata

# Copies of `brain_docs.MONEY_IN_TEXT` (brain_docs.py:60) and `brain_docs.WILL` (brain_docs.py:69),
# kept here because importing brain_docs pulls the database layer into a pure module and would
# make a cycle once brain_docs calls the blueprint rules. A unit test asserts they are identical.
MONEY_IN_TEXT = re.compile(
    r"\b(?:rs\.?|pkr|aed|cad|usd|dirhams?|rupees?|lakhs?|crores?)\b|[$€£₹]"
    r"|\b\d{1,3}(?:,\d{2,3})+(?:\.\d+)?\b"
    r"|\b\d+(?:\.\d+)?\s?(?:k|m|lakh|lac|crore|million|thousand)\b"
    r"|\b(?:cost|costs|price|priced|fee|fees|charge|charged|budget|pay|paying)\b\D{0,15}\d{3,}",
    re.IGNORECASE,
)
WILL = re.compile(r"\bwill\b(?! not)", re.IGNORECASE)

# An option field is a sentence or two. A longer text is refused by the rules (MALFORMED), and the
# patterns only ever run on the first MAX_TEXT characters, so no input can make them slow.
MAX_TEXT = 1000

# --- folding -------------------------------------------------------------------------------------

_INVISIBLE = dict.fromkeys(
    map(
        ord,
        "​‌‍‎‏‪‫‬‭‮⁠⁡⁢⁣⁦⁧⁨⁩؜﻿­᠎͏",
    )
)
# look-alike letters (Cyrillic, Greek) to Latin, and the Arabic-script letter variants to one form
_LOOKALIKE = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j",
        "ѕ": "s", "һ": "h", "ԁ": "d", "ɡ": "g", "к": "k", "м": "m", "т": "t", "ӏ": "l",
        "α": "a", "ε": "e", "ο": "o", "ρ": "p", "ι": "i", "κ": "k", "ν": "v", "τ": "t", "υ": "u",
        "ي": "ي", "ى": "ي", "ی": "ي", "ې": "ي", "ے": "ي", "ك": "ك", "ک": "ك", "ہ": "ه", "ھ": "ه",
        "ة": "ه", "ۃ": "ه", "ٱ": "ا", "ँ": "ं",
    }
)  # fmt: skip
# combining marks: Latin accents, Arabic points, the Devanagari nukta
_MARKS = re.compile("[̀-ًͯ-ٰٟـۖ-़ۭ]")
_LOOKALIKE[0x066A] = "%"  # the Arabic percent sign
_SPACED_RUN = re.compile(r"(?<![^\W_])(?:[^\W_][ \-_.*]){2,}[^\W_](?![^\W_])")
_SEPARATOR = re.compile(r"[ \-_.*]")
_HYPHEN_BREAK = re.compile(r"-[ \t]*[\r\n]+[ \t]*")
_CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")
_ZERO_AS_O = re.compile(r"(?<![^\W_])\d[\do]{2,}(?![^\W_])")


def _ascii_digits(text: str) -> str:
    """Arabic-Indic, Devanagari and full-width digits become ASCII digits."""
    return "".join(
        str(unicodedata.decimal(ch)) if ch.isdecimal() and not ch.isascii() else ch for ch in text
    )


def fold(text: str) -> str:
    """The text as plain lower-case: compatibility forms, invisible and bidi marks, accents and
    Arabic points, other-script digits and look-alike letters all folded away."""
    s = unicodedata.normalize("NFKD", str(text))
    s = _HYPHEN_BREAK.sub("", s)  # a word broken across lines: "guaran-\nteed"
    s = s.translate(_INVISIBLE)
    s = _ascii_digits(s)
    s = s.casefold().translate(_LOOKALIKE)
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = _MARKS.sub("", s)
    s = _ZERO_AS_O.sub(lambda m: m.group(0).replace("o", "0"), s)  # 5OOOO
    return " ".join(s.split())


def _join_runs(folded: str) -> str:
    """Letters or digits spaced out one by one ("g u a r a n t e e d", "5 0 0 0 0", "r s 5 0 0 0")
    are joined."""
    return _SPACED_RUN.sub(lambda m: _SEPARATOR.sub("", m.group(0)), folded)


def views(text: str) -> tuple[str, ...]:
    """The text as written, folded, and folded with spaced-out letters and digits joined; the same
    again with tabs and control characters taken out ("guar<tab>anteed")."""
    raw = str(text)[:MAX_TEXT]
    seen: list[str] = []
    for base in (raw, _CONTROL.sub("", raw)):
        folded = fold(base)
        for view in (base, folded, _join_runs(folded)):
            if view not in seen:
                seen.append(view)
    return tuple(seen)


def _alt(words: str) -> str:
    """An alternation of folded words, longest first."""
    items = sorted({fold(w) for w in words.split()}, key=len, reverse=True)
    return "|".join(re.escape(w) for w in items)


def _word(body: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![^\W\d_])(?:{body})(?![^\W\d_])")


# --- promises ------------------------------------------------------------------------------------

_PROMISE_WORDS = (
    # English
    "guarantee guarantees guaranteed guaranteeing guaranty promise promises promised promising "
    "assure assures assured assurance swear swore sworn ensures certainly definitely surely "
    "undoubtedly doubtless certainty unfailing foolproof infallible "
    # Roman Urdu / Hindi in Latin letters
    "zaroor zarur zaror jarur jaroor lazmi lazmy pakka pakki pukka yaqeen yaqeeni yakeen yakini "
    "yaqini yaqeenan yaqinan yakinan zamanat shartiya shartia shartiyah bilashuba bilashak "
    # Hindi
    "गारंटी गारण्टी पक्का पक्की ज़रूर जरूर यकीनन निश्चित निश्चय अवश्य शर्तिया हमेशा सुनिश्चित"
)
_PROMISE_ARABIC = (
    "ضمان ضمانت ضمانة مضمون مضمونة یقینی یقین یقیناً ضرور پکا پکی ہمیشہ شرطیہ حتما حتماً "
    "بالتاکید بالتأكيد مؤكد مؤكدة اكيد أكيد"
)
_PROMISE_PHRASES = (
    r"(?:is|are|be|been|it's|its|that's)\s+certain",
    r"certain\s+(?:to|that|of)",
    r"for\s+sure",
    r"sure\s+to\b",
    r"no\s+doubt",
    r"without\s+(?:any\s+)?fail",
    r"(?:works?|work)\s+every\s+(?:single\s+)?time",
    r"every\s+single\s+time",
    r"always\s+(?:work|works|deliver|delivers|succeed|succeeds|help|helps|fix|fixes)",
    r"(?:100|hundred|one\s+hundred|a\s+hundred)\s?(?:%|percent|per\s?cent)",
    r"no\s+risk",
    r"risk\s?-?\s?free",
    r"zero\s+(?:risk|chance|doubt)",
    r"bina\s+kisi\s+risk",
    r"koi\s+risk\s+nahi",
    r"zaroor\s+\w+",
    r"pakka\s+\w+",
    # never fails, cannot fail, won't fail, you can't lose, no chance of failure
    r"(?:never|cannot|can't|can\s+not|can\s+never|will\s+never|won't|wont|will\s+not|doesn't"
    r"|does\s+not)\s+(?:possibly\s+)?(?:fail|fails|failed|failing|go\s+wrong|goes\s+wrong|backfire"
    r"|let\s+you\s+down)",
    r"(?:never|cannot|can't|can\s+not|can\s+never|won't)\s+lose",
    r"no\s+(?:chance|possibility|way)\s+(?:of|to)\s+(?:fail\w*|los\w+|go\w*\s+wrong)",
    r"bound\s+to\b",
    r"proven\s+to\b",
    r"proven\s+(?:results|track\s+record)",
    r"sure\s+(?:thing|bet|win|fire)",
    r"without\s+(?:a\s+)?doubt",
    r"beyond\s+(?:a\s+)?(?:doubt|question)",
    r"absolutely\s+(?:work|works|will|safe|certain|sure|no|nothing|everything)",
    r"trust\s+me",
    r"i\s+swear",
    r"(?:mark|believe)\s+my\s+words?",
    r"(?:going\s+to|gonna)\s+(?:boost|increase|double|triple|grow|improve|fix|raise|cut|save|reduce"
    r"|bring|solve|transform|multiply|skyrocket|work|help|succeed)",
    r"expect\s+(?:\w+\s+){0,2}to\s+(?:double|triple|quadruple|increase|grow|boost|save|cut|reduce"
    r"|multiply|gain)",
    # Roman Urdu / Hindi in Latin letters
    r"kabhi\s+(?:bhi\s+)?(?:fail|nakam|nakaam|ghalat)\w*",
    r"hamesha\s+(?:kaam|chal|theek|sahi|kamyab|work|successful|safe)\w*",
    r"bina\s+(?:kisi\s+)?(?:shak|shuba|shubah|risk|khatra|dar)\b",
    r"(?:sau|100)\s?(?:percent|per\s?cent|fisad|feesad|fi\s?sad|%)",
    r"(?:koi\s+)?(?:khatra|risk)\s+nahi(?:n)?",
    # Urdu
    r"بلا\s+شبه",
    r"بغیر\s+کسی\s+(?:خطر\w*|شک|شبہ|رسک)",
    r"(?:کوئی\s+)?خطر[ہے]\s+نہیں",
    r"سو\s+(?:فیصد|فی\s?صد|پرسنٹ)",
    r"کبھی\s+(?:بھی\s+)?(?:ناکام|فیل|ناکامی)\w*\s+نہیں",
    r"ہر\s+بار\s+(?:کام|کامیاب)\w*",
    # Hindi
    r"जोखिम\s+नहीं",
    r"बिना\s+(?:किसी\s+)?(?:जोखिम|शक|संदेह)",
    r"(?:सौ|100)\s?प्रतिशत",
    r"कभी\s+(?:भी\s+)?(?:फेल|असफल|नाकाम)\s+नहीं",
    # Arabic
    r"من\s+دون\s+مخاطر",
    r"بدون\s+مخاطر",
    r"لا\s+مخاطر\w*",
    r"(?:مئة|مائة)\s+(?:بال|في\s+ال)(?:مئة|مائة)",
    r"لن\s+(?:يفشل|تفشل)",
    r"(?:دائما|دايما|دوما)\s+(?:ينجح|تنجح|يعمل|تعمل|نجاح|مضمون)",
    r"(?:بلا|بدون)\s+شك",
    r"بكل\s+تأكيد",
    r"س(?:وف\s+)?(?:يزيد|يرفع|يضاعف|يحسن|يوفر|ينجح|تزيد|ترفع|تضاعف|تحسن|توفر|تنجح)\w*",
)
_ARABIC_PREFIX = "|".join(
    fold(p) for p in ("وال", "بال", "فال", "كال", "لل", "ال", "و", "ب", "ف", "ك", "ل")
)
PROMISE_EXTRA = re.compile(
    "|".join(
        [
            rf"(?<![^\W\d_])(?:{_alt(_PROMISE_WORDS)})(?![^\W\d_])",
            rf"(?<![؀-ۿ])(?:{_ARABIC_PREFIX})?(?:{_alt(_PROMISE_ARABIC)})(?![؀-ۿ])",
        ]
        + [rf"(?<![^\W\d_]){fold(p)}(?![^\W\d_])" for p in _PROMISE_PHRASES]
    )
)

# A guarantee that is denied is not a promise: "I can't guarantee anything", "not guaranteed",
# "no guarantee it will work", "guarantee nahi de sakta", "یقینی نہیں ہے". The denial and the rest
# of its clause are cut out before the promise patterns run (the clause ends at a comma, a full
# stop, or "but", "however", "and"), so "no guarantee, but it will definitely work" still flags.
_NEG_LEAD = (
    r"(?:\w+n't|cannot|can\s+not|will\s+not|do\s+not|does\s+not|did\s+not|could\s+not|would\s+not"
    r"|is\s+not|are\s+not|was\s+not|not|never|no|nothing|none|nobody|hardly|without|nor)"
)
_NEG_TERM = (
    r"(?:guarantee|guaranteed|guarantees|guaranty|promise|promised|promises|assure|assured"
    r"|assurance|ensure|ensured|certain|certainty|certainly|sure|definite|definitely|proven)"
)
_NEG_GAP = r"(?:(?!(?:risk|doubt|chance|fail\w*)\b)\w+\s+){0,3}?"
_REST = r"(?:(?!\s(?:but|however|yet|though|although|still|and)\b)[^.;!?,\n])*"
_REST_X = r"(?:(?!\s(?:lekin|magar|par|aur|لیکن|مگر|اور|लेकिन|मगर|और|لكن|لكنه))[^.;!?,،؟۔\n])*"
_NEG_OTHER = (
    r"(?:guarantee|zamanat|yaqeen|yakeen|yaqeeni|yakini|pakka|pakki|promise|wada|waada|certain)"
    rf"\s+(?:\w+\s+){{0,2}}?nahi\w*{_REST_X}",
    r"(?:ضمانت|ضمان|یقین|یقینی|پکا|پکی|وعدہ|وعده)\s+(?:\w+\s+){0,2}?نہیں" + _REST_X,
    r"(?:गारंटी|वादा|यकीन|पक्का|पक्की|निश्चित)\s+(?:\w+\s+){0,2}?नहीं" + _REST_X,
    r"(?:لا|ليس|غير|بدون|بلا)\s+(?:\w+\s+){0,2}?"
    r"(?:نضمن|[اأ]ضمن|يضمن|تضمن|ضمان\w*|مضمون\w*|مؤكد\w*|اكيد\w*|مؤكدا)" + _REST_X,
    r"لا\s+(?:يمكنني\s+ضمان|استطيع\s+ضمان|اعد|اعدك|اوعد)\w*" + _REST_X,
)
_NEGATED = re.compile(
    "|".join(
        [rf"(?<![^\W\d_]){_NEG_LEAD}\s+{_NEG_GAP}{_NEG_TERM}(?![^\W\d_]){_REST}"]
        + [q for p in _NEG_OTHER for q in (p, fold(p))]
    ),
    re.IGNORECASE,
)


def promise_in(text: str, *patterns: re.Pattern[str]) -> bool:
    """True when any view of the text, with denied guarantees cut out, matches the extra promise
    patterns, an invented outcome or saving, or any of `patterns`."""
    for view in views(text):
        kept = _NEGATED.sub(" ", view)
        if any(rx.search(kept) for rx in (PROMISE_EXTRA, OUTCOME_CLAIM, *patterns)):
            return True
    return False


# --- money ---------------------------------------------------------------------------------------

_CURRENCY_CODES = "rs pkr aed cad usd eur gbp inr sar"
_CURRENCY_WORDS = (
    "rs pkr aed cad usd eur gbp inr sar dollar dollars euro euros buck bucks pound pounds "
    "rupee rupees rupay rupaye rupiya rupye rupiye dirham dirhams riyal riyals "
    "روپے روپیہ روپیے روپے ریال درهم دراهم دولار يورو جنيه "
    "रुपये रुपया रुपए रुपैया"
)
_SYMBOLS = "[$€£₹¥₨]"
_MAGNITUDES = (
    "thousand thousands lakh lakhs lac lacs lak laak laakh laakhs crore crores karor million "
    "millions billion grand hundred hundreds sau sou hazar hazaar hajar hajaar "
    "لاکھ ہزار کروڑ ملین الف ألف آلاف الاف ألاف مليون مليار مئة مائة "
    "लाख हज़ार हजार करोड़ करोड मिलियन सौ"
)
_NUMBER_WORDS = (
    # English
    "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety "
    "hundred "
    # Roman Urdu
    "ek aik do teen char chaar paanch panch paanchh chhe chay saat aath nau das dus gyarah barah "
    "pandrah bees pachis pachees tees chalis pachas pachaas saath sattar assi nabbe sau "
    # Urdu
    "ایک دو تین چار پانچ چھ سات آٹھ نو دس بیس تیس چالیس پچاس ساٹھ ستر اسی نوے سو "
    # Hindi
    "एक दो तीन चार पाँच पांच छह सात आठ नौ दस बीस तीस चालीस पचास साठ सत्तर अस्सी नब्बे सौ "
    # Arabic
    "واحد اثنان اثنين ثلاثة ثلاث اربعة اربع خمسة خمس ستة ست سبعة سبع ثمانية ثماني تسعة تسع "
    "عشرة عشر عشرين ثلاثين اربعين خمسين ستين سبعين ثمانين تسعين مئة مائة ميه نصف "
    # fractions and articles that start a magnitude
    "half a an"
)
_N = _alt(_NUMBER_WORDS)
_MAG = _alt(_MAGNITUDES)
_CUR = _alt(_CURRENCY_WORDS)
_CODES = _alt(_CURRENCY_CODES)
_PRICE_WORDS = (
    "fee fees cost costs price prices priced pricing charge charges charged budget pay paying rate "
    "rates kharcha kharch qeemat keemat قیمت رقم لاگت خرچ خرچہ कीमत दाम سعر تكلفة ثمن"
)

MONEY_EXTRA = re.compile(
    # a currency code glued to or before a figure: "PKR50000", "Rs500", "usd 20"
    rf"(?<![^\W\d_])(?:{_CODES})\.?\s*\d"
    # a figure before a currency word: "500 dollars", "50000 rupay", "300 eur"
    rf"|(?<!\d)\d[\d.,]*\s*(?:{_CUR})(?![^\W\d_])"
    # a currency word before a figure
    rf"|(?<![^\W\d_])(?:{_CUR})\.?\s*\d"
    # symbols
    rf"|{_SYMBOLS}"
    # a figure with a magnitude: "5L", "5 lakh", "1.5m", "5 cr", "3 hazar", "5 lak"
    rf"|(?<![^\W\d_])(?<!\d)\d+(?:\.\d+)?\s?(?:k|l|m|cr|{_MAG})(?![^\W\d_])"
    # number words with a magnitude: "five hundred thousand", "fifty-thousand", "half a million",
    # "paanch hazaar", "two hundred", "five grand", "پانچ لاکھ", "पाँच लाख", "خمسة آلاف"
    rf"|(?<![^\W\d_])(?:{_N})(?:[\s-]+(?:{_N}|and)){{0,4}}[\s-]+(?:{_MAG})(?![^\W\d_])"
    # a magnitude with a currency word: "thousand rupees", "ألف ريال"
    rf"|(?<![^\W\d_])(?:{_MAG})[\s-]+(?:{_CUR})(?![^\W\d_])"
    # a number word with a currency word: "paanch sau rupay"
    rf"|(?<![^\W\d_])(?:{_N})[\s-]+(?:{_CUR})(?![^\W\d_])"
    # an amount followed by the old "/-": "3000/-"
    r"|(?<!\d)\d[\d,]*\s?/-"
    # grouped figures: 5,00,000 and 50 000
    r"|(?<![\d,.])\d{1,3}(?:,\d{2,3})+(?![\d])|(?<![\d,.])\d{1,3}(?: \d{3})+(?![\d])"
    # a figure of three or more digits near a price word
    rf"|(?<![^\W\d_])(?:{_alt(_PRICE_WORDS)})\w*\D{{0,15}}\d{{3,}}"
)

# A cost claim is money talk too: only staff says what a thing costs or that it is free.
_COST_CLAIMS = (
    r"free\s+of\s+charge",
    r"(?:at|for)\s+no\s+(?:cost|charge|extra|fee)\w*",
    r"no\s+(?:cost|charge|fee|fees|extra\s+(?:cost|charge))",
    r"zero\s+(?:cost|fee|fees|charge|charges)",
    r"costs?\s+nothing",
    r"for\s+free",
    r"(?:completely|totally|absolutely|entirely|100\s?%)\s+free",
    r"free\s+(?:forever|for\s+life)",
    r"without\s+(?:any\s+)?(?:cost|charge|fee)",
    r"gratis",
    r"low[\s-]?cost",
    r"cheap\w*",
    r"inexpensive",
    r"affordabl\w+",
    r"cost[\s-]?effective",
    r"budget[\s-]?friendly",
    # Roman Urdu
    r"(?:bilkul\s+)?(?:muft|mufat)",
    r"kam\s+(?:kharcha|kharch|qeemat|keemat|paisay|paise|lagat)",
    r"sast[aiey]\w*",
    r"bina\s+(?:kisi\s+)?(?:kharch\w*|paisay|paise)",
    r"koi\s+(?:kharch\w*|fees?)\s+nahi\w*",
    # Urdu
    r"مفت",
    r"کم\s+خرچ\w*",
    r"سست[ای]",
    r"بغیر\s+خرچ\w*",
    r"کوئی\s+(?:خرچ|فیس)\w*\s+نہیں",
    # Hindi
    r"मुफ़्त",
    r"मुफ्त",
    r"बिना\s+(?:खर्च|पैसे|शुल्क)",
    r"कम\s+खर्च",
    r"सस्त[ाी]",
    r"कोई\s+खर्च\s+नहीं",
    # Arabic
    r"مجان\w+",
    r"بدون\s+تكلف\w+",
    r"بلا\s+(?:مقابل|تكلف\w+)",
    r"رخيص\w*",
    r"تكلف[ةه]\s+منخفض\w*",
)
_COST_CLAIMS_MORE = (
    # English: "Free for the first year", "It is free of cost", "Costs less than a clerk"
    r"(?<!feel\s)free(?![-\w])(?!\s+(?:up|from|time|space|hand|to\s+(?:say|choose|decline"
    r"|leave|stop|cancel|ask|change|skip)))",
    r"costs?\s+(?:much\s+|far\s+|a\s+lot\s+)?(?:less|lower|fewer)\s+than",
    r"cheaper|less\s+expensive|more\s+affordable|lower\s+(?:cost|price)",
    r"(?:less|lower)\s+(?:cost|price|fee)\w*",
    # Roman Urdu
    r"(?:kharch\w*|fees?|charge\w*)\s+(?:\w+\s+){0,2}?nahi\s+(?:ho|lag|aay)\w*",
    r"nahi\s+lagega",
    r"(?:paisa|paise|paisay)\s+wasool",
    r"free\s+(?:hai|hoga|me|mein)",
    # Urdu
    r"(?:خرچ|خرچہ|فیس|چارج)\w*\s+(?:\w+\s+){0,2}?نہیں\s+(?:ہو|لگ|آئ)\w*",
    r"پیس[ہے]\s+وصول",
    r"(?:بغیر|بنا)\s+(?:کسی\s+)?(?:فیس|چارج|خرچ)\w*",
    # Hindi
    r"(?:खर्च|शुल्क|फीस|चार्ज)\w*\s+(?:\w+\s+){0,2}?नहीं\s+(?:हो|लग|आ)\w*",
    r"पैस[ाे]\s+वसूल",
    r"बिना\s+(?:किसी\s+)?(?:फीस|चार्ज|खर्च|शुल्क)",
    # Arabic
    r"لا\s+(?:تكلف\w+|رسوم|يوجد\s+رسوم|مقابل)",
    r"(?:بدون|بلا)\s+(?:رسوم|اي\s+رسوم|مقابل|اي\s+تكلف\w+)",
    r"(?:اقل|ارخص)\s+(?:تكلف\w+|سعرا|من)",
    r"تكلف[ةه]\s+اقل",
)
COST_CLAIM = re.compile(
    "|".join(rf"(?<![^\W\d_]){fold(p)}(?![^\W\d_])" for p in (*_COST_CLAIMS, *_COST_CLAIMS_MORE)),
    re.IGNORECASE,
)

_UNITS = (
    r"(?:hours?|hrs?|minutes?|mins?|days?|weeks?|months?|years?|%|percent|per\s?cent|times|fold)"
)
_QTY = (
    rf"(?:(?:\d[\d.,]*|{_N})\s?-?\s?{_UNITS}(?![^\W\d_])|half(?![^\W\d_])|twice(?![^\W\d_])"
    r"|(?:a\s+)?(?:third|quarter|fifth)(?![^\W\d_])|%)"
)
_OUTCOMES = (
    # saves two hours a day, cuts your costs in half, reduce missed orders by 30%
    rf"(?:sav(?:e|es|ed|ing|ings)|cut|cuts|cutting|reduc(?:e|es|ed|ing)|halv(?:e|es|ed|ing)"
    rf"|slash(?:es|ed|ing)?|trim(?:s|med|ming)?|lower(?:s|ed|ing)?|shrink(?:s|ing)?"
    rf"|speed(?:s|ed|ing)?\s+up)(?![^\W\d_])[^.;!?]{{0,40}}?{_QTY}",
    # double your sales, triple your revenue
    r"(?:double|doubles|doubled|doubling|triple|triples|tripled|tripling|quadruple\w*"
    r"|multipl(?:y|ies|ied|ying))\s+(?:your|the|our|its|their|my|sales|revenue|profits?|orders"
    r"|customers|income|growth|turnover|bookings|leads)(?![^\W\d_])",
    # halves your costs
    r"(?:halve|halves|halved|halving)\s+(?:your|the|our)\s+(?:costs?|time|wait\w*|expenses|workload"
    r"|bills?)(?![^\W\d_])",
    # 10x your revenue, five times more
    r"\d+(?:\.\d+)?\s?x(?![^\W\d_])(?!\d)",
    rf"(?:{_N})\s+times\s+(?:more|as|your|the|higher|faster|better|bigger)(?![^\W\d_])",
    # 20% more orders
    r"(?:%|percent|per\s?cent)\s+(?:more|fewer|less|higher|lower|faster|better|extra|bigger"
    r"|growth|increase|decrease|boost|uplift|reduction|savings?)(?![^\W\d_])",
    # ROI within a month, pays for itself
    r"(?:roi|return\s+on\s+investment|pay(?:s|ing)?\s+(?:back\s+)?for\s+itself|pay\s?back"
    r"|break[\s-]?even|recoup\w*)(?![^\W\d_])",
    # boosts sales
    r"(?:increase|increases|boost|boosts|grow|grows|raise|raises|lift|lifts)\s+(?:your\s+|the\s+"
    r"|our\s+)?(?:sales|revenue|profits?|income|orders|conversions|bookings|growth|turnover"
    r"|customers)(?![^\W\d_])",
)


def _fx(pattern: str) -> str:
    """Fold the literal parts of a pattern, never its escapes: `fold` would lower-case `\\W`."""
    return re.sub(
        r"(\\.)|([^\\]+)",
        lambda m: m.group(1) or (fold(m.group(2)) if m.group(2).strip() else m.group(2)),
        pattern,
    )


# Roman Urdu, Urdu, Hindi and Arabic: the same classes as above, built from word lists, so a
# saving, a rise, a doubling or a "free" is caught in any of the five languages.
_SAVE_X = _alt(
    "bachat bachte bachta bachti bachega bachegi bachenge bachayega bachayegi "
    "بچت بچتے بچتا بچتی بچیں बचत बचते बचता बचती बचेगा बचेंगे "
    "يوفر توفر وفر توفير يختصر تختصر اختصار يقلل تقلل تقليل يخفض تخفض خفض تخفيض يقلص تقلص"
)
_UNITS_X = _alt(
    "ghanta ghante ghantay ghanton minute minutes din dinon hafta haftay hafte mahina mahine "
    "mahinay saal roz rozana waqt "
    "گھنٹے گھنٹہ گھنٹا گھنٹوں منٹ دن ہفتہ ہفتے مہینہ مہینے سال روزانہ وقت "
    "रोज़ रोज रोजाना घंटे घंटा घंटों मिनट दिन हफ्ता हफ्ते महीना महीने साल समय "
    "ساعة ساعات ساعتين دقيقة دقائق يوم يوميا ايام اسبوع اسبوعيا شهر شهريا سنة الوقت"
)
_COSTN_X = _alt(
    "kharcha kharch kharche lagat qeemat keemat paisa paise paisay rupay rupaye "
    "خرچ خرچہ لاگت قیمت پیسے روپے खर्च लागत कीमत पैसे रुपये التكلفة تكلفة المصاريف المال"
)
_HALF_X = _alt("aadha aadhi adha adhi aadhe adhe نصف آدھا آدھی आधा आधी आधे النصف")
_MORE_X = _alt("zyada ziyada zyadah izafa اضافہ زیادہ مزید ज़्यादा ज्यादा अधिक")
_BIZ_X = _alt(
    "order orders sales sale customers customer munafa profit income revenue gahak bikri "
    "آرڈر آرڈرز سیلز گاہک منافع آمدنی बिक्री ऑर्डर ग्राहक मुनाफ़ा मुनाफा आमदनी "
    "الطلبات المبيعات العملاء الارباح الايرادات"
)
_DOUBLE_X = _alt(
    "dugna dugni dugne tigna دگنا دگنی دوگنا دوگنی تگنا दोगुना दोगुनी दुगना दुगनी तिगुना "
    "مضاعفة يضاعف تضاعف ضاعف"
)
_DO = r"(?:ho|kar|hojaye|ہو|کر|हो|कर)"
_PCT_X = (
    r"(?:%|fisad|feesad|fi\s?sad|percent|per\s?cent|فیصد|فی\s?صد|پرسنٹ|प्रतिशत|फीसदी"
    r"|بالمئة|في\s+المئة)"
)
_QTY_X = rf"(?:\d[\d.,]*|{_N})\s?-?\s?(?:{_UNITS_X}|{_PCT_X})(?![^\W\d_])"
_OUTCOMES_X = (
    # is se roz do ghante bachte hain, يوفر ساعتين يوميا (a saving verb with a quantity or unit)
    rf"(?:{_SAVE_X})(?![^\W\d_])[^.;!?]{{0,40}}?(?:{_QTY_X}|{_UNITS_X}|{_COSTN_X}|{_HALF_X}|%)",
    # اس سے روزانہ دو گھنٹے بچتے ہیں (the quantity first)
    rf"(?:{_QTY_X}|{_HALF_X})[^.;!?]{{0,25}}?(?:{_SAVE_X})(?![^\W\d_])",
    # waqt bachega, paise bachenge, وقت بچے گا, समय बचेगा (the thing saved first)
    rf"(?:{_UNITS_X}|{_COSTN_X})[^\s.;!?,]*\s+(?:[^\s.;!?,]+\s+){{0,2}}?"
    rf"(?:{_SAVE_X}|بچے\s+گ[اےی])",
    # orders barh jayenge, sales बढ़ेंगी
    rf"(?:{_BIZ_X})[^\s.;!?,]*\s+(?:[^\s.;!?,]+\s+){{0,3}}?(?:barh|badh|بڑھ|बढ़|बढ)[^\s.;!?,]*",
    # لا توجد اي رسوم
    r"لا\s+(?:توجد|يوجد)\s+(?:اي\s+)?(?:رسوم|تكلف\w+)",
    # bachat hogi
    r"(?:bachat|بچت|बचत)\s+(?:hogi|hoga|hoti|ho\s+gi|ہوگی|ہو\s+گی|ہوتی|होगी|होगा|होती)",
    # kharcha aadha ho jayega, خرچ آدھا ہو جائے گا, खर्च आधा हो जाएगा
    rf"(?:{_COSTN_X}|{_UNITS_X})[^\s.;!?,]*\s+(?:[^\s.;!?,]+\s+){{0,3}}?"
    rf"(?:{_HALF_X}|(?:kam|کم|कम)\s+{_DO}[^\s.;!?,]*)",
    rf"(?:{_HALF_X})\s+{_DO}[^\s.;!?,]*",
    # 20 fisad zyada orders, بیس فیصد زیادہ, बीस प्रतिशत ज़्यादा
    rf"(?:\d[\d.,]*|{_N})\s?(?:{_PCT_X})\s+(?:{_MORE_X})",
    # zyada orders milenge, ज़्यादा ऑर्डर मिलेंगे
    rf"(?:{_MORE_X})\s+(?:{_BIZ_X})[^\s.;!?,]*(?:\s+[^\s.;!?,]+){{0,2}}?\s+(?:mil|ho|aa|مل|ہو|मिल|हो)[^\s.;!?,]*",
    # زيادة الطلبات بنسبة عشرين بالمئة
    rf"(?:زيادة|ارتفاع|نمو|تحسن)\s+(?:[^\s.;!?,]+\s+){{0,4}}?(?:بنسبة|\d|{_N}|%)",
    # sales double ho jayegi, دگنا, दोगुना, يضاعف
    rf"(?:{_DOUBLE_X})[^\s.;!?,]*",
    rf"double\s+{_DO}[^\s.;!?,]*",
    rf"(?:{_BIZ_X})[^\s.;!?,]*\s+(?:[^\s.;!?,]+\s+){{0,2}}?(?:double|ضعف|ضعفين)(?![^\W\d_])",
    # paisa wasool, عائد الاستثمار
    r"(?:paisa|paise|paisay|پیسہ|پیسے|पैसा|पैसे)\s+(?:wasool|وصول|वसूल)",
    r"عائد\s+(?:على\s+)?الاستثمار|(?:يسترد|تسترد)[^\s.;!?,]*",
)
OUTCOME_CLAIM = re.compile(
    "|".join(
        [rf"(?<![^\W\d_]){p}" for p in _OUTCOMES] + [rf"(?<![^\W\d_]){_fx(p)}" for p in _OUTCOMES_X]
    )
)

# Phone numbers and reference numbers are not amounts: "+92 300 1234567", "0300-1234567",
# "order #12345", "ref 40213".
_ID_LIKE = re.compile(
    r"\+\d[\d \-()]{6,}\d"
    r"|(?<!\d)0\d{2,3}[ \-]\d{6,8}(?!\d)"
    r"|(?<![^\W\d_])(?:order|ref|reference|invoice|ticket|booking|tracking|case|id|receipt)"
    r"(?![^\W\d_])\.?\s*(?:no\.?|number)?\s*[:#-]?\s*\d+"
    r"|#\s*\d+"
    r"|(?<![^\W\d_])no\.\s*\d+"
)
_DIGIT_RUN = re.compile(r"(?<![\d.,+])(\d+)(?![\d]*[%.,]\d)")


def _bare_figure(view: str) -> bool:
    """A bare run of five to nine digits ("50000") is a figure, not a count of people or a year.
    Ten or more digits, a "+" or a leading zero on nine digits is a phone number, and a figure
    followed by "%" or "percent" is a percentage."""
    for m in _DIGIT_RUN.finditer(view):
        run, end = m.group(1), m.end(1)
        if not 5 <= len(run) <= 9:
            continue
        if run.startswith("0") and len(run) >= 9:
            continue
        rest = view[end:].lstrip()
        if rest[:1] == "%" or rest.startswith(("percent", "per cent")):
            continue
        return True
    return False


def money_in(text: str) -> bool:
    """True when any view of the text holds an amount or a cost claim: the old pattern, the extra
    patterns, a free or cheap claim, or a bare figure of five to nine digits. Phone numbers and
    reference numbers are cut out first."""
    for view in views(text):
        kept = _ID_LIKE.sub(" ", view)
        if (
            MONEY_IN_TEXT.search(kept)
            or MONEY_EXTRA.search(kept)
            or COST_CLAIM.search(kept)
            or OUTCOME_CLAIM.search(kept)
            or _bare_figure(kept)
        ):
            return True
    return False


# --- a guessed cause worded as a fact -------------------------------------------------------------

_STOP = frozenset(
    (
        "a an the is are was were be been do does did not no nor of at to in on and or for it its "
        "they we you i he she our your their this that these those with by from as so than then "
        "there here have has had will would can could may might should shall into over under about "
        "because since while when where which who whom what why how all any each every some such "
        "only own same too very just also still yet"
    ).split()
)
_HEDGE_WORDS = (
    "if may might could possibly perhaps maybe assuming suppose supposing seems apparently "
    "probably likely shayad agar mumkin شاید اگر ممکن لعل ربما إذا اذا यदि अगर शायद"
)
_HEDGE_PHRASES = ("ho sakta", "ho sakti", "हो सकता", "हो सकती")
_HEDGES = re.compile(
    "|".join(
        [rf"(?<![^\W\d_])(?:{_alt(_HEDGE_WORDS)})(?![^\W\d_])"]
        + [rf"(?<![^\W\d_]){fold(p)}(?![^\W\d_])" for p in _HEDGE_PHRASES]
    )
)
_SENTENCE = re.compile(r"[.!?؟۔\n;]+")
_CLAUSE = re.compile(
    r"[,،:()\[\]–—]|(?<![^\W\d_])(?:and|but|so|because|aur|lekin|phir|toh)(?![^\W\d_])"
)
_CONTRACTION = re.compile(r"(?<![^\W\d_])([^\W\d_]+)n['’]t(?![^\W\d_])")
_STEM = 5


def content_stems(text: str) -> set[str]:
    """The content words of a text, cut to a short stem so "counting" and "count" meet."""
    s = _CONTRACTION.sub(r"\1 not", fold(text))
    s = s.replace("'", "").replace("’", "")
    words = re.findall(r"[^\W\d_]+", s)
    return {w[:_STEM] for w in words if len(w) >= 3 and w not in _STOP}


def states_as_fact(cause: str, text: str) -> bool:
    """True when `text` words the guessed `cause` as a fact: a sentence that holds most of the
    cause's content words (or the cause itself when it has fewer than two) with no hedge word in
    the same clause as those words. A hedge in another sentence or clause does not count."""
    if not isinstance(cause, str) or not isinstance(text, str):
        return False
    stems = content_stems(cause)
    if not stems:
        return False
    need = max(2, math.ceil(0.6 * len(stems))) if len(stems) >= 2 else 1
    whole = fold(cause)
    for sentence in _SENTENCE.split(text):
        if len(stems) < 2:
            found = whole in fold(sentence)
        else:
            found = len(content_stems(sentence) & stems) >= need
        if not found:
            continue
        hedged = any(
            _HEDGES.search(fold(clause)) and content_stems(clause) & stems
            for clause in _CLAUSE.split(sentence)
        )
        if not hedged:
            return True
    return False
