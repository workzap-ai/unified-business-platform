"""L2-1: the word lists and small readers behind the limit types beyond "verb + object".

Pure: no database, no model, no network, no import from `evalkit` or `constraint_check`. Every
function takes text that `constraint_check.norm` has already normalised (lower case, ASCII digits,
no invisible marks), except `option_places`, which also wants the raw option to see capital letters.

A limit type exists here only when its words are POSITIVELY recognised: a place from PLACES, a
topic word from TOPIC_WORDS, a size unit from SIZE_UNITS, a hiring freeze from FREEZE. Anything
else is left to the caller, which then answers `unknown`, never `ok`.
"""

import re
from dataclasses import dataclass

PLACES = frozenset(
    """karachi lahore islamabad rawalpindi faisalabad multan peshawar quetta sialkot gujranwala
    hyderabad sukkur bahawalpur sargodha abbottabad mardan okara jhelum gujrat dubai dhabi sharjah
    ajman riyadh jeddah dammam doha muscat kuwait manama delhi mumbai bangalore chennai kolkata
    dhaka london manchester birmingham toronto paris istanbul cairo pakistan punjab sindh
    balochistan khyber india uae saudi turkey china""".split()
)
NATIONWIDE = frozenset(
    "nationwide countrywide national everywhere abroad overseas international worldwide "
    "globally global".split()
)
NATION_PHRASES = re.compile(
    r"\b(?:all over|across the country|other cities|another city|other countries|every city|"
    r"all cities|whole country|other towns|more cities)\b"
)
EXPANSION_VERBS = frozenset(
    "open expand ship deliver sell launch start operate serve cover extend grow".split()
)
_PLACE_CUE = re.compile(
    r"\b(?:only|just|beyond|outside|within|limited to|restricted to|other than|except|"
    r"not possible|expand|expansion)\b"
)
_NOT_PLACES = frozenset(
    "monday tuesday wednesday thursday friday saturday sunday january february march april may "
    "june july august september october november december ramadan eid facebook instagram whatsapp "
    "google tiktok youtube amazon daraz shopify".split()
)
_CAP_AFTER_PREP = re.compile(r"\b(?:in|to|at|from|near|around|across)\s+([A-Z][a-z]{2,})")


def place_limit(text: str) -> tuple[str, ...]:
    """The places a location limit allows, or () when `text` is not a location limit."""
    words = re.findall(r"[^\W\d_]+", text)
    places = tuple(dict.fromkeys(w for w in words if w in PLACES))
    return places if places and _PLACE_CUE.search(text) else ()


def option_places(raw: str, normalised: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(places the option names that the lexicon knows, capitalised names it does not know)."""
    known = tuple(dict.fromkeys(w for w in re.findall(r"[^\W\d_]+", normalised) if w in PLACES))
    unknown = tuple(
        dict.fromkeys(
            m.group(1).lower()
            for m in _CAP_AFTER_PREP.finditer(raw)
            if m.group(1).lower() not in PLACES and m.group(1).lower() not in _NOT_PLACES
        )
    )
    return known, unknown


def reaches_beyond(normalised: str) -> bool:
    words = set(re.findall(r"[^\W\d_]+", normalised))
    return bool(words & NATIONWIDE) or bool(NATION_PHRASES.search(normalised))


# ------------------------------------------------------------------------------- topics

TOPIC_WORDS: dict[str, frozenset[str]] = {
    "delivery": frozenset(
        "deliver delivers delivered delivering delivery deliveries dispatch ship ships shipping "
        "shipped shipment courier doorstep".split()
    ),
    "travel": frozenset(
        "travel travels traveling travelling travelled trip trips visit visits visiting tour "
        "fly flight journey commute abroad".split()
    ),
    "weekend": frozenset(
        "weekend weekends saturday sunday saturdays sundays holiday holidays".split()
    ),
    "late hours": frozenset("late midnight overnight night nights 247 roundtheclock".split()),
    "internet": frozenset(
        "internet wifi online cloud web website app apps software digital email ecommerce".split()
    ),
    "computer": frozenset(
        "computer computers laptop laptops pc pcs tablet tablets software".split()
    ),
    "vehicle": frozenset(
        "car cars van vans truck trucks bike bikes motorcycle vehicle vehicles rickshaw "
        "pickup".split()
    ),
}
_RESOURCE_CUE = re.compile(
    r"\b(?:no|without|lack|lacks|lacking|don't have|do not have|dont have|have no|has no|"
    r"don't own|do not own|not available|unavailable)\b"
)
_TOPIC_MODAL = re.compile(
    r"\b(?:cannot|can't|cant|can not|won't|unable to|not able to|never|not allowed to|"
    r"don't|do not|dont|no way to|not possible)\b"
)
# a limit about changing, buying, hiring, cutting... is about THAT verb, not about a topic
_OTHER_VERB = frozenset(
    "change replace switch swap alter modify upgrade scrap stop close cut reduce raise increase "
    "hire recruit employ add expand extend buy purchase fire dismiss afford".split()
)


def topic_limit(text: str) -> str:
    """The topic a resource or capability limit is about ("no internet at the shop", "cannot work
    weekends", "cannot deliver"), or "" when it is not one."""
    words = re.findall(r"[^\W\d_]+|\d+[a-z/]*", text)
    if set(words) & _OTHER_VERB:
        return ""
    if not (_RESOURCE_CUE.search(text) or _TOPIC_MODAL.search(text)):
        return ""
    for name, members in TOPIC_WORDS.items():
        if any(w in members or w.rstrip("s") in members for w in words):
            return name
    return ""


def topic_hits(topic: str, words: list[str]) -> list[str]:
    members = TOPIC_WORDS.get(topic, frozenset())
    return [w for w in words if w in members or w.rstrip("s") in members]


# ---------------------------------------------------------------------------------- size

SIZE_UNITS = {
    "sqft": "sqft", "sq ft": "sqft", "square feet": "sqft", "square foot": "sqft",
    "sq feet": "sqft", "sqm": "sqm", "sq m": "sqm", "square meters": "sqm",
    "square metres": "sqm", "marla": "marla", "marlas": "marla", "kanal": "kanal",
    "kg": "kg", "kgs": "kg", "kilos": "kg", "litres": "litre", "liters": "litre",
    "litre": "litre", "liter": "litre", "tons": "ton", "tonnes": "ton", "ton": "ton",
    "feet": "feet", "ft": "feet", "metres": "metre", "meters": "metre", "metre": "metre",
    "meter": "metre",
}  # fmt: skip
_SIZE = re.compile(
    r"(?<![\d.,])(\d+(?:\.\d+)?)\s*("
    + "|".join(sorted(map(re.escape, SIZE_UNITS), key=len, reverse=True))
    + r")\b"
)
_SIZE_CUE = re.compile(
    r"\b(?:only|just|max|maximum|at most|up to|limited|small|tiny|cannot exceed|can't exceed|"
    r"no more than|not more than|no larger|no bigger|fits|capacity)\b"
)
SPACE_WORDS = frozenset(
    "area space room counter shelf shelves table tables machine machines display showroom "
    "storage stock rack racks seating tables extension extend expand larger bigger".split()
)


@dataclass(frozen=True, slots=True)
class Size:
    value: float
    unit: str


def sizes_in(text: str) -> list[Size]:
    out = []
    for m in _SIZE.finditer(text):
        try:
            out.append(Size(float(m.group(1)), SIZE_UNITS[m.group(2)]))
        except (ValueError, KeyError):
            continue
    return out


def size_limit(text: str) -> Size | None:
    found = sizes_in(text)
    return found[0] if found and _SIZE_CUE.search(text) else None


# ---------------------------------------------------------------------------- hiring freeze

_NEG = (
    r"(?:do not|don't|dont|doesn't|does not|should not|shouldn't|cannot|can not|can't|cant|"
    r"won't|will not|never|avoid(?:ing)?|not to|unable to|not allowed to|not able to|"
    r"no budget to|no money to|no plan to|stop|stopped|refuse to|no way to|must not|mustn't|"
    r"not willing to|not going to)"
)
_HIRE_V = r"(?:hire|hiring|recruit\w*|employ|employing|onboard\w*|engage|appoint\w*|take on)"
FREEZE = (
    re.compile(rf"\b{_NEG}\s+(?:\w+\s+){{0,3}}?{_HIRE_V}\b"),
    re.compile(
        r"\b(?:hiring|recruit\w*|headcount|employment)\b.{0,25}\b(?:frozen|freeze|fixed|capped|"
        r"not allowed|banned|stopped|on hold|paused|prohibited|closed)\b"
    ),
    re.compile(r"\b(?:hiring|recruitment|headcount)\s+freeze\b|\bfreeze on (?:hiring|recruit\w*)"),
    re.compile(
        r"\bno (?:more|new|extra|additional) (?:staff|people|employees|workers|hires|headcount)\b"
        r"|\b(?:cannot|can't|cant|can not) afford (?:more |new |extra )?"
        r"(?:staff|people|employees|workers)\b"
    ),
)
_TAKE_ON = re.compile(r"\b(?:take|takes|taking|took|taken) on\b")


def is_hiring_freeze(text: str) -> bool:
    t = _TAKE_ON.sub("hire", text)
    return any(p.search(t) for p in FREEZE)


def take_on_as_hire(text: str) -> str:
    return _TAKE_ON.sub("hire", text)
