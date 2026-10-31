"""A number the owner corrects ("not 10, 100", "10 nahi, 100", "no wait, it is 15 kg").

Platform spec B7.1/B7.3: a correction is kept, not lost. The saved problem must show the corrected
figure, the old figure stays in the revision history, and the reply must use the new figure.

Pure functions. `numeric_correction` finds (wrong, right) from the latest message and the owner's
earlier ones; it is deliberately strict (an explicit "not X, Y" pair, or a correction cue plus
an old number followed by the same word as the new one),
so an unrelated number is never swapped.

Languages (L1-7a): English, Roman Urdu, Urdu script, Hindi (Devanagari) and Arabic. Figures may be
written in Western, Arabic-Indic, Persian or Devanagari digits (mixed in one message too), with
lakh, crore, hazar, thousand, million or k after them in Latin, Devanagari, Urdu or Arabic script
("5 lakh" is 500000). Written by one author, not reviewed by a native speaker of Hindi, Urdu or
Arabic: tests/unit/test_pi_l1_cues_hindi_arabic.py measures recall and precision with its n.

Safety of the parser (audit fix): every pattern is linear (possessive quantifiers, a figure never
starts inside a run of digits and commas), `numeric_correction` reads at most MAX_INPUT characters
(longer text gives None), and no public function raises on input that is not text.

Implicit corrections (decided and documented): a bare figure ("oops 100", "نہیں نہیں 100", "typo,
100") is a correction only when the nearest earlier owner message that has figures has exactly ONE
figure; with two or more it is None (fail safe). A strong self-correction cue ("galti", "typo",
"I meant", "قصدي", "गलती") with one figure accepts that single earlier figure whatever noun follows;
with two figures in the same message ("galti se 10 likha, 100 hain") the first is the wrong one,
unless only the second was said earlier. Reported speech ("he said 100 staff", "usne kaha", "wo keh
raha tha") is never a correction.
"""

import re
from decimal import Decimal
from functools import lru_cache

from app.modules.pi.script_words import WORD, arabic_stem, english_stem, fold, hindi_stem

MAX_INPUT = 4000  # longer text is not parsed: numeric_correction gives None (fail safe)
MAX_EARLIER = 50  # only the latest earlier messages are looked at
MAX_OLD_FIGURES = 12  # an earlier message with more figures than this is not guessed at

_DIGITS = str.maketrans(
    {
        **{ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")},  # Arabic-Indic
        **{ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")},  # Persian and Urdu
        **{ord(c): str(i) for i, c in enumerate("०१२३४५६७८९")},  # Devanagari
        ord("٫"): ".",  # Arabic decimal separator
        ord("٬"): ",",  # Arabic thousands separator
    }
)
# One figure: 5,000 or 5000 or 5.5. Possessive, and never started inside a run of digits and commas,
# so a long run is read once (linear), not once per start position.
NUM = (
    r"(?<!\d)(?<!\d,)("
    r"(?:\d{1,2}(?:,\d{2}(?=,))++,\d{3}(?!\d)"  # Indian grouping: 5,00,000
    r"|\d{1,3}(?:,\d{3})++(?!\d)"  # western grouping: 500,000
    r"|\d++)(?:\.\d++)?+)"
)
_NUMBER = re.compile(NUM)
NO = r"(?:nahi|nahin|nhi|nai|نہیں|نہی|नहीं|नही|नहि)"
# Arabic "not": لا, ليس, مش, مو (and with the joining و)
AR_NO = r"(?<!\w)(?:و?ليس|و?لا|مش|مو)(?!\w)"
# What may sit between the wrong and the right figure: "it was", "but", "बल्कि", "पर", "بلکہ", "بل".
_LINK = (
    r"(?:(?:it\s+(?:was|is)|its|it's|but|woh|wo|ye|yeh|balki|balkay|par|pe|lekin|magar|"
    r"बल्कि|पर|लेकिन|मगर|वो|वह|ये|यह|दरअसल|असल\s+में|बजाय|بلکہ|مگر|لیکن|وہ|یہ|اصل\s+میں|دراصل)"
    r"\s++)?+"
)
_AR_LINK = r"(?:(?:بل|لكن|ولكن|إنما|وإنما|بالعكس|هو|هي|كان|كانت|الصحيح|الرقم|في\s+الحقيقة)\s++)?+"
_SEP = r"\s*+[,;:.،؛-]?+\s*+"
CUE = re.compile(
    r"\b(?:not|no|sorry|correction|actually|wait|wrong|instead|rather|nahi|nahin|nhi|galat|ghalat|"
    r"darasal|asal|matlab|balki|galti|ghalti|galtee|ghaltee|typo|oops|mistake|maaf|maafi|meant|"
    r"misspoke)\b"
    r"|نہیں|غلط|غلطی|دراصل|اصل\s+میں|معاف|بلکہ|مطلب"
    r"|नहीं|नही|गलत|गलती|टाइपो|दरअसल|असल\s+में|माफ|सॉरी|मतलब|बल्कि|रुकिए|ठहरिए"
    r"|(?<!\w)(?:لا|ليس|مش|بل|خطأ|خطا|تصحيح|اقصد|أقصد|قصدي|قلت|آسف|عفوا|الصحيح|في\s+الحقيقة)"
    r"(?!\w)",
    re.IGNORECASE,
)
# A cue that says "I got my own figure wrong" (a plain "no" or "sorry" is a weaker cue).
STRONG_CUE = re.compile(
    r"\b(?:typo|oops|mistake|misspoke|my\s+bad|i\s+meant|i\s+mean|i\s+said|i\s+wrote|i\s+typed|"
    r"galti|ghalti|galtee|ghaltee|mera\s+matlab|kaha\s+tha|likha\s+tha|bola\s+tha)\b"
    r"|غلطی|میرا\s+مطلب|کہا\s+تھا|لکھا\s+تھا"
    r"|गलती|टाइपो|मेरा\s+मतलब|कहा\s+था|लिखा\s+था"
    r"|(?<!\w)(?:قلت|قصدي|اقصد|أقصد|كتبت|المقصود|خطأ|خطا|غلطة)(?!\w)",
    re.IGNORECASE,
)
# Someone else's figure ("he said 100 staff", "usne kaha", "wo keh raha tha"): never a correction.
REPORTED = re.compile(
    r"\b(?:he|she|they|him|her|manager|boss|partner)\s+(?:said|says|told|claims?|thinks?)\b"
    r"|\b(?:us|unho|unhon)\s*ne\s+(?:kaha|bola|bataya)\b"
    r"|\b(?:wo|woh|vo)\s+(?:keh|kah|bol)\s*(?:raha|rahi|rahe|ta|ti)\b"
    r"|उसने\s+कहा|उन्होंने\s+कहा|वो\s+कह\s+रहा|वह\s+कह\s+रहा"
    r"|اس\s+نے\s+کہا|انہوں\s+نے\s+کہا|وہ\s+کہہ\s+رہا"
    r"|(?<!\w)(?:قال|قالت|قالوا)(?!\w)",
    re.IGNORECASE,
)
# Words that leave a message "bare": only a cue and a number, no thing named.
BARE_WORDS = frozenset(
    """no not sorry actually wait wrong instead rather nahi nahin nhi galat ghalat galti ghalti
    galtee typo oops mistake maaf maafi meant mean said wrote typed correction it its was is the
    number figure i my ye yeh woh wo hai hain tha thi hun hoon sahi correct right bad se ho gayi
    नहीं नही गलत गलती टाइपो है हैं था थी सही मतलब मेरा
    نہیں غلط غلطی ہے ہیں تھا سہی مطلب میرا
    لا ليس خطأ خطا قلت قصدي اقصد أقصد هو هي كان الصحيح""".split()
)
# A figure with a scale word after it: "5 lakh", "10 हज़ार", "2 کروڑ", "3 ملايين", "10k".
_SCALE = (
    r"(?:\s*+(?:lakhs?|lacs?|crores?|karors?|haz+aar|hazar|hajar|thousand|million|hundred|sau|"
    r"लाख|करोड|हजार|सौ|لاکھ|لاكه|لاك|کروڑ|ہزار|ألف|الف|آلاف|ألاف|مليون|ملايين|ملیون|ملین|"
    r"سو|مئة|مائة)|k)"
)
_SCALE_END = r"(?![\wऀ-ॿً-ٟ])"
_FIGURE = re.compile(NUM + rf"(?:({_SCALE}){_SCALE_END})?+", re.IGNORECASE)
_MULTIPLIER = (
    (("hundred", "sau", "सौ", "سو", "مئة", "مائة"), Decimal(100)),
    (("lakh", "lac", "لاکھ", "لاك", "लाख"), Decimal(100000)),
    (("crore", "karor", "کروڑ", "करोड"), Decimal(10000000)),
    (("million", "مليون", "ملايين", "ملیون", "ملین"), Decimal(1000000)),
)
# "not 10, 100" / "not 10, it was 100" / "not 10 but 100"
NOT_THEN = re.compile(rf"\bnot\s++{NUM}{_SEP}{_LINK}{NUM}", re.IGNORECASE)
# "nahi 10 balki 100" / "नहीं 10 बल्कि 100" / "نہیں 10 بلکہ 100" (a leading "no")
NO_NUM_THEN = re.compile(rf"{NO}\s++{NUM}{_SEP}{_LINK}{NUM}", re.IGNORECASE)
# Arabic: "لا 10 بل 100" / "ليس 10 بل 100" / "مش 10، 100"
AR_NOT_THEN = re.compile(rf"{AR_NO}\s++{NUM}{_SEP}{_AR_LINK}{NUM}")
# "100, not 10"
THEN_NOT = re.compile(rf"{NUM}{_SEP}not\s++{NUM}", re.IGNORECASE)
# Arabic: "100 وليس 10" / "100، لا 10"
AR_THEN_NOT = re.compile(rf"{NUM}{_SEP}{AR_NO}\s++{NUM}")
# "10 nahi, 100" / "nahi 20 nahi, 12" / "20 nahi 12 hain" / "10 नहीं, 100"
NUM_NAHI = re.compile(rf"{NUM}\s*+{NO}{_SEP}{_LINK}{NUM}", re.IGNORECASE)
# "100 hai, 10 nahi" / "100 है, 10 नहीं" / "100 ہے، 10 نہیں" (the right figure first)
THEN_NAHI = re.compile(
    rf"{NUM}\s*+(?:(?:hai|hain|है|हैं|ہے|ہیں)\s*+[,;:.،؛-]?+|[,;:.،؛-])\s*+{NUM}\s*+{NO}",
    re.IGNORECASE,
)
STOP = frozenset("the and was are for with that this have has had not but its our their".split())


def _str(value: object) -> str:
    """Only text is read: None, numbers, bytes, lists and the like are an empty string."""
    return value if isinstance(value, str) else ""


def _plain(value: Decimal) -> str:
    text = format(value, "f")  # exact, and no limit on the length of the number
    return text.rstrip("0").rstrip(".") if "." in text else text


def _value(match: re.Match[str]) -> Decimal:
    """The figure of a match with its scale word applied ("5 lakh" is 500000)."""
    try:
        base = Decimal(match.group(1).replace(",", ""))
    except ArithmeticError:
        return Decimal(0)
    scale = (match.group(2) or "").strip().casefold()
    if not scale:
        return base
    for names, multiplier in _MULTIPLIER:
        if any(scale.startswith(n) for n in names):
            return base * multiplier
    return base * 1000  # hazar, thousand, k, ألف


# ---- number WORDS (PS-2) -------------------------------------------------------------------
# Kinds: u small (1-19), t tens (20-90), x special small (25, 75, 1.5, 2.5), k Arabic hundreds
# (200-900, one word), h hundred, m a multiplier (thousand, lakh, million, crore).
_LEX: dict[str, tuple[str, Decimal]] = {}


def _add(kind: str, value: str, words: str) -> None:
    for w in words.split():
        _LEX[fold(w)] = (kind, Decimal(value))


def _units(kind: str, names: str, first: int = 1) -> None:
    for i, group in enumerate(names.split("|"), first):
        _add(kind, str(i), group)


_units(
    "u",
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    "fifteen|sixteen|seventeen|eighteen|nineteen",
)
for _n, _e in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), 2):
    _add("t", str(_n * 10), _e)
_add("h", "100", "hundred")
_add("m", "1000", "thousand")
_add("m", "100000", "lakh lakhs lac lacs")
_add("m", "10000000", "crore crores")
_add("m", "1000000", "million")
# Roman Urdu and Hindi in Latin letters
_units(
    "u",
    "ek aik|do|teen|char chaar|paanch panch paach|chay chhe chhay chhah chaah|saat|aath|nau|"
    "das dus|gyarah|barah|terah|chaudah|pandrah|solah|satrah|atharah|unnees",
)
for _v, _w in (
    ("20", "bees"),
    ("30", "tees"),
    ("40", "chalis"),
    ("50", "pachas"),
    ("60", "saath"),
    ("70", "sattar"),
    ("80", "assi"),
    ("90", "nabbe"),
):
    _add("t", _v, _w)
_add("x", "25", "pachees pachchis")
_add("x", "75", "pachattar")
_add("x", "1.5", "dedh")
_add("x", "2.5", "dhai")
_add("h", "100", "sau")
_add("m", "1000", "hazaar hazar hajar")
_add("m", "10000000", "karor")
# Urdu script
_units("u", "ایک|دو|تین|چار|پانچ|چھ|سات|آٹھ|نو|دس|گیارہ|بارہ|تیرہ|چودہ|پندرہ|سولہ|سترہ|اٹھارہ|انیس")
for _v, _w in (
    ("20", "بیس"),
    ("30", "تیس"),
    ("40", "چالیس"),
    ("50", "پچاس"),
    ("60", "ساٹھ"),
    ("70", "ستر"),
    ("80", "اسی"),
    ("90", "نوے"),
):
    _add("t", _v, _w)
_add("x", "25", "پچیس")
_add("x", "75", "پچھتر")
_add("x", "1.5", "ڈیڑھ")
_add("x", "2.5", "ڈھائی")
_add("h", "100", "سو")
_add("m", "1000", "ہزار")
_add("m", "100000", "لاکھ")
_add("m", "10000000", "کروڑ")
_add("m", "1000000", "ملین ملیون")
# Hindi
_units(
    "u",
    "एक|दो|तीन|चार|पांच पाँच|छह छः छे|सात|आठ|नौ|दस|ग्यारह|बारह|तेरह|चौदह|पंद्रह पन्द्रह|सोलह|"
    "सत्रह|अठारह|उन्नीस",
)
for _v, _w in (
    ("20", "बीस"),
    ("30", "तीस"),
    ("40", "चालीस"),
    ("50", "पचास"),
    ("60", "साठ"),
    ("70", "सत्तर"),
    ("80", "अस्सी"),
    ("90", "नब्बे"),
):
    _add("t", _v, _w)
_add("x", "25", "पच्चीस पचीस")
_add("x", "75", "पचहत्तर")
_add("x", "1.5", "डेढ़")
_add("x", "2.5", "ढाई")
_add("h", "100", "सौ")
_add("m", "1000", "हज़ार हजार")
_add("m", "100000", "लाख")
_add("m", "10000000", "करोड़")
_add("m", "1000000", "मिलियन")
# Arabic
_units(
    "u",
    "واحد احد احدى|اثنان اثنين اثنا اثنتا|ثلاثة ثلاث|اربعة اربع|خمسة خمس|ستة ست|سبعة سبع|"
    "ثمانية ثماني ثمان|تسعة تسع|عشرة عشر",
)
for _v, _w in (
    ("20", "عشرون عشرين"),
    ("30", "ثلاثون ثلاثين"),
    ("40", "اربعون اربعين"),
    ("50", "خمسون خمسين"),
    ("60", "ستون ستين"),
    ("70", "سبعون سبعين"),
    ("80", "ثمانون ثمانين"),
    ("90", "تسعون تسعين"),
):
    _add("t", _v, _w)
for _v, _w in (
    ("200", "مئتان مئتين مائتان مائتين"),
    ("300", "ثلاثمئة ثلاثمائة"),
    ("400", "اربعمئة اربعمائة"),
    ("500", "خمسمئة خمسمائة"),
    ("600", "ستمئة ستمائة"),
    ("700", "سبعمئة سبعمائة"),
    ("800", "ثمانمئة ثمانمائة"),
    ("900", "تسعمئة تسعمائة"),
):
    _add("k", _v, _w)
_add("h", "100", "مئة مائة مئه مية")
_add("m", "1000", "ألف")
_add("m", "1000", "آلاف")
_add("m", "1000000", "مليون ملايين")

# Words that are also ordinary words, or "a/an": a figure only with a magnitude after them (ek sau,
# do hazaar), a count noun (not for the singular words), or as the object of a correction cue.
_SINGULAR = frozenset(fold(w) for w in "one ek aik ایک एक واحد احد".split())
_AMBIGUOUS = _SINGULAR | frozenset(
    fold(w) for w in "do das teen saath chay nau دو نو اسی ست दो ".split()
)
_VERBS_BEFORE_DO = frozenset(
    "kar karo kardo de dey dena dijiye diye bata batao bhej bhejo dikha dikhao rakh rakho le lo "
    "hone ro".split()
)
_TITLES = frozenset("mr mrs ms dr shri sri sir miss".split())
_IDIOM_AFTER = frozenset(
    fold(w)
    for w in "percent percentage fisad fisat times thanks thank shukriya shukria baar bar "
    "فیصد فیصدی شکریہ بار مرتبہ مرة شكرا प्रतिशत धन्यवाद बार".split()
)
_CUE_PREV = frozenset(
    fold(w)
    for w in "not no nahi nahin nhi nai but balki بلکہ बल्कि بل لكن said meant mean wrote typed "
    "was is "
    "kaha likha bola matlab "
    "نہیں نہی नहीं नही لا ليس مش مو قلت قصدي اقصد كتبت مطلب مطلب کہا لکھا कहा लिखा मतलब".split()
)
_NO_WORDS = frozenset(
    fold(w) for w in "not nahi nahin nhi nai نہیں نہی नहीं नही لا ليس مش مو".split()
)
_LINK_NEXT = frozenset(
    fold(w)
    for w in "but balki balkay lekin magar par hai hain tha thi بلکہ مگر لیکن ہے ہیں है हैं "
    "बल्कि लेकिन पर بل لكن كان".split()
)
_NOUNS = frozenset(
    fold(w)
    for w in """
    people person staff client customer employee worker member student teacher shop store branch
    outlet order parcel booking appointment patient table room flat apartment unit item product car
    truck vehicle bird chick animal cow buffalo day week month year hour minute second kg kilo gram
    ton litre liter bag box piece pcs rupee rs pkr usd dollar euro aed sar dirham riyal percent
    pound
    log bande banda admi aadmi gahak grahak dukan dukaan dukane dukanein rupay rupaye rupye din dino
    hafte hafta haftay mahine mahina maheene saal sal ghante ghanta kilo bori bags mareez bacche
    bachay bache talib malazim mulazim kamgar cheezein gaari gaarian murghi murghiyan
    لوگ لوگوں بندے بندہ آدمی گاہک گاہکوں دکان دکانیں روپے روپیہ دن ہفتے ہفتہ مہینے مہینہ سال گھنٹے
    گھنٹہ کلو بوری مریض بچے ملازم ملازمین ورکر
    लोग आदमी ग्राहक दुकान दुकानें ऑर्डर रुपये रुपया दिन हफ्ते महीने साल घंटे किलो बोरी मरीज बच्चे
    कर्मचारी
    عميل عملاء زبون زبائن موظف موظفين عامل عمال مستأجر مستأجرين حجز حجوزات طلب طلبات شقة شقق محل
    محلات فرع فروع يوم ايام اسبوع اسابيع شهر اشهر شهور سنة سنوات ساعة ساعات كيلو ريال درهم دولار
    جنيه روبية مريض مرضى طالب طلاب طرد شحنة شحنات طائر طيور مشترك مشتركين عائلة اسرة بطاقة
    """.split()
)
_GAP = re.compile(r"[\s\-‐‑]*")
_PUNCT_AFTER = re.compile(r"\s*(?:[,;:.،؛!?)\]\"']|$)")
_PERCENT_AFTER = re.compile(r"\s*%")
_AND = frozenset({"and", "و"})
_ARTICLES = frozenset({"a", "an"})


def _noun_like(word: str) -> bool:
    stems = {word, english_stem(word), arabic_stem(word), hindi_stem(word), word.rstrip("ا")}
    if word.endswith(("ات", "ين", "ون", "ان")):
        stems.add(word[:-2])
    return not stems.isdisjoint(_NOUNS)


@lru_cache(maxsize=8192)
def _fold_word(word: str) -> str:
    return fold(word)


class _Tok:
    __slots__ = ("end", "joined", "kind", "start", "value", "vstart", "word")

    def __init__(self, start: int, end: int, word: str) -> None:
        self.start, self.end, self.vstart, self.word = start, end, start, word
        self.kind: str | None = None
        self.value = Decimal(0)
        self.joined = False  # written with a joining waw ("وعشرون")


def _tokens(text: str, blocked: list[tuple[int, int]]) -> list[_Tok]:
    toks: list[_Tok] = []
    b = 0
    for m in WORD.finditer(text):
        t = _Tok(m.start(), m.end(), _fold_word(m.group()))
        while b < len(blocked) and blocked[b][1] <= t.start:
            b += 1
        inside = b < len(blocked) and blocked[b][0] < t.end
        if not inside and not t.word.isdigit():
            hit = _LEX.get(t.word)
            if hit is None and len(t.word) > 3 and t.word[0] == "و" and t.word[1:] in _LEX:
                hit = _LEX[t.word[1:]]
                t.joined, t.vstart = True, t.start + 1
                t.word = t.word[1:]
            if hit is not None:
                t.kind, t.value = hit
            elif t.word in _AND or t.word in _ARTICLES:
                t.kind = "and" if t.word in _AND else "art"
        toks.append(t)
    return toks


class _Phrase:
    __slots__ = (
        "end",
        "first",
        "has_mag",
        "last",
        "last_mult",
        "last_value",
        "lead",
        "n",
        "start",
        "total",
        "current",
    )

    def __init__(self, first: int, start: int) -> None:
        self.first, self.start, self.end = first, start, start
        self.total = self.current = Decimal(0)
        self.last = ""
        self.last_value = Decimal(0)
        self.last_mult = Decimal(0)
        self.has_mag = False
        self.n = 0
        self.lead = first  # index of the first token of the phrase (the article included)


def _extend(
    ph: _Phrase | None, i: int, t: _Tok, prev_art: bool, toks: list[_Tok]
) -> _Phrase | None:
    """Add token t (a number word) to phrase ph; None when ph cannot take it (a new one starts)."""
    kind, v = t.kind or "", t.value
    if ph is None:
        ph = _Phrase(i, t.vstart)
        if prev_art and kind in ("h", "m"):
            ph.start, ph.lead = toks[i - 1].start, i - 1
        if kind in ("h", "m"):
            ph.current = Decimal(1) if kind == "m" else Decimal(0)
    lk = ph.last
    if ph.n:
        if kind in ("u", "t", "x"):
            small_pair = (lk == "t" and kind == "u" and v < 10) or (
                lk == "u" and ph.last_value < 10 and kind == "t" and t.joined
            )
            teen = t.word == fold("عشر") and lk == "u" and ph.last_value < 10
            if lk in ("h", "m", "k"):
                ph.current += v
            elif small_pair or teen:
                ph.current += v
                kind = "u"
            else:
                return None
        elif kind == "k":
            if lk not in ("m",):
                return None
            ph.current += v
        elif kind == "h":
            if lk in ("u", "t", "x"):
                ph.current *= 100
            elif lk == "m":
                ph.current = Decimal(100)
            else:
                return None
        elif kind == "m":
            if lk == "m" or (ph.last_mult and v >= ph.last_mult):
                return None
            base = ph.current if ph.current else Decimal(1)
            ph.total += base * v
            ph.current = Decimal(0)
            ph.last_mult = v
    else:
        if kind in ("u", "t", "x", "k"):
            ph.current = v
        elif kind == "h":
            ph.current = Decimal(100)
        else:  # m
            ph.total, ph.current, ph.last_mult = v, Decimal(0), v
    if kind in ("h", "m", "k"):
        ph.has_mag = True
    ph.last, ph.last_value, ph.end = kind, v, t.end
    ph.n += 1
    return ph


def _accept(ph: _Phrase, toks: list[_Tok], last_i: int, text: str) -> bool:
    """Is this phrase a figure here? A word that is also an ordinary word needs context."""
    value = ph.total + ph.current
    words = [
        t.word for t in toks[ph.first : last_i + 1] if t.kind in ("u", "t", "x", "k", "h", "m")
    ]
    prev = toks[ph.lead - 1].word if ph.lead > 0 else ""
    nxt = toks[last_i + 1] if last_i + 1 < len(toks) else None
    glued = nxt is not None and _GAP.fullmatch(text[ph.end : nxt.start]) is not None
    if value == 100 and (
        (glued and nxt is not None and nxt.word in _IDIOM_AFTER)
        or _PERCENT_AFTER.match(text, ph.end)
    ):
        return False  # "a hundred percent sure"
    if ph.has_mag and glued and nxt is not None and nxt.word in _IDIOM_AFTER:
        return False  # "a thousand times", "lakh shukriya"
    if "das" in words and (prev in _TITLES or not text[toks[ph.first].start].islower()):
        return False  # a name
    singular = all(w in _SINGULAR for w in words)
    ambiguous = any(w in _AMBIGUOUS for w in words)
    if ph.n >= 2 and ph.has_mag and ph.first == ph.lead:
        return True  # "paanch sau", "do hazaar": the magnitude makes the count a figure
    if ph.n == 1 and not ambiguous and not ph.has_mag:
        return True  # "ten", "دس", "पचास"
    if ph.n >= 2 and not ambiguous:
        return True
    if ph.lead < ph.first:
        return True  # "a hundred"
    # single magnitude word, or an ordinary-word number: context
    noun = glued and nxt is not None and _noun_like(nxt.word)
    if noun and not singular:
        return True
    follow = (
        _PUNCT_AFTER.match(text, ph.end)
        or (nxt is not None and (nxt.word in _NO_WORDS or nxt.word in _LINK_NEXT))
        or (glued and nxt is not None and nxt.word in _LINK_NEXT)
    )
    if prev in _CUE_PREV and follow:
        return True  # "not ten", "I meant sau"
    if nxt is not None and nxt.word in _NO_WORDS:
        k = last_i + 2
        if k < len(toks) and (
            toks[k].kind in ("u", "t", "x", "k", "h", "m") or toks[k].word.isdigit()
        ):
            return True  # "do nahi, teen"
    if ph.n == 1 and ph.last in ("m", "k"):
        return True  # "lakh", "مليون", "ثلاثمئة": a magnitude alone is a figure (idioms are out)
    if ph.n == 1 and ph.has_mag and not ambiguous:  # sau, hundred: also ordinary words
        return bool(noun) or bool(glued and nxt is not None and nxt.word in _LINK_NEXT)
    return False


def _may_hold_number_word(text: str) -> bool:
    """Cheap pre-check on the distinct words: most text has no number word at all."""
    for w in set(WORD.findall(text)):
        f = _fold_word(w)
        if f in _LEX or (f[:1] == "و" and f[1:] in _LEX):
            return True
    return False


def _word_spans(text: str, blocked: list[tuple[int, int]]) -> list[tuple[int, int, Decimal, bool]]:
    if not _may_hold_number_word(text):
        return []
    toks = _tokens(text, blocked)
    out: list[tuple[int, int, Decimal, bool]] = []
    ph: _Phrase | None = None
    last_i = -1
    pending_art = False

    def close() -> None:
        nonlocal ph
        if ph is not None and _accept(ph, toks, last_i, text):
            out.append((ph.start, ph.end, ph.total + ph.current, True))
        ph = None

    for i, t in enumerate(toks):
        adjacent = i > 0 and _GAP.fullmatch(text[toks[i - 1].end : t.start]) is not None
        if ph is not None and not adjacent:
            close()
        if t.kind in ("u", "t", "x", "k", "h", "m"):
            prev_word = toks[i - 1].word if i else ""
            if t.word in ("do", "دو", "दो") and prev_word in _VERBS_BEFORE_DO:
                close()  # "kar do": the verb, not a 2
                pending_art = False
                continue
            nxt = _extend(ph, i, t, pending_art and adjacent, toks) if ph is not None else None
            if ph is not None and nxt is None:
                close()
                nxt = _extend(None, i, t, pending_art and adjacent, toks)
            elif ph is None:
                nxt = _extend(None, i, t, pending_art and adjacent, toks)
            ph, last_i = nxt, i
            pending_art = False
        elif t.kind == "and":
            if ph is not None and ph.last not in ("h", "m", "k") and t.word != "و":
                close()
            continue
        else:
            close()
            pending_art = t.kind == "art"
    close()
    return out


def _digit_spans(text: str) -> list[tuple[int, int, Decimal, bool]]:
    """Every digit figure of the (digit-translated) text: (start, end, value, has a scale word)."""
    return [(m.start(), m.end(), _value(m), bool(m.group(2))) for m in _FIGURE.finditer(text)]


def _all_spans(text: str) -> list[tuple[int, int, Decimal, bool]]:
    """Digit figures and number-word phrases, in order. A scaled digit figure ("5 lakh") owns its
    scale word, so that word never starts a phrase of its own."""
    spans = _digit_spans(text)
    blocked = [(a, b) for a, b, _, _ in spans]
    words = _word_spans(text, blocked)
    return sorted(spans + words, key=lambda x: x[0]) if words else spans


def expand(text: str) -> str:
    """The text with Eastern digits as 0-9, nukta dropped, and every scaled figure and number-word
    phrase written out ("5 lakh" and "paanch lakh" both give "500000"). Matching runs on this, so
    one rule covers every script. Never raises: anything that is not text is read as empty."""
    text = _str(text).translate(_DIGITS).replace("़", "")
    out, last = [], 0
    for start, end, value, rewrite in _all_spans(text):
        if rewrite:
            out.append(text[last:start])
            out.append(_plain(value))
            last = end
    out.append(text[last:])
    return "".join(out)


def norm(token: str) -> str:
    """A number as a comparable string: commas out, Eastern digits turned into 0-9, no zero tail."""
    whole, _, frac = _str(token).translate(_DIGITS).replace(",", "").partition(".")
    whole = whole.lstrip("0") or "0"
    frac = frac.rstrip("0")
    return f"{whole}.{frac}" if frac else whole


def numbers_in(text: str) -> list[str]:
    return [norm(m) for m in _NUMBER.findall(expand(text))]


def _following_plain(plain: str, number: str) -> str:
    """The first word after the number in already expanded text."""
    for m in _NUMBER.finditer(plain):
        if norm(m.group(1)) == number:
            tail = [fold(w) for w in WORD.findall(plain[m.end() :]) if not w[0].isdigit()]
            tail = [arabic_stem(w) for w in tail if w not in STOP]
            return tail[0][:5] if tail else ""
    return ""


def _following_word(text: str, number: str) -> str:
    """The first word after the number ("10 clients" gives "client"): the same fact?"""
    return _following_plain(expand(text), number)


def _is_bare(text: str) -> bool:
    """Only a cue and a figure: no thing is named ("oops 100", "نہیں نہیں 100")."""
    words = [fold(w) for w in WORD.findall(text) if not w[0].isdigit()]
    return all(w in BARE_WORDS or w in _BARE_FOLDED for w in words)


_BARE_FOLDED = frozenset(fold(w) for w in BARE_WORDS)


def _explicit(text: str) -> tuple[str, str] | None:
    for pattern, order in (
        (NOT_THEN, (0, 1)),
        (NUM_NAHI, (0, 1)),
        (NO_NUM_THEN, (0, 1)),
        (AR_NOT_THEN, (0, 1)),
        (THEN_NOT, (1, 0)),
        (THEN_NAHI, (1, 0)),
        (AR_THEN_NOT, (1, 0)),
    ):
        m = pattern.search(text)
        if m:
            wrong, right = norm(m.group(order[0] + 1)), norm(m.group(order[1] + 1))
            if wrong != right:
                return wrong, right
    return None


def numeric_correction(latest: str, earlier: list[str]) -> tuple[str, str] | None:
    """(wrong, right) when the latest message corrects a number, else None. Never raises; text
    longer than MAX_INPUT characters is not parsed (None)."""
    if not isinstance(latest, str) or len(latest) > MAX_INPUT:
        return None
    history = [
        e[:MAX_INPUT]
        for e in (list(earlier)[-MAX_EARLIER:] if isinstance(earlier, (list, tuple)) else [])
        if isinstance(e, str)
    ]
    text = " ".join(expand(latest).split())
    if not text or REPORTED.search(text):
        return None
    found = _explicit(text)
    if found:
        return found
    strong = bool(STRONG_CUE.search(text))
    if not (strong or CUE.search(text)):
        return None
    mine = numbers_in(text)
    distinct = list(dict.fromkeys(mine))
    named = re.search(rf"\bnot\s++{NUM}", text, re.IGNORECASE)  # "5,000 subscribers, not 500"
    if named and len(distinct) == 2:
        wrong = norm(named.group(1))
        others = [n for n in distinct if n != wrong]
        if len(others) == 1:
            return wrong, others[0]
    earlier_texts = [e for e in history if e and e != latest]
    if len(distinct) == 2 and strong:
        # "galti se 10 likha, 100 hain": the first is wrong, unless only the second was said before
        said_before = {n for e in earlier_texts for n in numbers_in(e)}
        first, second = distinct
        if second in said_before and first not in said_before:
            return second, first
        return first, second
    if len(distinct) != 1:
        return None
    right = distinct[0]
    for old in reversed(earlier_texts):
        olds = [n for n in dict.fromkeys(numbers_in(old)) if n != right]
        if not olds:
            continue
        if len(olds) > MAX_OLD_FIGURES:
            return None
        word = _following_word(text, right)
        old_plain = expand(old)
        same = [n for n in olds if word and _following_plain(old_plain, n) == word]
        if len(same) == 1:
            return same[0], right
        if len(olds) == 1 and (strong or _is_bare(text)):
            return olds[0], right  # the implicit correction: exactly one earlier figure
        return None  # the nearest earlier message with numbers does not match: do not guess
    return None


def standalone(number: str) -> re.Pattern[str]:
    """The number as its own figure: 10 matches "10 clients" but not "100", "10.5" or "5,10"."""
    plain = _str(number).replace(".", r"\.")
    return re.compile(rf"(?<![\d.,]){plain}(?![\d]|[.,]\d)")


def has_figure(text: str, number: str) -> bool:
    return any(norm(n) == number for n in numbers_in(text))


def replace_figure(text: str, wrong: str, right: str) -> str:
    """The text with every standalone `wrong` figure (any comma style, any scale word) written as
    `right`. Never raises: a text that is not a string gives an empty string."""
    source = _str(text)
    if not isinstance(wrong, str) or not isinstance(right, str):
        return source
    out, last = [], 0
    for start, end, value, _ in _all_spans(source.translate(_DIGITS)):  # translate keeps the length
        if norm(_plain(value)) == wrong:
            out.append(source[last:start])
            out.append(right)
            last = end
    out.append(source[last:])
    return "".join(out)


_ACK = re.compile(
    r"(?:\bnot\b|\binstead of\b|\brather than\b|\bnahi\b|\bnahin\b|\bnhi\b|\bnot\s+the\b|"
    r"के\s+बजाय|की\s+जगह|نہیں|کی\s+جگہ|ليس|بدل[اً]*\s+من|ولا|وليس)"
    r"[^.?!\n]{0,12}$",
    re.IGNORECASE,
)
_ACK_AFTER = re.compile(r"\s*(?:nahi|nahin|nhi|नहीं|नही|نہیں|نہی)(?!\w)", re.IGNORECASE)


def reply_problem(reply: str, wrong: str, right: str) -> str | None:
    """Why a reply to a correction cannot go: it does not use the new figure, or it still gives the
    old one as a fact ("not 10" or "instead of 10" is an acknowledgement, not a fact)."""
    if not has_figure(reply, right):
        return (
            f"the owner just corrected a figure to {right} (not {wrong}): the reply must use "
            f"{right}"
        )
    plain = expand(reply)
    for m in _NUMBER.finditer(plain):
        if norm(m.group(1)) != wrong:
            continue
        before = plain[max(0, m.start() - 14) : m.start()]
        after = plain[m.end() : m.end() + 8]
        if _ACK.search(before) or _ACK_AFTER.match(after):
            continue
        return (
            f"the owner corrected {wrong} to {right}, but the reply still gives {wrong} as a "
            f"fact: use {right} only"
        )
    return None


def superseded(old_word: str, new_texts: list[str], correction: bool) -> bool:
    """An earlier user_word that the correction replaces: it carries a figure that the new wording
    contradicts (a different figure about the same thing), so the record does not keep it as the
    current fact. It stays in the revision history, which holds the old list in full."""
    if not correction:
        return False
    old = set(numbers_in(old_word))
    new = {n for t in new_texts for n in numbers_in(t)}
    if not old or not new or old & new:
        return False
    stems = {w.casefold()[:5] for w in WORD.findall(old_word) if len(w) >= 4} - STOP
    fresh = {w.casefold()[:5] for t in new_texts for w in WORD.findall(t) if len(w) >= 4}
    return bool(stems & fresh)
