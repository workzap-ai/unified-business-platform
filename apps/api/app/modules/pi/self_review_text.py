# ruff: noqa: E501
"""PS-10: text helpers and the small multilingual lexicons of the self-review gate.

Pure and linear: every function cuts its input to `MAX_TEXT` characters first. Four languages,
one logic: English, Roman Urdu, Urdu script, Arabic. Patterns are written in natural spelling and
folded with the same `fold` as the text, so a spelling variant of a letter cannot hide a match.
"""

from __future__ import annotations

import re
import unicodedata

from app.modules.pi.self_review_types import MAX_TEXT

_MARKS = re.compile("[ً-ٰٟۖ-ۭـ]")
_FOLD = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ة": "ہ",
        "ه": "ہ",
        "ۃ": "ہ",
        "ھ": "ہ",
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
        "٪": "%",
        "’": "'",
    }
)


def cut(text: object, limit: int = MAX_TEXT) -> str:
    return text[:limit] if isinstance(text, str) else ""


def fold(text: object) -> str:
    """Lower-case, one shape per letter written several ways, marks dropped, digits ASCII."""
    t = unicodedata.normalize("NFKC", cut(text)).casefold()
    return _MARKS.sub("", t).translate(_FOLD)


def rx(*alts: str) -> re.Pattern[str]:
    """One alternation, each alternative folded like the text (use no upper-case escapes)."""
    return re.compile("|".join(f"(?:{fold(a)})" for a in alts))


_WORD = re.compile(r"[^\W_]+")


def words(text: object) -> list[str]:
    return _WORD.findall(fold(text))


def content_words(text: object) -> set[str]:
    return {w for w in words(text) if len(w) >= 3 or not w.isascii() and len(w) >= 2}


def sentences(text: object) -> list[str]:
    parts = re.split(r"(?<=[.!?؟۔])\s+|\n+", cut(text).strip())
    return [p.strip() for p in parts if p and p.strip()]


def question_count(text: object) -> int:
    return len(re.findall(r"[?؟]", cut(text)))


def last_is_question(text: object) -> bool:
    t = cut(text).rstrip().rstrip("\"')]}*_ ")
    return bool(t) and t[-1] in "?؟"


def numbers(text: object) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", fold(text).replace(",", "")))


# ---- script and language detection (this module's own; no import of language.py) ----

_ARABIC_LETTER = re.compile("[ؠ-يٮ-ۓۺ-ۿ]")
_URDU_ONLY = re.compile("[ٹڈڑںھہےگچپژکیہھے]")
_ARABIC_ONLY = re.compile("[ةيكىهأإؤ]")
_LATIN_LETTER = re.compile("[a-z]")
_URDU_WORDS = frozenset(
    "کیا آپ اور کو کے سے میں مجھے ہمیں نہیں کریں چاہیے ہے ہیں کی کا یہ وہ پر کر".split()
)
_ARABIC_WORDS = frozenset("في من على ما هل الذي هذا هذه أن إلى عن مع كان لا نحن أنا أنت".split())
ROMAN_URDU = frozenset(
    "hai hain nahi nahin aap kya kar ke ki ko mein se aur ka ho tha hoga kaise kab ek yeh woh "
    "mujhe apka apki shukriya kijiye karein chahiye masla kitna kon kyun lekin bhi par phir "
    "abhi sirf jaye kaam mera meri mere hum ap kuch sab".split()
)
ENGLISH = frozenset(
    "the is and you to of a for what how can this that with are it be your do not on we have "
    "will would about which when from or if an so but in because may they there was has had been "
    "i my me them at by as any all one more our their also just than then who why could should "
    "does did long going".split()
)


def detect_language(text: object) -> str | None:
    """en / roman_ur / ur / ar, or None when it cannot tell (never a guess)."""
    raw = unicodedata.normalize("NFKC", cut(text))
    low = raw.casefold()
    arabic = len(_ARABIC_LETTER.findall(raw))
    latin = len(_LATIN_LETTER.findall(low))
    if arabic == 0 and latin == 0:
        return None
    if arabic > latin:
        urdu_letters = len(_URDU_ONLY.findall(raw))
        arabic_letters = len(_ARABIC_ONLY.findall(raw))
        toks = set(re.findall(r"[؀-ۿ]+", raw))
        urdu_w = len(toks & _URDU_WORDS)
        arabic_w = len(toks & _ARABIC_WORDS)
        if urdu_letters > arabic_letters or urdu_w > arabic_w:
            return "ur"
        if arabic_letters > urdu_letters or arabic_w > urdu_w:
            return "ar"
        return None
    toks_l = re.findall(r"[a-z']+", low)
    ru = sum(1 for t in toks_l if t in ROMAN_URDU)
    en = sum(1 for t in toks_l if t in ENGLISH)
    if ru >= 2 and ru >= en:
        return "roman_ur"
    if en >= 2 and en > ru:
        return "en"
    return None


def script_of_language(lang: str) -> str:
    return {"en": "latin", "roman_ur": "latin", "ur": "arabic", "ar": "arabic"}.get(lang, "")


# ---- lexicons ----

HEDGE = rx(
    r"(?<!\w)(?:may|might|could|perhaps|maybe|possibly|probably|likely|seems?|appears?|"
    r"guess|assum\w*|hypothes\w*|not sure|i think|i suspect|if|"
    r"shayad|hosakta|ho sakta|ho sakti|lagta|lagti|mumkin|andaza|andaaza|agar|meri samajh|"
    r"khayal hai|gumaan)(?!\w)",
    r"شاید|ہو سکتا|ہوسکتا|ہو سکتی|لگتا|لگتی|ممکن|اندازہ|اگر|میرا خیال|گمان",
    r"ربما|قد ",
    r"يبدو|ممكن|احتمال|أظن|اظن|أعتقد|اعتقد|إذا|اذا|لعل|يحتمل|فرضية",
)

CLAIM_WORD = rx(
    r"(?<!\w)(?:guarantee[sd]?|guaranteed|promise[sd]?|risk[- ]free|roi|return on investment|"
    r"100 ?%|for sure|"
    r"will (?:definitely|certainly|surely|save|earn|double|triple|boost|increase|grow|cut|reduce))(?!\w)",
    r"(?<!\w)(?:guarantee|pakka|yaqeen(?:i|an)?|zaroor (?:barh|bach|faida)|faida (?:hoga|zaroor)|"
    r"bachat (?:hogi|hoga)|waada|wada|paisay bach(?:en|enge)|double ho)(?!\w)",
    r"ضمانت|یقینی|یقیناً|یقینا|پکا|وعدہ|فائدہ ہوگا|بچت ہوگی|دگنا|ضرور (?:بڑھ|بچ)",
    r"ضمان|نضمن|اضمن|أضمن|مضمون|وعد|حتما|بالتأكيد سي|توفير|سيزيد|ستزيد|سيوفر|ستوفر|مضاعف",
)

PERCENT = re.compile(fold(r"(\d+(?:\.\d+)?)\s*(?:%|percent|per cent|فیصد|في المئة|بالمئة)"))
MONEY = re.compile(
    fold(
        r"(?:rs\.?|pkr|usd|aed|sar|\$|€|£|rupees?|dollars?|روپے|ریال|درہم|دولار|ريال|درهم)\s*(\d[\d,]*)"
        r"|(\d[\d,]*)\s*(?:rs\.?|pkr|usd|aed|sar|rupees?|dollars?|روپے|ریال|درہم|دولار|ريال|درهم)"
    )
)

NEGATION = rx(
    r"(?<!\w)(?:no|not|never|cannot|can't|cant|without|nahi|nahin|nai|nahi|can not)(?!\w)",
    r"نہیں|نہ ",
    r"لا |لن |لم |ليس|بدون|بغیر|بلا ",
)
CONDITIONAL = rx(
    r"(?<!\w)(?:when|once|after|if|until|before|to be|will be|would be|should be|can be)(?!\w)",
    r"(?<!\w)(?:jab|agar|jaise hi|baad)(?!\w)",
    r"جب|اگر|بعد",
    r"عند|اذا|إذا|بعد|حین|لو ",
)

JARGON = frozenset(
    "kpi roi synergy leverage scalable stakeholder stakeholders paradigm omnichannel ecosystem "
    "api saas end-to-end onboarding pipeline bandwidth holistic".split()
)

IMPLEMENTED = rx(
    r"(?<!\w)(?:has|have|had|is|are|was|were)(?: all)?(?: been)? "
    r"(?:implemented|delivered|completed|installed|deployed|launched|finished|done|live|set up|built)(?!\w)",
    r"(?<!\w)(?:we|i)(?:'ve| have| had)? (?:already )?"
    r"(?:implemented|delivered|completed|installed|deployed|set up|built|done|fixed)(?!\w)",
    r"already (?:live|running|working|done|in place)",
    r"all done",
    r"(?<!\w)(?:ho gaya|ho chuka|ho chuki|kar diya|kar di|laga diya|lagaa diya|mukammal ho|"
    r"install ho|chalu ho gaya|deliver ho|ban gaya|ban chuka)(?!\w)",
    r"ہو گیا|ہو چکا|ہو چکی|کر دیا|کر دی|لگا دیا|مکمل ہو|نصب ہو|شروع ہو چکا|بن گیا",
    r"تم تنفيذ|تم تسليم|تم الانتهاء|تم تفعيل|تم تثبيت|تم انجاز|تم إنجاز|تم اعداد|تم إعداد|نفذنا|سلمنا|أنجزنا|انجزنا",
)

APPROVAL = rx(
    r"all clear|no issues|everything checks out|fits (?:all|every)|meets all|"
    r"fully compatible|approved|no (?:problems|constraints)",
    r"sab theek|koi masla nahi|sab shartein poori|mukammal tor par munasib|manzoor",
    r"سب ٹھیک|کوئی مسئلہ نہیں|منظور شدہ|تمام شرائط پوری",
    r"كل شيء جيد|لا توجد مشاكل|لا مشاكل|تم اعتماد|جميع القيود محققه|مناسب تماما|معتمد",
)


def has_hedge(sentence: str) -> bool:
    return bool(HEDGE.search(fold(sentence)))


def guarded_hits(
    pattern: re.Pattern[str], text: object, guards: tuple[re.Pattern[str], ...]
) -> list[str]:
    """Matches of `pattern` in the folded text with no guard word in the 30 characters before and, when
    guards are given, no negation in the rest of the clause (Urdu puts the "nahi" after the verb)."""
    t = fold(text)
    out: list[str] = []
    for m in pattern.finditer(t):
        before = t[max(0, m.start() - 30) : m.start()]
        after = re.split(r"[.!?؟۔\n]", t[m.end() : m.end() + 16])[0]
        if any(g.search(before) for g in guards) or (guards and NEGATION.search(after)):
            continue
        out.append(m.group(0).strip())
        if len(out) >= 10:
            break
    return out
