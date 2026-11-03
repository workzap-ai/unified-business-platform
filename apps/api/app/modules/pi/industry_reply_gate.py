"""G11 noAssumedIndustry on the REPLY side (L1-8): no trade noun the owner did not say.

Spec v1.6 Part 19, rule G11: "If the owner's industry has not been stated or confirmed, pi uses no
industry-specific nouns in questions or ideas, and never speaks a guessed industry as a fact. If it
needs to know, it asks openly ('Ye maal kis cheez ka hai?'), never as a leading choice ('AC units ya
spare parts?')." Today only the input side is enforced: `service_conversation` blanks the
industry knowledge when the trade is unconfirmed (`industry_unconfirmed`), but nothing checks what
the model then writes. This module is that check. It is a PURE function and is NOT wired in yet.

`unconfirmed_industry_noun(reply, owner_words, trade_confirmed, language)` returns a `Finding`
(naming the first noun) or None.

Rules
- `trade_confirmed` true: never a Finding (a stated or confirmed trade is the owner's own).
- Only whole words and phrases count, matched after stemming (`script_words.stem`: English plural,
  Arabic article, Hindi plural ending) in English, Roman Urdu, Urdu script, Hindi and Arabic.
- The lexicon is conservative: hand-written trade nouns per pack key (`TRADE_NOUNS`) plus the Arabic
  and Urdu trade words of `industry_words.TRADE_WORDS` (read only, 4 letters or more so "لان",
  "because", never counts). Generic words (shop, business, customers, stock, maal, dukaan,
  karobar, दुकान, محل...) are in no list, and `GENERIC_WORDS` documents the ones tests pin.
- The owner's own words are never blocked: a noun the owner wrote is fine, and so is any noun of a
  trade the owner named (after "AC repair" the reply may say "spare parts"). A noun that
  belongs to several trades (spare parts) is excused by any one of them.

Where it is called (for the FT-02 lane; this file does not touch the hot files)
  `service_conversation.py` sets `industry_unconfirmed` where it blanks the knowledge
  (~line 3759, `unconfirmed_trade`) and never reads it. The call site is `part18_problem` (~line
  5000), next to the other reply guards:

      finding = unconfirmed_industry_noun(
          reply, owner_texts, trade_confirmed=not context.get("industry_unconfirmed"),
          language=language)
      if finding: return finding.reason

  Rewrite contract: the reason goes into the one rewrite request ("regenerate with the reason");
  the model asks openly what the business sells instead of offering a choice. If the second reply
  fails again, send a safe fallback (an open question: what the business does or sells), never
  the reply with the noun. The check must run in brain mode only, like the other guards.

Honest limit: written by one author; the Hindi, Urdu and Arabic forms are not reviewed by a native
speaker. A missed noun lets a reply through; a wrongly listed word can only cause one rewrite.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from app.modules.pi.industry_words import TRADE_PHRASES, TRADE_WORDS
from app.modules.pi.script_words import WORD, tokens

MIN_DERIVED_LETTERS = 4
MAX_PHRASE = 3

# pack key -> trade nouns (English, Roman Urdu, Urdu script, Hindi, Arabic). Plural and article
# forms are cut by `stem`, so the singular is enough in English and Arabic.
TRADE_NOUNS: dict[str, tuple[str, ...]] = {
    "hvac_ac_sales_installation_and_service": (
        "ac",
        "ac unit",
        "air conditioner",
        "air conditioning",
        "split ac",
        "compressor",
        "refrigerant",
        "اے سی",
        "ایئر کنڈیشنر",
        "کمپریسر",
        "एसी",
        "एयर कंडीशनर",
        "कंप्रेसर",
        "مكيف",
        "تكييف",
        "كمبروسر",
        "spare part",
        "spares",
        "kalpurze",
        "اسپیئر پارٹس",
        "پرزے",
        "स्पेयर पार्ट्स",
        "पुर्जे",
        "قطع غيار",
    ),
    "restaurants": (
        "restaurant",
        "menu",
        "chef",
        "waiter",
        "dine in",
        "ریسٹورنٹ",
        "ویٹر",
        "रेस्टोरेंट",
        "रेस्तरां",
        "वेटर",
        "मेनू",
        "مطعم",
        "نادل",
    ),
    "dhabas_food_trucks_chai_stalls_and_street_food": (
        "dhaba",
        "chai stall",
        "food truck",
        "ڈھابہ",
        "ढाबा",
        "ढाबे",
    ),
    "bakeries_mithai_and_confectionery": (
        "bakery",
        "cake",
        "mithai",
        "sweets shop",
        "بیکری",
        "مٹھائی",
        "बेकरी",
        "मिठाई",
        "مخبز",
        "حلويات",
    ),
    "pharmacies_and_medical_stores": (
        "pharmacy",
        "medicine",
        "chemist",
        "dawai",
        "دوائی",
        "فارمیسی",
        "फार्मेसी",
        "दवाई",
        "दवा",
        "صيدلية",
        "دواء",
    ),
    "clinics_and_gp_practices": (
        "clinic",
        "doctor",
        "patient",
        "کلینک",
        "ڈاکٹر",
        "مریض",
        "क्लिनिक",
        "डॉक्टर",
        "मरीज",
        "عيادة",
        "طبيب",
        "مريض",
    ),
    "dental_clinics": (
        "dentist",
        "dental",
        "teeth",
        "ڈینٹل",
        "دانت",
        "डेंटल",
        "दांत",
        "اسنان",
    ),
    "hospitals": ("hospital", "ہسپتال", "अस्पताल", "مستشفى"),
    "hotels": ("hotel", "guest room", "ہوٹل", "होटल", "فندق"),
    "salons_and_barbers": (
        "salon",
        "barber",
        "haircut",
        "سیلون",
        "حجام",
        "सैलून",
        "नाई",
        "صالون",
        "حلاق",
    ),
    "gyms_and_fitness_studios": ("gym", "جم", "जिम", "نادي رياضي"),
    "tailoring_and_alteration_shops": (
        "tailor",
        "stitching",
        "درزی",
        "सिलाई",
        "दर्जी",
        "خياط",
        "خياطة",
    ),
    "unstitched_fabric_lawn_and_textile_retail": (
        "fabric",
        "unstitched",
        "lawn suit",
        "کپڑا",
        "कपड़ा",
        "कपडा",
        "قماش",
        "اقمشة",
    ),
    "jewellery": (
        "jewellery",
        "jeweller",
        "gold ring",
        "زیور",
        "جیولری",
        "ज्वेलरी",
        "गहने",
        "مجوهرات",
        "صائغ",
    ),
    "mobile_phones_and_accessories": (
        "mobile phone",
        "smartphone",
        "phone case",
        "موبائل فون",
        "मोबाइल फोन",
        "هاتف",
        "جوال",
    ),
    "electronics_and_home_appliances_retail": (
        "refrigerator",
        "fridge",
        "washing machine",
        "microwave",
        "فریج",
        "फ्रिज",
        "ثلاجة",
        "غسالة",
    ),
    "hardware_paint_sanitary_and_building_materials_shops": (
        "hardware store",
        "sanitary",
        "plumbing",
        "bricks",
        "ہارڈویئر",
        "हार्डवेयर",
        "सैनिटरी",
        "ईंट",
        "مواد بناء",
    ),
    "cement_blocks_pavers_and_precast": ("cement", "concrete", "سیمنٹ", "सीमेंट", "اسمنت"),
    "tiles_marble_and_bathroom_kitchen_showrooms": (
        "tiles",
        "marble",
        "ٹائل",
        "ماربل",
        "टाइल",
        "संगमरमर",
        "بلاط",
        "رخام",
    ),
    "furniture_and_home_decor_retail": ("furniture", "sofa", "فرنیچر", "फर्नीचर", "सोफा", "أثاث"),
    "auto_workshops_and_service_centres": (
        "mechanic",
        "car service",
        "oil change",
        "مکینک",
        "मैकेनिक",
        "ميكانيكي",
        "spare part",
        "spares",
        "kalpurze",
        "اسپیئر پارٹس",
        "پرزے",
        "स्पेयर पार्ट्स",
        "पुर्जे",
        "قطع غيار",
    ),
    "tyre_battery_and_auto_parts_shops": (
        "tyre",
        "tire",
        "car battery",
        "ٹائر",
        "टायर",
        "اطار",
        "اطارات",
        "spare part",
        "spares",
        "kalpurze",
        "اسپیئر پارٹس",
        "پرزے",
        "स्पेयर पार्ट्स",
        "पुर्जे",
        "قطع غيار",
    ),
    "generator_sales_rental_and_service": (
        "generator",
        "genset",
        "جنریٹر",
        "जनरेटर",
        "مولد",
        "spare part",
        "spares",
        "اسپیئر پارٹس",
        "قطع غيار",
    ),
    "solar_epc_and_installers": (
        "solar",
        "inverter",
        "solar panel",
        "سولر",
        "इन्वर्टर",
        "सोलर",
        "طاقة شمسية",
        "سولار",
    ),
    "kiryana_corner_shops_and_convenience_stores": (
        "grocery",
        "kiryana",
        "kariyana",
        "کریانہ",
        "किराना",
        "بقالة",
    ),
    "poultry_farms": ("poultry", "broiler", "chicks", "مرغی", "پولٹری", "मुर्गी", "पोल्ट्री", "دواجن"),
    "cattle_and_buffalo_dairy_farms": (
        "dairy",
        "buffalo",
        "milk",
        "डेयरी",
        "ڈیری",
        "دودھ",
        "بھینس",
        "दूध",
        "भैंस",
        "حليب",
        "جاموس",
    ),
    "crop_farming": (
        "crop",
        "harvest",
        "wheat",
        "fasal",
        "فصل",
        "گندم",
        "फसल",
        "गेहूं",
        "محصول",
        "قمح",
    ),
    "seed_fertiliser_and_pesticide_dealers": (
        "fertiliser",
        "fertilizer",
        "pesticide",
        "seeds",
        "کھاد",
        "खाद",
        "बीज",
        "سماد",
        "بذور",
    ),
    "printing_presses_and_print_on_demand": (
        "printing press",
        "print shop",
        "پرنٹنگ",
        "प्रिंटिंग",
        "مطبعة",
        "طباعة",
    ),
    "trucking_and_goods_transport_companies": (
        "truck",
        "trucking",
        "ٹرک",
        "ट्रक",
        "شاحنة",
        "شاحنات",
    ),
    "courier_and_last_mile_delivery_companies": (
        "courier",
        "parcel rider",
        "کوریئر",
        "कूरियर",
        "ساعي توصيل",
    ),
    "real_estate_agencies_and_brokers": (
        "real estate",
        "property dealer",
        "پراپرٹی",
        "प्रॉपर्टी",
        "عقار",
        "عقارات",
    ),
    "laundry_and_dry_cleaning": ("laundry", "dry cleaning", "لانڈری", "लॉन्ड्री", "مغسلة"),
    "law_firms": ("lawyer", "law firm", "وکیل", "वकील", "محامي", "محامي"),
    "accounting_audit_and_tax_practices": (
        "accountant",
        "ٹیکس ریٹرن",
        "اکاؤنٹنٹ",
        "अकाउंटेंट",
        "محاسب",
    ),
    "travel_agencies_and_ticketing": (
        "travel agency",
        "air ticket",
        "ٹریول ایجنسی",
        "ट्रैवल एजेंसी",
        "وكالة سفر",
    ),
    "hajj_and_umrah_operators": ("umrah", "hajj", "عمرہ", "उमराह", "عمرة"),
    "private_schools_and_school_chains": (
        "school",
        "classroom",
        "اسکول",
        "سکول",
        "स्कूल",
        "مدرسة",
    ),
    "tuition_centres_and_academies": ("tuition", "academy", "ٹیوشن", "اکیڈمی", "ट्यूशन", "अकादमी"),
    "wedding_planners_and_event_management": (
        "wedding",
        "banquet",
        "شادی",
        "शादी",
        "बैंक्विट",
        "زفاف",
        "قاعة",
    ),
    "photography_and_videography_studios": (
        "photographer",
        "photography",
        "فوٹوگرافی",
        "फोटोग्राफी",
        "تصوير",
    ),
    "perfumes_attar_and_oud": ("perfume", "attar", "oud", "عطر", "इत्र", "परफ्यूम"),
    "pet_shops_and_pet_supplies": ("pet shop", "pet food", "پیٹ شاپ", "पेट शॉप", "حيوانات اليفة"),
    "veterinary_clinics_and_animal_health_suppliers": (
        "vet",
        "veterinary",
        "ویٹرنری",
        "पशु चिकित्सक",
        "بيطري",
    ),
    "meat_shops_and_butchers": ("butcher", "meat", "قصائی", "گوشت", "कसाई", "मांस", "جزار", "لحم"),
    "car_wash_and_detailing": ("car wash", "detailing", "کار واش", "कार वॉश", "غسيل سيارات"),
    "steel_re_rolling_mills_and_metal_fabrication": (
        "steel",
        "welding",
        "scrap iron",
        "لوہا",
        "لوہے",
        "लोहा",
        "स्टील",
        "حديد",
        "لحام",
    ),
    "textile_spinning_and_weaving_mills": (
        "yarn",
        "loom",
        "weaving",
        "دھاگہ",
        "धागा",
        "غزل",
        "نسيج",
    ),
    "general_factories_and_workshops": (
        "factory",
        "mill",
        "workshop",
        "karkhana",
        "karkhane",
        "کارخانہ",
        "کارخانے",
        "फैक्ट्री",
        "कारखाना",
        "कारखाने",
        "مصنع",
        "مصانع",
        "ورشة",
    ),
    "garment_and_knitwear_export_units": (
        "garment",
        "knitwear",
        "hosiery",
        "گارمنٹس",
        "गारमेंट्स",
        "ملابس جاهزة",
    ),
    "pest_control": ("pest control", "termite", "fumigation", "دیمک", "दीमक", "مكافحة الحشرات"),
}

# Words that name no trade. Never in any list; `GENERIC_WORDS` is what the tests pin.
GENERIC_WORDS = (
    "shop",
    "business",
    "customers",
    "customer",
    "stock",
    "orders",
    "staff",
    "items",
    "products",
    "goods",
    "supplier",
    "maal",
    "dukaan",
    "karobar",
    "کاروبار",
    "دکان",
    "گاہک",
    "माल",
    "दुकान",
    "व्यापार",
    "ग्राहक",
    "متجر",
    "محل",
    "تجارة",
    "عميل",
    "زبون",
    "مخزون",
)


@dataclass(frozen=True)
class Finding:
    noun: str  # the owner-visible word or phrase as it stands in the reply
    labels: tuple[str, ...]  # the pack keys it belongs to
    language: str
    reason: str  # the sentence for the rewrite request


# Words that are plain talk when they stand alone ("Do you have an accountant?", "Is the fabric
# woven or knitted?") and name a trade only next to a trade word. surface -> context words.
_ACCOUNTING_CONTEXT = (
    "firm practice audit tax taxes return returns bookkeeping ٹیکس آڈٹ ضريبة ضرائب تدقيق ऑडिट"
).split()
_FABRIC_CONTEXT = (
    "stitch stitching stitched unstitched lawn tailor tailors yards suit suits boutique "
    "سلائی لان درزی सिलाई خياطة"
).split()
CONTEXTUAL: dict[str, tuple[str, ...]] = {
    **{w: tuple(_ACCOUNTING_CONTEXT) for w in ("accountant", "اکاؤنٹنٹ", "अकाउंटेंट", "محاسب")},
    **{w: tuple(_FABRIC_CONTEXT) for w in ("fabric", "کپڑا", "कपड़ा", "قماش", "اقمشة")},
}
_ARABIC_SUFFIXES = ("كم", "نا", "ها", "هم", "ك", "ي", "ه")  # your, our, her, their, my, his


@lru_cache(maxsize=1)
def _lexicon() -> dict[tuple[str, ...], frozenset[str]]:
    """stem tuple -> the pack keys the noun belongs to."""
    found: dict[tuple[str, ...], set[str]] = {}

    def add(key: str, surface: str) -> None:
        stems = tuple(tokens(surface))
        if stems and len(stems) <= MAX_PHRASE:
            found.setdefault(stems, set()).add(key)

    for key, words in TRADE_NOUNS.items():
        for word in words:
            add(key, word)
    for table in (TRADE_WORDS, TRADE_PHRASES):
        for key, words in table.items():
            for word in words:
                # a short derived word ("لان", "حج") can be a common word of another language
                if len(word.replace(" ", "")) >= MIN_DERIVED_LETTERS and any(
                    ord(c) > 0x590 for c in word
                ):
                    add(key, word)
    return {stems: frozenset(keys) for stems, keys in found.items()}


@lru_cache(maxsize=1)
def _context() -> dict[tuple[str, ...], frozenset[str]]:
    """stem tuple of a contextual noun -> the stems of the words that make it a trade noun."""
    return {
        tuple(tokens(word)): frozenset(t for c in words for t in tokens(c))
        for word, words in CONTEXTUAL.items()
    }


@lru_cache(maxsize=1)
def _lexicon_tokens() -> frozenset[str]:
    return frozenset(t for stems in _lexicon() for t in stems)


def _canon(token: str) -> str:
    """An Arabic noun with a possessive suffix ("مخبزك", "your bakery") as the bare noun."""
    known = _lexicon_tokens()
    if token in known or not any("\u0600" <= c <= "\u06ff" for c in token):
        return token
    for suffix in _ARABIC_SUFFIXES:
        if not token.endswith(suffix):
            continue
        bare = token[: -len(suffix)]
        taa = bare[:-1] + "ه" if bare.endswith("ت") else bare
        for candidate in (bare, taa, "و" + bare, "و" + taa):  # a leading و was cut by the stem
            if candidate in known:  # a taa marbuta turns into ت before a suffix
                return candidate
    return token


def _spans(text: str) -> list[tuple[tuple[str, ...], str]]:
    """Every word and short phrase of a text as (stems, words as written), in text order."""
    raw = [m.group(0) for m in WORD.finditer(text)]
    stems = [_canon(t) for t in tokens(text)]
    return [
        (tuple(stems[i : i + size]), " ".join(raw[i : i + size]))
        for i in range(len(stems))
        for size in range(1, MAX_PHRASE + 1)
        if i + size <= len(stems)
    ]


def nouns_in(text: str, need_context: bool = True) -> list[tuple[str, frozenset[str]]]:
    """The trade nouns a text uses: (words as written, pack keys), first occurrence order. A
    contextual noun ("accountant", "fabric") counts only next to a trade word unless
    `need_context` is false (the owner's own words)."""
    if not isinstance(text, str):
        return []
    lexicon = _lexicon()
    contextual = _context()
    present = {_canon(t) for t in tokens(text)}
    seen: set[tuple[str, ...]] = set()
    found: list[tuple[str, frozenset[str]]] = []
    for stems, written in _spans(text):
        if stems not in lexicon or stems in seen:
            continue
        if need_context and stems in contextual and not (contextual[stems] & present):
            continue
        seen.add(stems)
        found.append((written, lexicon[stems]))
    return found


def unconfirmed_industry_noun(
    reply: str,
    owner_words: str | Sequence[str],
    trade_confirmed: bool,
    language: str = "",
) -> Finding | None:
    """A Finding when the trade is not confirmed and the reply uses a trade noun the owner did not
    say; None otherwise. See the module docstring for the rules and the call site. Never raises:
    input that is not text (None, numbers, bytes, dicts) gives None."""
    if trade_confirmed or not isinstance(reply, str):
        return None
    if isinstance(owner_words, str):
        said = owner_words
    elif isinstance(owner_words, (list, tuple)):
        said = " ".join(w for w in owner_words if isinstance(w, str))
    else:
        said = ""
    language = language if isinstance(language, str) else ""
    spoken = nouns_in(said, need_context=False)
    spoken_stems = {tuple(_canon(t) for t in tokens(written)) for written, _ in spoken}
    spoken_trades = set().union(*(keys for _, keys in spoken)) if spoken else set()
    for written, keys in nouns_in(reply):
        if tuple(_canon(t) for t in tokens(written)) in spoken_stems or keys & spoken_trades:
            continue
        return Finding(
            noun=written,
            labels=tuple(sorted(keys)),
            language=language,
            reason=(
                f"it uses the industry word '{written}', but the owner has not said what the "
                "business is. Do not guess a trade: ask openly what the business sells or does "
                "(never a leading choice between trades), and use only the owner's own words"
                + (f". Reply in {language}" if language else "")
            ),
        )
    return None
