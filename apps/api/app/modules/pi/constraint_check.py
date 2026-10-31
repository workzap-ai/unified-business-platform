"""L2-1: does one option break something the owner said they cannot do? Pure and deterministic.

No database, no model, no network, and NO import from `evalkit` (the FT-A3 scorer has open
findings and must not feed production logic). `check_option(option_text, requirements, language)`
returns a `Verdict`: status `ok`, `violates` or `unknown`, the rule that fired, the matched
evidence words and a reason.

THE LIMITS (what this module does and does not read), stated once
  * Rejecting is fail-safe for the owner's stated hard limits; accepting is not. `ok` means every
    stated limit was read, compared, and not broken. A limit that cannot be read or compared gives
    `unknown`, never `ok` (no requirements at all is `ok`: there is nothing to break; requirements
    that could not be read from the database, `columns_available=False`, are `unknown`).
  * Languages: English and Roman Urdu word lists (verb families, cost and income words, units,
    durations). Urdu script, Hindi, Arabic and any other script: amounts are parsed (digits in any
    script; lakh, crore, hazar and Rs words in Urdu and Devanagari) but their role (cost or income)
    is not known, so a figure above a ceiling is `unknown`, and every word rule is `unknown`.
  * The `language` argument is a hint recorded in reasons; the word lists are used for both
    English and Roman Urdu whatever it says.
  * Words are matched on the FULL stemmed word ("employee" is not "employ", "appointment" is not
    "appoint", "evening" is not "even", "care" is not "car"). Synonyms of an object ("till" for
    "POS") are not known: a matching verb with a different object is `ok` only when the objects
    share nothing, and `unknown` when they share only a generic word (system, machine, tool).
  * Budget: figures are compared as stated (a monthly figure against a total ceiling, Rs against
    INR, are not converted); another currency than the ceiling's is `unknown`. A staff limit
    ("only 2 staff", "hiring is frozen") is a ceiling on the people an option adds. A cause is
    not a limit and is ignored here. With NO budget stated, an option that looks like it costs
    money is `unknown` (never "clear of the limits"). Options in Urdu script, Arabic and Hindi are
    read through `constraint_scripts` (verbs and objects as English concepts); a word it does not
    know makes the option `unknown`, never `ok`.
  * A deadline: a date needs a calendar and this module has no clock, so only durations ("in 2
    weeks", "kal tak") are compared. An option that states no timeframe, or one longer than the
    deadline, is `unknown`: it never silently passes and it is never rejected for time alone.
  * A `cannot afford <outcome>` limit ("we cannot afford downtime") is a goal, not a purchasable
    object: an option that names the outcome with an avoidance cue (never, without, prevent, so
    that) is `ok`, one that names it with no such cue is `unknown`, one that does not mention it is
    `ok`. A `cannot afford <thing>` limit (new equipment) rejects buying that thing, and leaves
    renting it `unknown`.
"""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Literal

from app.modules.pi import constraint_lexicon as lex
from app.modules.pi import constraint_scripts as scripts
from app.modules.pi.requirements_types import (
    Limit,
    Requirements,
    TriedItem,
    as_requirements,
)

Status = Literal["ok", "violates", "unknown"]

RULE_NONE = "none"
RULE_CANNOT_CHANGE = "cannot_change"
RULE_TRIED = "tried_failed"
RULE_BUDGET = "budget"
RULE_DEADLINE = "deadline"
RULE_UNREADABLE = "unreadable"


@dataclass(frozen=True, slots=True)
class Verdict:
    status: Status
    rule: str
    evidence: tuple[str, ...]
    reason: str


def _ok(rule: str, reason: str, evidence: tuple[str, ...] = ()) -> Verdict:
    return Verdict("ok", rule, evidence, reason)


def _violates(rule: str, reason: str, evidence: tuple[str, ...]) -> Verdict:
    return Verdict("violates", rule, evidence, reason)


def _unknown(rule: str, reason: str, evidence: tuple[str, ...] = ()) -> Verdict:
    return Verdict("unknown", rule, evidence, reason)


# --------------------------------------------------------------------------------- text basics

_LETTER = r"[^\W\d_]"
_WORD = re.compile(rf"{_LETTER}+(?:'{_LETTER}+)?")
_LATIN = re.compile(r"[A-Za-z]")
_OTHER_LETTER = re.compile(r"[^\W\d_A-Za-zÀ-ɏ]")
_CLAUSE_BREAK = re.compile(r"[;:!?\n]|\.(?=\s|$)")
_BREAK_WORDS = frozenset(
    "then but so because while whereas although though aur phir lekin magar".split()
)


# Arabic-script letter forms that mean the same letter: alef, yeh, kaf, heh. Marks (tashkeel,
# tatweel) are dropped. The same fold is applied to every Arabic-script word list below.
_AR_FOLD = {
    **dict.fromkeys("أإآٱ", "ا"),
    **dict.fromkeys("يى", "ی"),
    "ك": "ک",
    **dict.fromkeys("ةہۃە", "ه"),
}
# Cyrillic and Greek letters that look like Latin ones (upper and lower case).
_HOMOGLYPHS = str.maketrans(
    "АВЕКМНОРСТХаеорсухіјѕΑΒΕΖΗΙΚΜΝΟΡΤΥΧαοινρκτυε",
    "ABEKMHOPCTXaeopcyxijsABEZHIKMNOPTYXaoivpktue",
)
_ASCII_APOSTROPHE = str.maketrans("`", "'")
_ANY_WORD = re.compile(r"(?:[^\W\d_]|[ऀ-ःऺ-ॏ॑-ॗॢॣ])+")
_DOTTED = re.compile(r"(?<![^\W\d_])(?:[^\W\d_]\.){2,}")  # P.O.S. -> POS
_DIGIT_RUN = re.compile(r"(?<!\d)\d(?:(?: ?, ?| )\d){2,}(?!\d)")  # 9 0 , 0 0 0 -> 90,000
_THOUSANDS = re.compile(r"(?<![\d,.])\d{1,3}(?: \d{3})+(?!\d)")  # 90 000 -> 90000
_COMMA_DECIMAL = re.compile(
    r"(?<![\d,.])(\d{1,2}),(\d{1,2})(?!\d)"
    r"(?=\s*(?:lakhs?|lacs?|crores?|million|hazar|thousand|k|m)\b)"
)  # 1,2 lakh -> 1.2 lakh
_SPACED = re.compile(r"(?<![^\W\d_])(?:[^\W\d_] ){2,}[^\W\d_](?![^\W\d_])")


def _canon(text: str) -> str:
    """NFKC, no invisible or bidi marks, no Arabic marks, one form per Arabic letter (no case)."""
    out = []
    for ch in unicodedata.normalize("NFKC", text):
        code = ord(ch)
        if unicodedata.category(ch) == "Cf" or code == 0x640 or 0x64B <= code <= 0x65F:
            continue
        if code == 0x670 or 0x6D6 <= code <= 0x6ED:
            continue
        out.append(_AR_FOLD.get(ch, ch))
    return "".join(out)


def _fold_homoglyphs(word: re.Match[str]) -> str:
    w = word.group(0)
    if any("a" <= c.lower() <= "z" for c in w):  # only inside a word that also has Latin letters
        return w.translate(_HOMOGLYPHS)
    return w


def norm(text: str) -> str:
    """The text the rules read: lower case, one apostrophe, ASCII digits, no invisible marks,
    look-alike letters folded inside Latin words, letter-spacing collapsed, currency glued to
    digits pulled apart."""
    return _norm(text) if isinstance(text, str) else ""


@lru_cache(maxsize=64)
def _norm(text: str) -> str:
    if text.isascii():
        t = text.translate(_ASCII_APOSTROPHE).lower()
    else:
        out = []
        for ch in _canon(text):
            if ch.isdigit() and not ch.isascii():
                try:
                    ch = str(unicodedata.decimal(ch))
                except ValueError:
                    pass
            out.append("'" if ch in "’‘ʼ`" else ch)
        t = _ANY_WORD.sub(_fold_homoglyphs, "".join(out)).lower()
    t = _SPACED.sub(lambda m: m.group(0).replace(" ", ""), t)
    t = _DOTTED.sub(lambda m: m.group(0).replace(".", ""), t)
    t = _DIGIT_RUN.sub(lambda m: m.group(0).replace(" ", ""), t)
    t = _THOUSANDS.sub(lambda m: m.group(0).replace(" ", ""), t)
    t = _COMMA_DECIMAL.sub(r"\1.\2", t)
    t = re.sub(r"\b(rs|pkr|inr|usd|eur|gbp|aed|sar)\.?(?=\d)", r"\1 ", t)
    t = re.sub(r"\b(rs)\.(?=\s)", r"\1", t)
    return t


def spaced_runs(text: str) -> list[str]:
    """The words that were written letter by letter ("b u y"), as collapsed."""
    if not isinstance(text, str):
        return []
    canon = _ANY_WORD.sub(_fold_homoglyphs, _canon(text)).lower()
    return [m.group(0).replace(" ", "") for m in _SPACED.finditer(canon)]


SCRIPT_TABLE, SCRIPT_STOP = scripts.build(_canon)


def mostly_latin(text: str) -> bool:
    other = len(_OTHER_LETTER.findall(text or ""))
    return other == 0 or len(_LATIN.findall(text or "")) >= other


def words_of(text: str) -> list[str]:
    return _WORD.findall(norm(text))


@dataclass(frozen=True, slots=True)
class Tok:
    word: str
    clause: int


def tokens_of(text: str) -> list[Tok]:
    """Words with a clause number; punctuation breaks a clause, and so do a few joining words."""
    t = norm(text)
    out: list[Tok] = []
    clause = 0
    pos = 0
    for m in re.finditer(rf"{_LETTER}+(?:'{_LETTER}+)?|[;:!?\n]|\.(?=\s|$)", t):
        piece = m.group(0)
        if not piece[0].isalpha():
            clause += 1
            continue
        if piece in _BREAK_WORDS:
            clause += 1
            continue
        out.append(Tok(piece, clause))
        pos = m.end()
    del pos
    return out


def noun_stem(word: str) -> str:
    w = word.lower().removesuffix("'s")
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("sses", "xes", "ches", "shes")) and len(w) > 4:
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is")) and len(w) > 3:
        return w[:-1]
    return w


def verb_stems(word: str) -> set[str]:
    """Candidate base forms of a word, whole-word only (never a prefix)."""
    w = word.lower().removesuffix("'s")
    out = {w}
    if w.endswith("ies") and len(w) > 4:
        out.add(w[:-3] + "y")
    if w.endswith("es") and len(w) > 3:
        out.add(w[:-2])
    if w.endswith("s") and len(w) > 2:
        out.add(w[:-1])
    for suffix in ("ing", "ed"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 2:
            base = w[: -len(suffix)]
            out.add(base)
            out.add(base + "e")
            if len(base) > 2 and base[-1] == base[-2]:
                out.add(base[:-1])
            if suffix == "ed" and base.endswith("i"):
                out.add(base[:-1] + "y")
    return out


# ---------------------------------------------------------------------------- verb families

FAMILIES: dict[str, frozenset[str]] = {
    "CHANGE": frozenset(
        "change replace switch swap alter modify migrate upgrade overhaul scrap abandon ditch "
        "discard retire remove convert rebuild restructure reorganise reorganize rework "
        "badal badlen badalna tabdeel".split()
    ),
    "BUY": frozenset(
        "buy purchase acquire order procure get obtain invest bought kharid khareed kharidna "
        "kharidein kharidain kharidenge".split()
    ),
    "RENT": frozenset("rent lease borrow subscribe share outsource kiraya kiraye kiray".split()),
    "HIRE": frozenset("hire recruit employ onboard appoint engage bharti".split()),
    "ADD": frozenset("add increase expand extend grow barha barhana izafa".split()),
    "CLOSE": frozenset("close shut".split()),
    "STOP": frozenset(
        "stop halt cease discontinue quit cancel end drop suspend pause band".split()
    ),
    "USE": frozenset("use adopt rely install deploy operate istemal istamal".split()),
    "CUT": frozenset("cut reduce lower slash decrease trim shrink kam ghata ghatana".split()),
    "RAISE": frozenset("raise hike increase boost barha barhana barhayen".split()),
    "MOVE": frozenset("move relocate shift transfer".split()),
    "OPEN": frozenset("open launch khol kholna".split()),
    "PROMOTE": frozenset("market advertise promote".split()),
    "MAKE": frozenset("make produce manufacture build create".split()),
    "ACCEPT": frozenset("accept receive take".split()),
    "OFFER": frozenset("offer give provide grant".split()),
    "SELL": frozenset("sell bech becho bechna".split()),
    "FIRE": frozenset("fire dismiss sack terminate retrench nikalna nikal".split()),
}
# Words that are also common nouns: after a determiner they are the noun, not the verb.
NOUN_TOO = frozenset(
    "change order market cut offer increase raise rent lease share drop switch move end stop "
    "close sale open build use fire".split()
)
DETERMINERS = frozenset(
    "the a an our your their my his her its this that these those each every any some "
    "another one no".split()
)
NEGATIONS = frozenset(
    "not no never dont don't doesnt doesn't without avoid avoiding instead rather skip skipping "
    "nahi na bagair bina cannot can't".split()
)


def verb_families(word: str) -> frozenset[str]:
    stems = verb_stems(word)
    return frozenset(name for name, members in FAMILIES.items() if stems & members)


# -------------------------------------------------------------------------- object vocabulary

NEW_WORDS = frozenset("new naya naye nayi another replacement fresh".split())
HIRE_FILLER = frozenset(
    "more new extra additional another part time full temporary permanent junior senior".split()
)
STAFF_WORDS = frozenset(
    """developer accountant designer plumber marketer rep agent agency cleaner cook guard waiter
    teacher nurse tailor electrician mechanic receptionist intern freelancer contractor consultant
    engineer technician supervisor secretary bookkeeper trainer""".split()
) | frozenset(
    "staff employee worker person people anyone anybody someone somebody clerk assistant helper "
    "cashier driver salesman salesperson team hand labour labor manager".split()
)
SHOP_WORDS = frozenset(
    "shop store branch outlet site location office warehouse premise showroom".split()
)
GENERIC = frozenset(
    """system software tool app application machine equipment thing process solution setup platform
    device service way approach new more extra additional old current existing same own all
    something anything everything one it them they we you our your use make take keep have do work
    business customer client order time""".split()
)
STOPWORDS = frozenset(
    """we i you they he she it is are was were be been am of to for in on at by with from the a an
    and or if so as that this these those our your their my his her its not no than then also just
    only still even any some can will would should could may might must do does did have has had
    hum ham aap ap hamara hamari hamare ko ka ki ke ye yeh wo woh mein me se par pe aur bhi koi
    naya naye nayi apna apni apne hai hain tha thi""".split()
    + """के का की है हैं हम आप यह वह में से को पर और भी कोई नहीं
    کے کا کی ہے ہیں ہم آپ یہ وہ میں سے کو پر اور بھی کوئی نہیں
    في من على الى عن هذا هذه نحن انت هو هي و ان كان لا ما""".split()
)
STOPWORDS = STOPWORDS | frozenset(_canon(w) for w in STOPWORDS)


def object_key(word: str) -> str:
    stem = noun_stem(word)
    if stem in STAFF_WORDS:
        return "STAFF"
    if stem in SHOP_WORDS:
        return "SHOP"
    return stem


# ------------------------------------------------------------------------------ amounts

UNITS = {
    "crore": Decimal(10_000_000), "crores": Decimal(10_000_000), "cr": Decimal(10_000_000),
    "crs": Decimal(10_000_000), "کروڑ": Decimal(10_000_000),
    "करोड़": Decimal(10_000_000),
    "lakh": Decimal(100_000), "lakhs": Decimal(100_000), "lac": Decimal(100_000),
    "lacs": Decimal(100_000), "لاکھ": Decimal(100_000),
    "لاک": Decimal(100_000), "लाख": Decimal(100_000),
    "hazar": Decimal(1000), "hazaar": Decimal(1000), "thousand": Decimal(1000),
    "thousands": Decimal(1000), "k": Decimal(1000), "ہزار": Decimal(1000),
    "हज़ार": Decimal(1000), "हजार": Decimal(1000),
    "million": Decimal(1_000_000), "millions": Decimal(1_000_000), "mn": Decimal(1_000_000),
    "m": Decimal(1_000_000), "billion": Decimal(1_000_000_000),
    "billions": Decimal(1_000_000_000), "bn": Decimal(1_000_000_000),
    "arab": Decimal(1_000_000_000),
}  # fmt: skip
UNITS = {_canon(k): v for k, v in UNITS.items()}
_UNIT_ALT = "|".join(sorted((re.escape(u) for u in UNITS), key=len, reverse=True))
_NUM = r"(?:\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})+,\d{3}|\d+)(?:\.\d+)?"
_AMOUNT = re.compile(
    rf"(?<![\d,.])(?P<num>{_NUM})(?:\s*(?P<unit>{_UNIT_ALT})(?![^\W\d_]))?(?![\d])", re.IGNORECASE
)
_CUR_WORDS = (
    r"rs|pkr|inr|usd|eur|gbp|aed|sar|rupees?|rupay[ae]?|rupe[ey]s?|dollars?|dirhams?|"
    "روپے|روپیہ|रुपये|"
    "रुपए|ريال|ريالات|درهم|دراهم|دينار|جنيه"
)
_CUR_WORDS = _canon(_CUR_WORDS)
_CUR_BEFORE = re.compile(rf"(?:(?<![^\W\d_])(?:{_CUR_WORDS})|[₹$£€])\s*$")
_CUR_AFTER = re.compile(rf"^\s*(?:/-|(?:{_CUR_WORDS})(?![^\W\d_])|[₹$£€])")
_RANGE_JOIN = re.compile(r"^\s*(?:-|–|—|to|se)\s*$")
_BETWEEN_AND = re.compile(r"(?:between|from)\s+(?:rs|pkr|inr|usd|[₹$])?\s*$")
_AND_JOIN = re.compile(r"^\s+and\s+$")

COST_CUES = frozenset(
    """buy bought buying purchase purchased cost costs costing pay pays paying paid price priced
    invest investing invested spend spent spending get install subscription subscribe fee fees
    budget rent lease upgrade afford quote quoted expense expenses kharid khareed lagat lagega
    lagenge lagta kharcha kharch qeemat keemat daam dam ada""".split()
)
INCOME_CUES = frozenset(
    """sell sold selling sale sales earn earns earned earning earnings income revenue profit
    profits save saves saved saving savings gain gains turnover collect collected charge charged
    charging bech becho bechna kama kamao kamai munafa bachat bacha""".split()
)
STRONG_COST = frozenset("buy purchase invest pay spend cost price kharid khareed".split())
QUANTITY_NOUNS = frozenset(
    """staff people person persons employees workers users customers clients items pieces units
    products orders days weeks months years hours minutes mins seconds branches shops stores
    locations sites percent times visits calls messages sms chats tables chairs rooms""".split()
)
LENGTH_NOUNS = frozenset(
    "cable wire pipe rope tape wide long high deep tall away apart metre metres meter".split()
)
CURRENCY_OF = (
    (re.compile(r"usd|dollar|\$"), "USD"),
    (re.compile(r"eur|€"), "EUR"),
    (re.compile(r"gbp|£"), "GBP"),
    (re.compile(_canon("aed|dirham|درهم|دراهم")), "AED"),
    (re.compile(_canon("sar|riyal|ريال|ريالات")), "SAR"),
    (re.compile(_canon("dinar|دينار|جنيه")), "OTHER"),
)


@dataclass(frozen=True, slots=True)
class Amount:
    value: Decimal
    raw: str
    start: int
    end: int
    unit: str | None
    currency: str | None  # None: no currency marker next to it
    role: str  # cost, income, ambiguous, none
    in_range: bool = False
    period: str = ""  # month, year, week, day or "" (one-off)


def _currency_name(marker: str) -> str:
    for pattern, name in CURRENCY_OF:
        if pattern.search(marker):
            return name
    return "RS"


def _cue_role(word: str) -> str | None:
    stems = verb_stems(word)
    if stems & INCOME_CUES:
        return "income"
    if stems & COST_CUES:
        return "cost"
    return None


def _clause_part(text: str, start: int, end: int) -> tuple[list[str], list[str]]:
    """The words before `start` and after `end` that share the number's clause."""
    before = text[max(0, start - 300) : start]
    cut = 0
    for brk in _CLAUSE_BREAK.finditer(before):
        cut = brk.end()
    before = before[cut:]
    after = text[end : end + 300]
    m = _CLAUSE_BREAK.search(after)
    if m:
        after = after[: m.start()]
    before_words = [w for w in _WORD.findall(before)]
    after_words = [w for w in _WORD.findall(after)]
    # a joining word ends the clause on either side
    for i in range(len(before_words) - 1, -1, -1):
        if before_words[i] in _BREAK_WORDS or before_words[i] == "and":
            before_words = before_words[i + 1 :]
            break
    for i, w in enumerate(after_words):
        if w in _BREAK_WORDS or w == "and":
            after_words = after_words[:i]
            break
    return before_words, after_words


_PERIOD = re.compile(
    r"\s*(?:/-)?\s*(?:(?:/|per|a|every|each|har|ek)\s*"
    r"(month|mo|year|yr|week|day|mahina|mahine|saal)\b|"
    r"(monthly|yearly|annually|weekly|daily|mahana|salana)\b)"
)
_PERIOD_ANY = re.compile(
    r"(?:per|a|every|each|/|ek)\s*(month|year|week)\b|\b(monthly|yearly|annually|weekly|mahana|salana)\b"
)
_PERIOD_OF = {
    "month": "month", "mo": "month", "monthly": "month", "mahina": "month", "mahine": "month",
    "mahana": "month", "year": "year", "yr": "year", "yearly": "year", "annually": "year",
    "saal": "year", "salana": "year", "week": "week", "weekly": "week", "day": "day",
    "daily": "day",
}  # fmt: skip
_EACH = re.compile(
    r"\s*(?:/-)?\s*(?:each|apiece|a piece|every|har ek|per\s+(?:piece|unit|item|head|person|user|"
    r"seat|device|tablet|branch|shop))\b"
)
_CUR_PREFIX = r"(?:(?:rs|pkr|inr|usd|eur|gbp|aed|sar)\s*|[₹$£€]\s*)?"
_QTY_DIGITS = re.compile(
    r"(\d{1,4})\s+(?:[a-z]+\s+){0,2}(?:at|@|for|of|x|×)\s+" + _CUR_PREFIX + "$"
)
_QTY_WORD = re.compile(r"\b([a-z]+)\s+(?:[a-z]+\s+)?(?:at|@|for|of|x)\s+" + _CUR_PREFIX + "$")


def _period_after(post: str) -> str:
    m = _PERIOD.match(post)
    return _PERIOD_OF.get(m.group(1) or m.group(2) or "", "") if m else ""


def _period_of_text(text: str) -> str:
    m = _PERIOD_ANY.search(text)
    return _PERIOD_OF.get((m.group(1) or m.group(2)) if m else "", "")


def _quantity(before: str, post: str) -> int:
    """ "3 tablets at Rs 20,000 each": the figure is per piece, so it is 3 times as much."""
    if not _EACH.match(post):
        return 1
    m = _QTY_DIGITS.search(before)
    if m:
        return max(1, int(m.group(1)))
    w = _QTY_WORD.search(before)
    if w and w.group(1) in SMALL_NUMBER_WORDS and w.group(1) != "do":
        return SMALL_NUMBER_WORDS[w.group(1)]
    return 1


def _value(num: str, unit: str | None) -> Decimal | None:
    if len(num) > 18:
        return Decimal(10**18)  # absurdly large: above any ceiling, never costly to compare
    try:
        value = Decimal(num.replace(",", ""))
    except InvalidOperation:
        return None
    return value * UNITS[unit.lower()] if unit else value


# ------------------------------------------------------------ number words (five languages)

_SMALL_WORDS = """
one 1 two 2 three 3 four 4 five 5 six 6 seven 7 eight 8 nine 9 ten 10 eleven 11 twelve 12
thirteen 13 fourteen 14 fifteen 15 sixteen 16 seventeen 17 eighteen 18 nineteen 19 twenty 20
thirty 30 forty 40 fifty 50 sixty 60 seventy 70 eighty 80 ninety 90
ek 1 do 2 teen 3 char 4 paanch 5 panch 5 chhe 6 chay 6 saat 7 aath 8 nau 9 das 10 gyarah 11
barah 12 terah 13 chaudah 14 pandrah 15 solah 16 satrah 17 atharah 18 unnees 19 bees 20
pachees 25 tees 30 chalis 40 pachas 50 saath 60 sattar 70 assi 80 nabbe 90
एक 1 दो 2 तीन 3 चार 4 पाँच 5 पांच 5 छह 6 छः 6 सात 7 आठ 8 नौ 9 दस 10 बीस 20 पच्चीस 25 तीस 30
चालीस 40 पचास 50 साठ 60 सत्तर 70 अस्सी 80 नब्बे 90
ایک 1 دو 2 تین 3 چار 4 پانچ 5 چھ 6 سات 7 آٹھ 8 نو 9 دس 10 بیس 20 پچیس 25 تیس 30 چالیس 40
پچاس 50 ساٹھ 60 ستر 70 اسی 80 نوے 90
واحد 1 اثنان 2 اثنین 2 ثلاثة 3 ثلاث 3 اربعة 4 اربع 4 خمسة 5 خمس 5 ستة 6 سبعة 7 ثمانية 8 تسعة 9
عشرة 10 عشرين 20 ثلاثين 30 اربعين 40 خمسين 50 ستين 60 سبعين 70 ثمانين 80 تسعين 90
عشرون 20 ثلاثون 30 اربعون 40 خمسون 50 ستون 60 سبعون 70 ثمانون 80 تسعون 90
"""
_MAGNITUDE_WORDS = """
hundred 100 sau 100 सौ 100 سو 100 مئة 100 مائة 100 مئتين 200 مئتان 200
thousand 1000 hazar 1000 hazaar 1000 हज़ार 1000 हजार 1000 ہزار 1000 ألف 1000 الاف 1000
lakh 100000 lac 100000 लाख 100000 لاکھ 100000
million 1000000 مليون 1000000 crore 10000000 करोड़ 10000000 کروڑ 10000000
billion 1000000000 arab 1000000000 مليار 1000000000
"""


def _word_table(spec: str) -> dict[str, int]:
    parts = spec.split()
    return {_canon(parts[i]): int(parts[i + 1]) for i in range(0, len(parts), 2)}


SMALL_NUMBER_WORDS = _word_table(_SMALL_WORDS)
MAGNITUDE_WORDS = _word_table(_MAGNITUDE_WORDS)
_ARTICLES = frozenset({"a", "an"})
_JOINERS = frozenset({"and", "aur", "و"})
_FOLLOWING_CURRENCY = re.compile(rf"\s*(?:{_CUR_WORDS})(?![^\W\d_])")


def _number_words_to_digits(t: str) -> str:
    """Spell-outs such as "fifty thousand", "pachas hazar", "पचास हज़ार" or "خمسين ألف" become
    digits. A run of number words counts only with a magnitude word (thousand, lakh, hazar...) or
    a currency word right after it, so "one cashier" and "do you" are left alone."""
    out: list[str] = []
    last = 0
    words = list(_ANY_WORD.finditer(t))
    i = 0
    while i < len(words):
        j = i
        total = current = 0
        seen_magnitude = False
        seen_number = False
        valid_end = i
        while j < len(words):
            w = words[j].group(0)
            if j > i and t[words[j - 1].end() : words[j].start()].strip():
                break  # something other than spaces between the words
            if w in SMALL_NUMBER_WORDS:
                current += SMALL_NUMBER_WORDS[w]
                seen_number = True
            elif w in MAGNITUDE_WORDS:
                value = MAGNITUDE_WORDS[w]
                if value < 1000:
                    current = (current or 1) * value if value == 100 else current + value
                else:
                    total += (current or 1) * value
                    current = 0
                seen_magnitude = True
                seen_number = True
            elif (
                w in _ARTICLES
                and j == i
                and j + 1 < len(words)
                and words[j + 1].group(0) in MAGNITUDE_WORDS
            ):
                current += 1
            elif w in _JOINERS and seen_number and j > i:
                j += 1
                continue
            else:
                break
            valid_end = j
            j += 1
        if not seen_number:
            i += 1
            continue
        end = words[valid_end].end()
        after_digit = t[: words[i].start()].rstrip()[-1:].isdigit()  # "5 lakh": a unit, not words
        small_seen = any(words[k].group(0) in SMALL_NUMBER_WORDS for k in range(i, valid_end + 1))
        if not after_digit and (
            (seen_magnitude and (small_seen or _FOLLOWING_CURRENCY.match(t, end)))
            or (small_seen and _FOLLOWING_CURRENCY.match(t, end))
        ):
            out.append(t[last : words[i].start()])
            out.append(str(total + current))
            last = end
        i = valid_end + 1
    out.append(t[last:])
    return "".join(out)


def parse_amounts(
    text: str, *, assume_money: bool = False, latin: bool | None = None
) -> list[Amount]:
    """The money figures in `text`. With `assume_money` (a budget text) every figure counts except
    counts of things and percentages; otherwise a figure needs a currency marker or a cost/income
    word in its own clause, and a number with neither is ignored."""
    t = _number_words_to_digits(norm(text))
    latin = mostly_latin(t) if latin is None else latin
    raw_matches = list(_AMOUNT.finditer(t))
    spans: list[tuple[int, int, Decimal, str | None, str, bool]] = []
    i = 0
    while i < len(raw_matches):
        m = raw_matches[i]
        value = _value(m["num"], m["unit"])
        start, end, raw, unit, ranged = m.start(), m.end(), m.group(0), m["unit"], False
        if value is not None and i + 1 < len(raw_matches):
            nxt = raw_matches[i + 1]
            between = t[end : nxt.start()]
            joined = bool(_RANGE_JOIN.match(between)) or (
                bool(_AND_JOIN.match(between))
                and bool(_BETWEEN_AND.search(t[max(0, start - 40) : start]))
            )
            high = _value(nxt["num"], nxt["unit"])
            if joined and high is not None:
                value, end, raw, unit, ranged = (
                    max(value, high),
                    nxt.end(),
                    t[start : nxt.end()],
                    nxt["unit"],
                    True,
                )
                i += 1
        if value is not None:
            spans.append((start, end, value, unit, raw.strip(), ranged))
        i += 1
    out: list[Amount] = []
    for start, end, value, unit, raw, ranged in spans:
        before = t[max(0, start - 60) : start]
        after = t[end : end + 60]
        cur_b = _CUR_BEFORE.search(before)
        cur_a = _CUR_AFTER.match(after)
        marker = cur_b.group(0).strip() if cur_b else (cur_a.group(0).strip() if cur_a else "")
        currency = _currency_name(marker) if marker else None
        post = after[cur_a.end() :] if cur_a else after
        value = value * _quantity(t[max(0, start - 60) : start], post)
        period = _period_after(post)
        before_words, after_words = _clause_part(t, start, end + (cur_a.end() if cur_a else 0))
        after_first = after_words[0] if after_words else ""
        if after.lstrip().startswith("%") or after_first in {"percent", "pct"}:
            role = "none"
        elif assume_money:
            role = "cost"
            if currency is None and (
                after_first in QUANTITY_NOUNS or noun_stem(after_first) in QUANTITY_NOUNS
            ):
                role = "none"
        else:
            role = _role(value, unit, currency, before_words, after_words, after_first, latin)
        out.append(Amount(value, raw, start, end, unit, currency, role, ranged, period))
    return out


def _role(
    value: Decimal,
    unit: str | None,
    currency: str | None,
    before: list[str],
    after: list[str],
    after_first: str,
    latin: bool,
) -> str:
    near: list[tuple[float, str]] = []
    for idx, w in enumerate(reversed(before[-6:])):
        role = _cue_role(w)
        if role:
            near.append((idx + 1.0, role))
    for idx, w in enumerate(after[:3]):
        role = _cue_role(w)
        if role:
            near.append((idx + 1.5, role))
    cue = None
    if near:
        best = min(d for d, _ in near)
        roles = {r for d, r in near if d == best}
        cue = roles.pop() if len(roles) == 1 else "ambiguous"
    if not latin:
        return "ambiguous" if currency else "unclear"
    if currency:
        return cue or "cost"
    if after_first in QUANTITY_NOUNS or (
        noun_stem(after_first) in QUANTITY_NOUNS
        or (
            len(after_first) > 3
            and after_first.endswith("s")
            and unit is None
            and (not before or before[-1] not in DETERMINERS)
        )
    ):
        return "none"
    if unit and unit.lower() == "m":
        if after_first in LENGTH_NOUNS or not (set(before[-6:]) & STRONG_COST):
            return "none"
    if unit is None and value < 1000:
        return "none"
    if unit is None and 1990 <= value <= 2100 and before and before[-1] in {
        "in", "by", "since", "from", "until", "till", "year",
    }:  # fmt: skip
        return "none"
    return cue or "unclear"


# ------------------------------------------------------------------------------ budget

_FLOOR = re.compile(
    r"\b(?:at least|atleast|minimum|min|no less than|not less than|more than|over|above|"
    r"kam se kam|se zyada|starting|start from)\b"
)
_CEIL = re.compile(
    r"\b(?:under|below|up to|upto|within|max|maximum|at most|atmost|or less|or under|or below|"
    r"not more than|no more than|less than|not exceed|exceed|not cross|cross|limit|cap|ceiling|"
    r"tak|se kam|zyada se zyada|around|about|approx|approximately|only)\b"
    r"|(?:se\s+)?(?:zyada|ziada|upar|oopar)\s+nahi(?:n)?"
)
_BUDGET_SPLIT = re.compile(
    r"[,;]|\.(?=\s)|\b(?:and|so|with|since|because|but|while|although|though|lekin|aur|magar)\b"
)
_ZERO_BUDGET = re.compile(
    r"\b(?:no budget|zero budget|nil|nothing|zero|free only|budget nahi|koi budget nahi|"
    r"bilkul nahi|no money|0 budget)\b"
)


@dataclass(frozen=True, slots=True)
class Ceiling:
    value: Decimal | None  # None: no ceiling found
    currency: str | None
    floor_only: bool
    raw: str
    period: str = ""


def parse_ceiling(text: str) -> Ceiling:
    """The ceiling a budget text states. A floor ('at least', 'minimum') is never a ceiling and
    never hides a ceiling in a later part joined by so/with/since/because/and/but."""
    t = norm(text)
    amounts = [a for a in parse_amounts(t, assume_money=True) if a.role != "none"]
    if not amounts:
        if _ZERO_BUDGET.search(t):
            return Ceiling(Decimal(0), None, False, "zero")
        return Ceiling(None, None, False, "")
    pieces: list[tuple[int, int]] = []
    last = 0
    for m in _BUDGET_SPLIT.finditer(t):
        pieces.append((last, m.start()))
        last = m.end()
    pieces.append((last, len(t)))
    ceilings: list[Amount] = []
    floors: list[Amount] = []
    for a in amounts:
        piece = next((t[s:e] for s, e in pieces if s <= a.start < max(e, s + 1)), t)
        if a.in_range or _CEIL.search(piece) or not _FLOOR.search(piece):
            ceilings.append(a)
        else:
            floors.append(a)
    if not ceilings:
        return Ceiling(None, floors[0].currency if floors else None, True, floors[0].raw)
    low = min(ceilings, key=lambda a: a.value)
    return Ceiling(low.value, low.currency, False, low.raw, _period_of_text(t))


# ------------------------------------------------------------------------------ deadline

NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "ek": 1, "do": 2, "teen": 3, "char": 4,
    "paanch": 5, "panch": 5, "chhe": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
}  # fmt: skip
UNIT_DAYS = {
    "hour": 1 / 24, "hours": 1 / 24, "ghanta": 1 / 24, "ghantay": 1 / 24, "ghante": 1 / 24,
    "day": 1.0, "days": 1.0, "din": 1.0, "week": 7.0, "weeks": 7.0, "hafta": 7.0, "haftay": 7.0,
    "hafte": 7.0, "haftey": 7.0, "month": 30.0, "months": 30.0, "mahina": 30.0, "mahine": 30.0,
    "mahinay": 30.0, "year": 365.0, "years": 365.0, "saal": 365.0,
}  # fmt: skip
_DURATION = re.compile(
    r"(?P<n>\d+|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")"
    r"(?:\s*(?:-|to)\s*(?P<m>\d+))?\s+(?P<u>" + "|".join(UNIT_DAYS) + r")\b"
)
_TIMELINE_CUE = re.compile(
    r"\b(?:in|within|takes?|taking|ready|done|finish(?:ed)?|live|launch(?:ed)?|deliver(?:ed|y)?|"
    r"set ?up|complete[sd]?|lagega|lagenge|over|after|by)\b"
)
_INSTANT = re.compile(r"\b(?:today|aaj|same day|immediately|instant(?:ly)?|right away|abhi)\b")
_TOMORROW = re.compile(r"\b(?:tomorrow|kal)\b")
_NEXT = re.compile(r"\b(?:next|this|agle|is)\s+(week|month|hafta|hafte|mahina|mahine)\b")


def parse_days(text: str, *, need_cue: bool) -> float | None:
    """A duration in days, the longest one stated; None when there is none to read."""
    t = norm(text)
    best: float | None = None
    for m in _DURATION.finditer(t):
        if need_cue and not (
            _TIMELINE_CUE.search(t[max(0, m.start() - 24) : m.start()])
            or re.match(r"\s*(?:mein|me|tak)\b", t[m.end() :])
        ):
            continue
        n = m["m"] or m["n"]
        count = float(n) if n.isdigit() else float(NUMBER_WORDS[n])
        days = count * UNIT_DAYS[m["u"]]
        best = days if best is None else max(best, days)
    for m in _NEXT.finditer(t):
        days = 30.0 if m.group(1) in {"month", "mahina", "mahine"} else 7.0
        best = days if best is None else max(best, days)
    if _TOMORROW.search(t):
        best = 1.0 if best is None else max(best, 1.0)
    if _INSTANT.search(t):
        best = 0.0 if best is None else max(best, 0.0)
    return best


# ------------------------------------------------------------------------- the option


@dataclass(frozen=True, slots=True)
class _Option:
    text: str
    tokens: list[Tok]
    latin: bool
    unread: int = 0  # words in another script that the reading tables do not know


def _option(text: str) -> _Option:
    if not _OTHER_LETTER.search(text):  # no Urdu, Arabic, Hindi or other script letter at all
        return _Option(text, tokens_of(lex.take_on_as_hire(norm(text))), True)
    mapped, _, unread = scripts.to_english(
        norm(text),
        SCRIPT_TABLE,
        SCRIPT_STOP,
        is_known=lambda w: (
            w in SMALL_NUMBER_WORDS or w in MAGNITUDE_WORDS or bool(re.fullmatch(_CUR_WORDS, w))
        ),
        is_person=lambda w: object_key(w) == "STAFF",
        is_verb=lambda w: bool(verb_families(w)),
    )
    english = [w for w in _WORD.findall(mapped) if w.isascii()]
    readable = any(verb_families(w) or w == "keep" for w in english)  # a verb was recognised
    # these languages put the verb last: the marker makes every verb read the words before it
    marked = re.sub(r"([;:!?.\n])", r" karein \1", mapped) + " karein"
    return _Option(mapped, tokens_of(lex.take_on_as_hire(marked)), readable, unread)


CLOSE_ADVERB_NEXT = frozenset({"to", "by", "enough", "together", "friends", "friend"})
INVESTIGATE = frozenset(
    """measure measuring check checking investigate investigating evaluate evaluating assess
    assessing review reviewing audit auditing consider considering whether study studying explore
    exploring compare comparing worth research researching""".split()
)
NOT_AN_OPTION = frozenset(
    "option possible worth needed necessary allowed advisable wise required viable".split()
)
RU_VERB_FINAL = frozenset({"lein", "karein", "karen", "kijiye", "kar", "dein", "karo"})


def _proposed(tokens: list[Tok], i: int) -> bool:
    """False when tokens[i] is negated, only investigated ("measure whether replacing..."), or
    called "not an option / not possible" after it: it is named, not proposed."""
    clause = tokens[i].clause
    for j in range(max(0, i - 4), i):
        if tokens[j].clause != clause:
            continue
        if tokens[j].word in INVESTIGATE or (i - j <= 3 and tokens[j].word in NEGATIONS):
            return False
    after = [t.word for t in tokens[i + 1 : i + 7] if t.clause == clause]
    for k, word in enumerate(after):
        if word in {"not", "isnt", "isn't", "never", "unnecessary"} and (
            word == "unnecessary" or any(x in NOT_AN_OPTION for x in after[k + 1 : k + 3])
        ):
            return False
    return True


def _is_verb_at(tokens: list[Tok], i: int, families: frozenset[str]) -> frozenset[str]:
    """The families of tokens[i] that are in `families`, empty when it is a noun or negated."""
    w = tokens[i].word
    found = verb_families(w) & families
    if not found:
        return frozenset()
    clause = tokens[i].clause
    following = [t.word for t in tokens[i + 1 : i + 6] if t.clause == clause]
    if any(t.word in RU_VERB_FINAL for t in tokens if t.clause == clause):
        following += [t.word for t in tokens[max(0, i - 3) : i] if t.clause == clause]
    if "FIRE" in found and not any(object_key(x) == "STAFF" for x in following):
        found = found - {"FIRE"}  # a fire drill, an alarm: only "fire <a person>" is dismissing
    if "CLOSE" in found and following[:1] and following[0] in CLOSE_ADVERB_NEXT:
        found = found - {"CLOSE"}  # "close to the station", "close by": near, not shut
    if not found:
        return frozenset()
    if w in NOUN_TOO and i > 0 and tokens[i - 1].word in DETERMINERS:
        if tokens[i - 1].clause == clause:
            return frozenset()
    if not _proposed(tokens, i):
        return frozenset()
    return found


def _before(tokens: list[Tok], i: int, size: int = 5) -> list[Tok]:
    out: list[Tok] = []
    for j in range(i - 1, max(-1, i - 1 - size), -1):
        if tokens[j].clause != tokens[i].clause:
            break
        out.append(tokens[j])
    return out[::-1]


def _ru_option(tokens: list[Tok]) -> bool:
    return any(
        t.word in {"lein", "karein", "karen", "kijiye", "kar", "dein", "karo"} for t in tokens
    )


def _window(tokens: list[Tok], i: int, size: int = 6) -> list[Tok]:
    out: list[Tok] = []
    for j in range(i + 1, min(len(tokens), i + 1 + size)):
        if tokens[j].clause != tokens[i].clause:
            break
        if (
            verb_families(tokens[j].word)
            and tokens[j].word not in NOUN_TOO
            and any(t.word not in STOPWORDS and t.word not in DETERMINERS for t in out)
        ):
            break  # a second verb phrase starts: its objects are not this verb's
        out.append(tokens[j])
    return out


# ------------------------------------------------------------------------- cannot_change

OUTCOME_NOUNS = frozenset(
    """downtime delay loss lost error mistake stockout waste outage interruption failure breakdown
    complaint risk disruption wait lateness theft damage shortage queue absence closure
    slowdown""".split()
)
OUTCOME_VERBS = frozenset("lose miss waste damage risk".split())
AVOID_CUES = frozenset(
    """never no without avoid avoiding prevent prevents preventing eliminate eliminates reduce
    reduces minimise minimize protect protects ensure ensures cover backup zero guard stop
    stops""".split()
)
_MODAL = re.compile(
    r"\b(?:cannot|can't|cant|can not|couldn't|could not|unable to|not able to|won't|wont|"
    r"will not|not allowed to|are not allowed to|mustn't|must not|never|"
    r"(?:do not|don't|dont|doesn't|does not) want to|not willing to|refuse to|no way to)\b"
)
_RU_NEG = frozenset("nahi nahin nhi".split())
_KEEP = re.compile(
    r"^(?:we )?(?:must |have to |need to |has to )?(?:keep(?:ing)?|stuck with|stay(?:ing)? with)\s+"
)


@dataclass(frozen=True, slots=True)
class _Lim:
    kind: str  # action, afford_object, avoid_outcome, object_only, unknown_verb, location, size,
    # topic, unreadable
    families: frozenset[str] = frozenset()
    objects: tuple[str, ...] = ()
    outcomes: tuple[str, ...] = ()
    verb: str = ""
    verb_final: bool = False  # Roman Urdu puts the object before the verb
    payload: tuple[float, str] | None = None


VAGUE = frozenset(
    """thing things stuff etc see above below discussed same before know what say said whatever
    anything something someone x y z it that this""".split()
)
_FILLER_AFTER = frozenset({"more", "new", "any", "afford", "to"})


def _content_objects(ws: list[str]) -> tuple[str, ...]:
    keys: list[str] = []
    for w in ws:
        if w in STOPWORDS or w in DETERMINERS or w in _FILLER_AFTER or w in VAGUE or len(w) < 2:
            continue
        if verb_families(w) and w not in NOUN_TOO and noun_stem(w) not in STAFF_WORDS:
            continue  # "stop taking cash": taking is a verb, cash is the object
        key = object_key(w)
        if key not in keys:
            keys.append(key)
    return tuple(keys)


def _has_content(ws: list[str]) -> bool:
    return any(w not in STOPWORDS and w not in DETERMINERS and w not in _FILLER_AFTER for w in ws)


def _concrete(objs: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(o for o in objs if o not in GENERIC and noun_stem(o) not in GENERIC)


def _action(fams: frozenset[str], after: list[str], verb: str, final: bool = False) -> _Lim:
    objs = _content_objects(after)
    if not objs and _has_content(after):
        return _Lim("unreadable")  # only filler after the verb: "cannot change the thing"
    return _Lim("action", fams, objs, verb=verb, verb_final=final)


_PROMISE = re.compile(r"\b(?:promise|promises|guarantee|guarantees|assure|ensure|pledge)\b")
PROMISE_WORDS = frozenset(
    "promise promises promised promising guarantee guarantees guaranteed guaranteeing assure "
    "assured ensure ensures pledge pledged".split()
)


def parse_limit(text: str) -> _Lim:
    """Read one cannot_change clause. See the module docstring for the semantics."""
    if not mostly_latin(text):
        return _Lim("unreadable")
    t = lex.take_on_as_hire(norm(text))
    ws = _WORD.findall(t)
    if not ws:
        return _Lim("unreadable")
    if lex.is_hiring_freeze(t):
        return _Lim("action", frozenset({"HIRE"}), (), verb="hire")
    places = lex.place_limit(t)
    if places:
        return _Lim("location", objects=places)
    size = lex.size_limit(t)
    if size:
        return _Lim("size", payload=(size.value, size.unit))
    promise = _PROMISE.search(t)
    if promise and _MODAL.search(t):  # "we cannot promise delivery days": about the promise
        objs = _content_objects(_WORD.findall(t[promise.end() :]))
        return _Lim("promise", objects=objs) if objs else _Lim("unreadable")
    topic = lex.topic_limit(t)
    if topic:
        return _Lim("topic", verb=topic)
    m = _MODAL.search(t)
    if m:
        rest = _WORD.findall(t[m.end() :])
        if rest and rest[0] == "afford":
            rest = rest[1:]
            if rest and rest[0] == "to":
                rest = rest[1:]
            first = next((w for w in rest if verb_families(w)), None)
            if rest and first == rest[0] and first not in NOUN_TOO:
                return _action(frozenset(verb_families(first)), rest[1:], first)
            if rest and rest[0] in OUTCOME_VERBS:
                return _Lim("avoid_outcome", outcomes=_content_objects(rest[1:]) or (rest[0],))
            outcomes = tuple(object_key(w) for w in rest if noun_stem(w) in OUTCOME_NOUNS)
            if outcomes:
                return _Lim("avoid_outcome", outcomes=outcomes)
            objs = _content_objects(rest)
            if not objs:
                return _Lim("unreadable")
            return _Lim("afford_object", frozenset({"BUY"}), objs, verb="afford")
        for idx, w in enumerate(rest):
            fams = verb_families(w)
            if fams:
                return _action(fams, rest[idx + 1 :], w)
        objs = _content_objects(rest)
        return _Lim("unknown_verb", objects=objs) if _concrete(objs) else _Lim("unreadable")
    if _RU_NEG & set(ws) and any(w.startswith("sak") for w in ws):
        for idx, w in enumerate(ws):
            fams = verb_families(w)
            if fams:
                others = [
                    o
                    for o in ws[:idx] + ws[idx + 1 :]
                    if not o.startswith("sak") and o not in _RU_NEG and o != "kar"
                ]
                return _action(fams, others, w, True)
        return _Lim("unreadable")
    stripped = _KEEP.sub("", t)
    sws = _WORD.findall(stripped)
    if sws and verb_families(sws[0]) and sws[0] not in NOUN_TOO and stripped == t:
        return _action(verb_families(sws[0]), sws[1:], sws[0])
    objs = _content_objects(sws)
    if not _concrete(objs):
        return _Lim("unreadable")
    return _Lim("object_only", frozenset({"CHANGE", "STOP"}), objs)


def _generic_only(objs: tuple[str, ...]) -> bool:
    return all(o in GENERIC or noun_stem(o) in GENERIC for o in objs)


_CLAUSE_SPLIT = re.compile(
    r"[;!?\n]|\.(?=\s|$)|,|\b(?:but|because|since|so|while|although|though|however|lekin|"
    r"magar|kyunke|kyunki)\b"
)
_SUBJECTS = frozenset("we i they you hum ham main wo woh".split())
_LIMIT_CUE = re.compile(
    r"\b(?:only|keep|keeping|stuck with|stay with|afford|fixed|frozen|not possible|"
    r"not an option|no more)\b"
)


def _is_limit_clause(clause: str) -> bool:
    ws = set(_WORD.findall(clause))
    return bool(
        _MODAL.search(clause)
        or (_RU_NEG & ws)
        or lex.is_hiring_freeze(clause)
        or lex._RESOURCE_CUE.search(clause)
        or lex.place_limit(clause)
        or lex.size_limit(clause)
        or _LIMIT_CUE.search(clause)
    )


def limit_clauses(text: str) -> list[str]:
    """The clauses of a stated limit that state a limit ("we can't hire; we can train" has one).
    With no limit wording at all the whole text is the one clause ("POS system")."""
    t = lex.take_on_as_hire(norm(text))
    clauses: list[str] = []
    for part in _CLAUSE_SPLIT.split(t):
        part = part.strip()
        if not part:
            continue
        words = _WORD.findall(part)
        if clauses and not (set(words) & _SUBJECTS) and not any(verb_families(w) for w in words):
            clauses[-1] += " " + part  # a list item: "the POS, the printer"
        else:
            clauses.append(part)
    found = [c for c in clauses if _is_limit_clause(c)]
    return found or [t]


def _check_cannot(option: _Option, limit: Limit) -> Verdict:
    rule = RULE_CANNOT_CHANGE
    if not option.latin:
        return _unknown(rule, "the option is not in a script this check can read")
    results = [_check_lim(option, parse_limit(c), limit.text) for c in limit_clauses(limit.text)]
    for status in ("violates", "unknown"):
        for verdict in results:
            if verdict.status == status:
                return verdict
    return results[0]


def _hits_in(option: _Option, words_wanted: Callable[[str], bool]) -> list[str]:
    toks = option.tokens
    return [t.word for i, t in enumerate(toks) if words_wanted(t.word) and _proposed(toks, i)]


def _check_special(option: _Option, lim: _Lim, limit_text: str) -> Verdict:
    rule = RULE_CANNOT_CHANGE
    nt = norm(option.text)
    if lim.kind == "location":
        known, unnamed = lex.option_places(option.text, nt)
        allowed = set(lim.objects)
        outside = [p for p in known if p not in allowed]
        if outside:
            return _violates(
                rule, f"the option goes beyond what the owner allows ({limit_text})", tuple(outside)
            )
        if lex.reaches_beyond(nt):
            return _violates(
                rule, f"the option reaches beyond the places allowed ({limit_text})", ("beyond",)
            )
        if unnamed:
            return _unknown(rule, "the option names a place this check does not know", unnamed)
        words = set(_WORD.findall(nt))
        if not known and words & lex.EXPANSION_VERBS:
            return _unknown(rule, "the option expands without naming where")
        return _ok(rule, "the option stays inside the places the owner allows")
    if lim.kind == "size" and lim.payload:
        value, unit = lim.payload
        found = lex.sizes_in(nt)
        same = [s for s in found if s.unit == unit]
        if any(s.value > value for s in same):
            return _violates(
                rule,
                f"the option needs more room than the owner has ({limit_text})",
                tuple(f"{s.value:g} {s.unit}" for s in same),
            )
        if same:
            return _ok(rule, "the option's size fits the limit")
        if found or set(_WORD.findall(nt)) & lex.SPACE_WORDS:
            return _unknown(rule, "the option needs space and states no size in the limit's unit")
        return _ok(rule, "the option needs no space")
    hits = _hits_in(option, lambda w: bool(lex.topic_hits(lim.verb, [w])))
    if hits:
        return _violates(
            rule,
            f"the option involves {lim.verb}, which the owner said they cannot ({limit_text})",
            tuple(hits[:3]),
        )
    return _ok(rule, f"the option does not involve {lim.verb}")


def _check_lim(option: _Option, lim: _Lim, limit_text: str) -> Verdict:
    rule = RULE_CANNOT_CHANGE
    if lim.kind == "unreadable":
        return _unknown(rule, "the stated limit could not be read (script, wording or too vague)")
    if lim.kind in {"location", "size", "topic"}:
        return _check_special(option, lim, limit_text)
    if lim.kind == "promise":
        for i, tok in enumerate(option.tokens):
            if tok.word in PROMISE_WORDS and _proposed(option.tokens, i):
                near = [
                    object_key(t.word)
                    for t in option.tokens[i + 1 : i + 8]
                    if t.clause == tok.clause
                ]
                shared = [o for o in lim.objects if o in near]
                if shared:
                    return _violates(
                        rule,
                        f"the option promises what the owner ruled out ({limit_text})",
                        (tok.word, *shared),
                    )
        return _ok(rule, "the option makes no promise the owner ruled out")
    toks = option.tokens
    keys = [object_key(t.word) for t in toks]
    if lim.kind == "avoid_outcome":
        return _check_outcome(toks, lim)
    families = set(lim.families)
    if "HIRE" in families or ("ADD" in families and "STAFF" in lim.objects):
        families |= {"HIRE", "ADD"}
    if "CHANGE" in families and lim.objects:
        families |= {"RAISE", "CUT", "BUY"}
    hire_any = "HIRE" in lim.families and set(lim.objects) <= {"STAFF"}
    wanted = tuple(o for o in lim.objects if o not in GENERIC and noun_stem(o) not in GENERIC)
    generic = tuple(o for o in lim.objects if o not in wanted)
    unknown_hit: Verdict | None = None
    if "CHANGE" in lim.families and wanted:
        for i, tok in enumerate(toks):  # "a new courier" replaces the one that cannot change
            if tok.word in NEW_WORDS and _proposed(toks, i):
                near = [object_key(t.word) for t in toks[i + 1 : i + 4] if t.clause == tok.clause]
                shared = [w for w in wanted if w in near]
                if shared:
                    return _violates(
                        rule,
                        f"the option brings in a new one of what cannot change ({limit_text})",
                        (tok.word, *shared),
                    )
    if lim.kind == "unknown_verb":
        hit = [w for w in wanted if w in keys]
        if hit:
            return _unknown(
                rule, "the limit's verb is not known and the option names its object", tuple(hit)
            )
        return _unknown(rule, "the limit's verb is not one this check enforces")
    for i, tok in enumerate(toks):
        fams = _is_verb_at(
            toks, i, frozenset(families | ({"RENT"} if lim.kind == "afford_object" else set()))
        )
        if not fams:
            continue
        window = _window(toks, i)
        if lim.verb_final or _ru_option(toks):
            window = _before(toks, i) + window
        if (
            "BUY" in fams
            and "BUY" not in lim.families
            and not any(t.word in NEW_WORDS for t in window)
        ):
            continue  # buying is changing only when it is a NEW one
        wkeys = [object_key(t.word) for t in window]
        needs_staff = "ADD" in fams and not (fams & set(lim.families)) and "HIRE" in lim.families
        if needs_staff and "STAFF" not in wkeys:
            continue
        if hire_any and "HIRE" in fams:
            roles = [
                t.word
                for t in window
                if t.word not in STOPWORDS
                and t.word not in DETERMINERS
                and t.word not in HIRE_FILLER
            ]
            return _violates(
                rule,
                f"the option hires, which the owner said they cannot do ({limit_text})",
                (tok.word, *roles[:2]),
            )
        rental = "RENT" in fams and not (fams & set(lim.families))
        if wanted:
            shared = [w for w in wanted if w in wkeys]
            need = len(wanted) if len(wanted) <= 2 else (len(wanted) + 1) // 2
            if len(shared) >= need:
                evidence = (tok.word, *shared)
                if rental:
                    unknown_hit = unknown_hit or _unknown(
                        rule,
                        "renting may also cost what the owner said they cannot afford",
                        evidence,
                    )
                    continue
                return _violates(
                    rule,
                    f"the option does what the owner said they cannot do ({limit_text})",
                    evidence,
                )
            if shared or (generic and any(g in wkeys or noun_stem(g) in wkeys for g in generic)):
                unknown_hit = unknown_hit or _unknown(
                    rule,
                    "the option shares only part of, or a generic word with, what is ruled out",
                    (tok.word, *shared),
                )
            continue
        if generic:
            shared_g = [g for g in generic if g in wkeys]
            if shared_g:
                evidence = (tok.word, *shared_g)
                if rental:
                    unknown_hit = unknown_hit or _unknown(
                        rule,
                        "renting may also cost what the owner said they cannot afford",
                        evidence,
                    )
                    continue
                return _violates(
                    rule,
                    f"the option does what the owner said they cannot do ({limit_text})",
                    evidence,
                )
            unknown_hit = unknown_hit or _unknown(
                rule,
                "the limit names only a generic object, so the option cannot be compared",
                (tok.word,),
            )
            continue
        if rental:
            continue
        if lim.kind == "action" and not (fams & set(lim.families)) and not needs_staff:
            continue
        return _violates(
            rule,
            f"the option does what the owner said they cannot do ({limit_text})",
            (tok.word,),
        )
    if unknown_hit:
        return unknown_hit
    return _ok(rule, "the option does not do what the owner said they cannot do")


def _check_outcome(toks: list[Tok], lim: _Lim) -> Verdict:
    rule = RULE_CANNOT_CHANGE
    stems = set(lim.outcomes)
    for i, tok in enumerate(toks):
        if object_key(tok.word) in stems or noun_stem(tok.word) in stems:
            near = [t.word for t in toks[max(0, i - 6) : i + 3] if t.clause == tok.clause]
            if set(near) & AVOID_CUES:
                continue
            return _unknown(
                rule,
                "an outcome the owner cannot afford is named, with no sign that it is avoided",
                (tok.word,),
            )
    return _ok(rule, "the option does not name an outcome the owner cannot afford")


# ------------------------------------------------------------------------------- tried

FAILED = re.compile(
    r"didn'?t work|did not work|doesn'?t work|does not work|not work|no luck|failed|\bfail\b|"
    r"useless|no use|no help|didn'?t help|did not help|not help|nothing changed|no change|"
    r"no effect|worse|wasted|waste of|ignored|gave up|gave it up|nahi chala|nahi chal|"
    r"nahi hua|kaam nahi|nakam|bekar|faida nahi|fayda nahi|kuch nahi|nahi kiya"
)
SUCCEEDED = re.compile(r"\b(?:worked|helped|success|successful|improved|kaam kiya|chal gaya)\b")
DIFFERENT = re.compile(
    r"\b(?:different|differently|unlike|another way|new approach|new way|other than|alternative)\b"
)
_NEGATED_TAIL = re.compile(
    r"\b(?:instead of|rather than|unlike|not|without|avoid(?:ing)?|in place of)\b"
)
_RU_INSTEAD = re.compile(r"\b(?:ki jagah|ke bajaye|ke bajay|ki bajaye|ke badle)\b")


def _tried_words(text: str) -> list[frozenset[str]]:
    """The comparable words of a text, each as its set of whole-word base forms."""
    out: list[frozenset[str]] = []
    seen: set[frozenset[str]] = set()
    for w in _WORD.findall(norm(text)):
        if w in STOPWORDS or w in DETERMINERS or noun_stem(w) in GENERIC or len(w) < 3:
            continue
        key = object_key(w)
        forms = frozenset({key}) if key in {"STAFF", "SHOP"} else frozenset(verb_stems(w))
        if forms not in seen:
            seen.add(forms)
            out.append(forms)
    return out


def _check_tried(option: _Option, item: TriedItem) -> Verdict:
    rule = RULE_TRIED
    if not (mostly_latin(item.what) and mostly_latin(item.outcome)):
        return _unknown(rule, "a thing the owner tried is not in a script this check can read")
    if not option.latin:
        return _unknown(rule, "the option is not in a script this check can read")
    outcome = norm(item.outcome)
    failed = bool(FAILED.search(outcome))
    if SUCCEEDED.search(outcome) and not failed:
        return _ok(rule, "what the owner tried worked, so repeating it is not blocked")
    mine = _tried_words(item.what)
    if not mine:
        return _unknown(rule, "a thing the owner tried has no words this check can compare")
    text = norm(option.text)
    # what follows "instead of", "rather than", "not" ... is named, not proposed
    parts = []
    for clause in re.split(r"[;:!?\n]|\.(?=\s|$)|\b(?:then|but)\b", text):
        ru = _RU_INSTEAD.search(clause)
        if ru:
            clause = clause[ru.end() :]  # "X ki jagah Y": X is named, Y is proposed
        m = _NEGATED_TAIL.search(clause)
        parts.append(clause[: m.start()] if m else clause)
    kept = " ".join(parts)
    theirs = _tried_words(kept)
    shared = sorted(min(w, key=len) for w in mine if any(w & t for t in theirs))
    need = max(1, -(-len(mine) * 6 // 10))
    repeated = len(shared) >= need and (len(mine) > 1 or len(shared) == 1)
    partial = len(shared) >= 2 and not repeated
    if not (repeated or partial):
        return _ok(rule, "the option does not repeat what the owner tried")
    if DIFFERENT.search(kept):
        return _ok(rule, "the option says it takes a different approach", tuple(shared))
    if not failed:
        return _unknown(
            rule,
            "the option repeats something the owner tried, and how it went is not clear",
            tuple(shared),
        )
    if repeated:
        return _violates(
            rule, f"the option repeats something that failed ({item.what})", tuple(shared)
        )
    return _unknown(rule, "the option overlaps with something that failed", tuple(shared))


# ------------------------------------------------------------------------------ staff check

RULE_STAFF = "staff"
ADD_PEOPLE = frozenset(
    "hire recruit employ onboard engage appoint add assign allocate deploy bring".split()
)
_STAFF_MARKS = "ऀ-ःऺ-ॏ॑-ॗॢॣ"  # Devanagari vowel signs
_STAFF_TOKEN = re.compile(rf"\d+|(?:[^\W\d_]|[{_STAFF_MARKS}]|')+|[;:!?\n]|\.(?=\s|$)")
_STAFF_CAP = re.compile(
    r"\b(?:only|at most|atmost|up to|upto|max|maximum|no more than|not more than|limit|cap|"
    r"total|just|sirf|kewal)\b"
)
_STAFF_CAP_OTHER = ("केवल", "सिर्फ", "صرف", "فقط")
_STAFF_PEOPLE_OTHER = ("لوگ", "عملہ", "ملازم", "लोग", "कर्मचारी", "स्टाफ", "موظف", "اشخاص", "أشخاص")
_STAFF_FLOOR = re.compile(
    r"\b(?:at least|atleast|minimum|min|no less than|not less than|kam se kam)\b"
)
_AMBIGUOUS_NUMBERS = frozenset({"do", "teen"})


def _numbers_in(tokens: list[str], latin: bool) -> list[int]:
    out: list[int] = []
    for w in tokens:
        if w.isdigit():
            out.append(min(int(w), 10**6))
        elif w in SMALL_NUMBER_WORDS and not (latin and w in _AMBIGUOUS_NUMBERS):
            out.append(SMALL_NUMBER_WORDS[w])
    return out


def parse_staff_limit(text: str) -> int | None:
    """How many people may be added: a ceiling, 0 for a freeze, None when it cannot be read (a
    floor like "at least 2 staff" is no ceiling and is None)."""
    t = lex.take_on_as_hire(norm(text))
    if lex.is_hiring_freeze(t):
        return 0
    if _STAFF_FLOOR.search(t) and not _STAFF_CAP.search(t):
        return None
    tokens = _STAFF_TOKEN.findall(t)
    nums = _numbers_in(tokens, mostly_latin(t))
    if not nums:
        return None
    cue = (
        bool(_STAFF_CAP.search(t))
        or any(c in t for c in _STAFF_CAP_OTHER)
        or any(c in t for c in _STAFF_PEOPLE_OTHER)
        or any(object_key(w) == "STAFF" for w in tokens if not w.isdigit())
    )
    return min(nums) if cue else None


def added_people(text: str) -> tuple[int, bool, tuple[str, ...]]:
    """(people the option adds, whether it names people to add with no count, their words)."""
    toks = _STAFF_TOKEN.findall(lex.take_on_as_hire(norm(text)))
    clause = []
    c = 0
    for w in toks:
        if not (w[0].isalnum() or w[0] == "'") or w in _BREAK_WORDS:
            c += 1
        clause.append(c)
    total = 0
    unknown = False
    evidence: list[str] = []
    for i, w in enumerate(toks):
        if not verb_stems(w) & ADD_PEOPLE or w.isdigit():
            continue
        if any(
            toks[j] in NEGATIONS or toks[j] in INVESTIGATE
            for j in range(max(0, i - 4), i)
            if clause[j] == clause[i]
        ):
            continue
        found = None
        for j in range(i + 1, min(len(toks), i + 8)):
            if clause[j] != clause[i] or (j > i + 1 and verb_stems(toks[j]) & ADD_PEOPLE):
                break
            if object_key(toks[j]) == "STAFF":
                found = j
                break
        backward = False
        if found is None:  # Urdu, Hindi: "دو اور کلرک رکھیں" puts the people before the verb
            for j in range(i - 1, max(-1, i - 6), -1):
                if clause[j] != clause[i]:
                    break
                if object_key(toks[j]) == "STAFF":
                    found, backward = j, True
                    break
        if found is None:
            continue
        count = None
        scan = range(found - 1, max(-1, found - 4), -1) if backward else range(i + 1, found)
        for k in scan:
            if clause[k] != clause[i]:
                break
            v = toks[k]
            if v.isdigit():
                count = min(int(v), 10**6)
                break
            if v in SMALL_NUMBER_WORDS and v != "do":
                count = SMALL_NUMBER_WORDS[v]
                break
            if v in {"a", "an", "another"}:
                count = 1
                break
        if count is None and found + 1 < len(toks) and clause[found + 1] == clause[i]:
            after = toks[found + 1]  # Arabic: "موظفين اثنين" puts the number after the noun
            if after.isdigit():
                count = min(int(after), 10**6)
            elif after in SMALL_NUMBER_WORDS and after != "do":
                count = SMALL_NUMBER_WORDS[after]
        if count is None and toks[found] in {"someone", "somebody", "anyone"}:
            count = 1
        if count is None:
            unknown = True
            continue
        total += count
        evidence.append(toks[found])
    return total, unknown, tuple(evidence)


def _check_staff(option: _Option, limit: Limit) -> Verdict:
    rule = RULE_STAFF
    cap = parse_staff_limit(limit.text)
    if cap is None:
        return _unknown(rule, "the staff limit could not be read as a number of people")
    if not option.latin:
        return _unknown(rule, "the option is not in a script this check can read")
    total, unclear, evidence = added_people(option.text)
    if total > cap:
        return _violates(
            rule,
            f"the option adds {total} people, above what the owner allows ({limit.text})",
            evidence,
        )
    if unclear:
        return _unknown(rule, "the option adds people and names no count")
    if (
        not evidence
        and _ru_option(option.tokens)
        and any(object_key(t.word) == "STAFF" for t in option.tokens)
    ):
        return _unknown(rule, "the option mentions people and its count cannot be read")
    return _ok(rule, "the option adds no more people than the owner allows")


COSTLY_WORDS = frozenset(
    """app apps software system platform tool tools subscription gateway terminal machine equipment
    device devices tablet scanner printer hardware installation mehnga mehenga mehngi expensive
    costly premium""".split()
)


def _check_no_budget(option: _Option) -> Verdict | None:
    """No budget was stated: an option that looks like it costs money cannot be called clear."""
    rule = RULE_BUDGET
    costly = [
        a.raw
        for a in parse_amounts(option.text, latin=option.latin)
        if a.role in {"cost", "ambiguous", "unclear"}
    ]
    if not costly:
        costly = [
            t.word
            for i, t in enumerate(option.tokens)
            if _proposed(option.tokens, i)
            and (
                (verb_stems(t.word) & SPEND_VERBS and _is_spend_verb(option.tokens, i))
                or noun_stem(t.word) in COSTLY_WORDS
                or t.word in COSTLY_WORDS
            )
        ]
    if not costly:
        return None
    return _unknown(
        rule,
        "no budget was stated and the option looks like it costs money, so its cost could "
        "not be checked",
        tuple(costly[:3]),
    )


# ------------------------------------------------------------------------------ budget check

SPEND_VERBS = frozenset(
    "buy purchase invest subscribe lease rent hire recruit upgrade outsource order acquire "
    "pay kharid khareed kharidein kharidain kharidna khareedna khareedein lena lagwa lagwana "
    "lagwayen".split()
)


def _check_budget(option: _Option, limit: Limit) -> Verdict:
    rule = RULE_BUDGET
    ceiling = parse_ceiling(limit.text)
    if ceiling.value is None:
        why = (
            "the budget states only a minimum"
            if ceiling.floor_only
            else "no figure in the budget text"
        )
        return _unknown(rule, why)
    amounts = [
        a
        for a in parse_amounts(option.text, latin=option.latin)
        if a.role in {"cost", "ambiguous", "unclear"}
    ]
    over_unknown: Verdict | None = None
    for a in amounts:
        if (ceiling.currency and a.currency and ceiling.currency != a.currency) or (
            ceiling.currency in (None, "RS") and a.currency not in (None, "RS")
        ):
            over_unknown = over_unknown or _unknown(
                rule, "the option's figure is in another currency than the budget", (a.raw,)
            )
            continue
        if a.period != ceiling.period and (a.period or a.value > ceiling.value):
            over_unknown = over_unknown or _unknown(
                rule,
                "the option's figure covers another period (monthly, yearly) than the budget",
                (a.raw,),
            )
            continue
        if a.value > ceiling.value:
            if a.role == "cost":
                return _violates(
                    rule,
                    f"the option states a cost of {a.raw}, above the budget ({limit.text})",
                    (a.raw,),
                )
            over_unknown = over_unknown or _unknown(
                rule, "a figure above the budget could not be attributed (cost or income)", (a.raw,)
            )
    if over_unknown:
        return over_unknown
    if amounts:
        return _ok(
            rule,
            "every cost figure the option states is within the budget",
            tuple(a.raw for a in amounts),
        )
    if not option.latin:
        return _unknown(rule, "the option is not in a script this check can read")
    spend = [
        t.word
        for i, t in enumerate(option.tokens)
        if verb_stems(t.word) & SPEND_VERBS and _is_spend_verb(option.tokens, i)
    ]
    if spend:
        return _unknown(
            rule, "the option involves spending and states no cost figure", tuple(spend[:3])
        )
    return _ok(rule, "the option states no cost")


def _is_spend_verb(tokens: list[Tok], i: int) -> bool:
    w = tokens[i].word
    if w in NOUN_TOO and i > 0 and tokens[i - 1].word in DETERMINERS:
        return False
    return not any(
        tokens[j].clause == tokens[i].clause and tokens[j].word in NEGATIONS
        for j in range(max(0, i - 3), i)
    )


# ---------------------------------------------------------------------------- deadline check


def _check_deadline(option: _Option, limit: Limit) -> Verdict:
    rule = RULE_DEADLINE
    due = parse_days(limit.text, need_cue=False)
    if due is None:
        return _unknown(
            rule, "the deadline is not a duration this check can read (a date needs a calendar)"
        )
    taken = parse_days(option.text, need_cue=True)
    if taken is None:
        return _unknown(rule, "the option states no timeframe, so the deadline cannot be compared")
    if taken > due:
        return _unknown(
            rule,
            f"the option's timeframe is longer than the deadline ({limit.text}); "
            "it plainly cannot meet it",
            (),
        )
    return _ok(rule, "the option's timeframe fits the deadline")


# ----------------------------------------------------------------------------- the entry point


OPTION_CHARS = 3000  # a longer option is not scanned at all
LIMIT_CHARS = 2000  # a stated limit is a sentence; more than this is not read


def _unreadable(reason: str) -> Verdict:
    return _unknown(RULE_UNREADABLE, reason)


def check_option(
    option_text: str,
    requirements: Requirements | None,
    language: str | None = None,
) -> Verdict:
    """Check one option against everything the owner stated. See the module docstring.

    Never raises: input of the wrong type, or anything this module did not foresee, is `unknown`
    with a reason, never `ok`."""
    if not isinstance(option_text, str):
        return _unreadable("the option is not text")
    if len(option_text) > OPTION_CHARS:
        return _unreadable("the option is too long to be read reliably")
    try:
        return _check_option(option_text, requirements)
    except Exception:  # noqa: BLE001 - the contract is "never raise, never ok"
        return _unreadable("the option or the requirements could not be read")


def _check_option(
    option_text: str, requirements: Requirements | None, probe_budget: bool = True
) -> Verdict:
    reqs = as_requirements(requirements)
    if not isinstance(reqs, Requirements):
        return _unreadable("the requirements are not in a form this check reads")
    text = option_text.strip()
    if not text:
        return _unknown(RULE_UNREADABLE, "the option text is empty")
    if not reqs.columns_available:
        return _unknown(
            RULE_UNREADABLE, "the owner's requirements could not be read from the database"
        )
    option = _option(text)
    results: list[Verdict] = []
    for limit in reqs.cannot_change:
        results.append(_check_cannot(option, _clip(limit)))
    for item in reqs.tried:
        results.append(_check_tried(option, item))
    for limit in reqs.staff:
        results.append(_check_staff(option, _clip(limit)))
    for limit in reqs.budgets:
        results.append(_check_budget(option, _clip(limit)))
    for limit in reqs.deadlines:
        results.append(_check_deadline(option, _clip(limit)))
    if probe_budget and not reqs.budgets:
        no_budget = _check_no_budget(option)
        if no_budget:
            results.append(no_budget)
    if not results:
        return _ok(RULE_NONE, "the owner stated no limit to check")
    for verdict in results:
        if verdict.status == "violates":
            return verdict
    unreadable = _spaced_unreadable(text)
    if unreadable:
        return unreadable
    for verdict in results:
        if verdict.status == "unknown":
            return verdict
    if option.unread:
        return _unknown(
            results[0].rule,
            f"{option.unread} word(s) of the option are in a script this check does not read fully",
        )
    return _ok(results[0].rule, f"{len(results)} stated limit(s) read and none broken")


def _clip(limit: Limit) -> Limit:
    text = limit.text if isinstance(limit.text, str) else ""
    return limit if len(text) <= LIMIT_CHARS else Limit(text[:LIMIT_CHARS], limit.msg)


def _spaced_unreadable(text: str) -> Verdict | None:
    """Text written letter by letter is collapsed before it is read. When a collapsed run is not
    a word this module knows, what it hides is unknown, so the option cannot be `ok`."""
    for run in spaced_runs(text):
        if run in UNITS or verb_families(run) or re.fullmatch(_CUR_WORDS, run):
            continue
        return _unknown(
            RULE_UNREADABLE,
            "part of the option is spaced out letter by letter and cannot be read reliably",
            (run[:20],),
        )
    return None
