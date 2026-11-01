"""L1-8: G11 noAssumedIndustry on the reply side (industry_reply_gate.unconfirmed_industry_noun).

HONEST LIMIT. One author wrote every sentence and every Hindi, Urdu and Arabic trade word; no
native speaker has reviewed them and none of this is real traffic. The tables are small, so n is
printed and asserted. Measured here: recall on replies that DO assume a trade, and false positives
on 30 ordinary replies with no trade noun. The detector is not wired into service_conversation yet
(a hot file); see the module docstring for the call site.
"""

import pytest

from app.modules.pi import industry_packs as ip
from app.modules.pi import industry_reply_gate as irg
from app.modules.pi.industry_reply_gate import unconfirmed_industry_noun as check

# (language, reply, what the owner said, a word the Finding must name)
POSITIVES: list[tuple[str, str, str, str]] = [
    ("en", "AC units ya spare parts?", "", "AC"),  # the spec's own failing example
    ("en", "Do you sell restaurant equipment or kitchen tools?", "", "restaurant"),
    ("en", "How many patients do you see in a day?", "", "patients"),
    (
        "en",
        "Is the problem with your tailors or the fabric supply?",
        "I have a problem with my work",
        "tailors",
    ),
    ("en", "Are the delays on the trucks or at the warehouse?", "things are late", "trucks"),
    ("en", "Is it the generator that keeps failing?", "something keeps failing", "generator"),
    ("en", "Do you farm wheat or keep dairy cattle?", "", "wheat"),
    ("ru", "Aap AC bechte hain ya spare parts?", "", "AC"),
    ("ru", "Aap ke dhaba mein kitne log kaam karte hain?", "log kaam karte hain", "dhaba"),
    ("ru", "Kya aap ki bakery mein cake kam bikte hain?", "bikri kam hai", "bakery"),
    ("ru", "Mobile phone ki repair hoti hai ya sirf sale?", "", "Mobile phone"),
    ("ru", "Tyre ka maal kahan se aata hai?", "maal late aata hai", "Tyre"),
    ("ur", "کیا آپ ایئر کنڈیشنر بیچتے ہیں یا اسپیئر پارٹس؟", "", "ایئر کنڈیشنر"),
    ("ur", "آپ کے ریسٹورنٹ میں کتنے ویٹر ہیں؟", "عملہ کم ہے", "ریسٹورنٹ"),
    ("ur", "کیا مریض زیادہ آتے ہیں یا کم؟", "", "مریض"),
    ("ur", "آپ کا کلینک کتنے بجے کھلتا ہے؟", "کام کم ہے", "کلینک"),
    ("hi", "आप एसी बेचते हैं या स्पेयर पार्ट्स?", "", "एसी"),
    ("hi", "आपके रेस्टोरेंट में कितने वेटर हैं?", "स्टाफ कम है", "रेस्टोरेंट"),
    ("hi", "क्या मरीज देर तक इंतज़ार करते हैं?", "", "मरीज"),
    ("hi", "क्या दुकान में किराना का माल कम है?", "माल कम है", "किराना"),
    ("hi", "गेहूं की फसल का नुकसान हुआ क्या?", "नुकसान हुआ", "गेहूं"),
    ("ar", "هل تبيع المكيفات أم قطع غيار؟", "", "المكيفات"),
    ("ar", "كم عدد الأطباء في العيادة؟", "", "العيادة"),
    ("ar", "هل المشكلة في المطعم أم في التوصيل؟", "المشكلة في التوصيل", "المطعم"),
    ("ar", "هل تبيع الأثاث أم الأجهزة؟", "", "الأثاث"),
]

# Same replies, but the trade is stated or confirmed, or the owner said the word: never a Finding.
EXCUSED: list[tuple[str, str, str, bool]] = [
    ("AC units ya spare parts?", "we do AC repair", False),  # the owner named the trade
    ("AC units ya spare parts?", "", True),  # confirmed
    ("Aap AC bechte hain ya spare parts?", "main AC ka kaam karta hoon", False),
    ("आप एसी बेचते हैं या स्पेयर पार्ट्स?", "मैं एसी की मरम्मत करता हूँ", False),
    ("هل تبيع المكيفات أم قطع غيار؟", "عندي محل مكيفات", False),
    ("آپ کے ریسٹورنٹ میں کتنے ویٹر ہیں؟", "ہمارا ریسٹورنٹ ہے", False),
    ("How many patients do you see in a day?", "I run a clinic", False),
    ("How many patients do you see in a day?", "", True),
    ("Is it the generator that keeps failing?", "the generator keeps failing", False),
    ("Kya aap ki bakery mein cake kam bikte hain?", "meri bakery hai", False),
]

# 30 ordinary replies: no industry noun. Generic words (shop, business, customers, stock) appear.
ORDINARY: list[tuple[str, str]] = [
    ("en", "What does the business sell or do?"),
    ("en", "Thanks for telling me. How long has it been like this?"),
    ("en", "How many people work in your shop?"),
    ("en", "Are customers asking for credit, or is stock the problem?"),
    ("en", "I'm an AI assistant from Workzap. What is your business called?"),
    ("en", "That sounds frustrating. When did it start?"),
    ("en", "Which of these costs you the most each month?"),
    ("en", "What have you tried so far to fix it?"),
    ("en", "Is it happening every day, or only some weeks?"),
    ("en", "Do your orders come late, or do your customers pay late?"),
    ("ru", "Ye maal kis cheez ka hai?"),
    ("ru", "Aap ka karobar kya karta hai?"),
    ("ru", "Kitne log kaam karte hain aap ki dukaan par?"),
    ("ru", "Yeh masla kab se hai?"),
    ("ru", "Customers udhaar maangte hain ya stock kam hai?"),
    ("ru", "Samajh gaya. Kitni baar hota hai yeh?"),
    ("ur", "آپ کا کاروبار کیا کام کرتا ہے؟"),
    ("ur", "یہ مسئلہ کب سے ہے؟"),
    ("ur", "آپ کی دکان پر کتنے لوگ کام کرتے ہیں؟"),
    ("ur", "کیا گاہک ادھار مانگتے ہیں یا مال کم ہے؟"),
    ("hi", "आपका कारोबार क्या काम करता है?"),
    ("hi", "यह समस्या कब से है?"),
    ("hi", "आपकी दुकान पर कितने लोग काम करते हैं?"),
    ("hi", "क्या ग्राहक उधार माँगते हैं या माल कम है?"),
    ("hi", "यह कितनी बार होता है?"),
    ("ar", "ما هو عملك؟"),
    ("ar", "منذ متى بدأت هذه المشكلة؟"),
    ("ar", "كم عدد الموظفين في المحل؟"),
    ("ar", "هل الزبائن يطلبون الدين أم المخزون قليل؟"),
    ("ar", "ماذا جربت حتى الآن لحل هذا؟"),
]


def _found(reply: str, owner: str, lang: str):
    return check(reply, owner, trade_confirmed=False, language=lang)


@pytest.mark.parametrize(("lang", "reply", "owner", "noun"), POSITIVES, ids=lambda v: str(v)[:30])
def test_an_assumed_trade_noun_is_a_finding(lang, reply, owner, noun) -> None:
    finding = _found(reply, owner, lang)
    assert finding is not None, reply
    assert noun.casefold() in reply.casefold()
    assert finding.language == lang
    assert finding.labels  # it names pack keys
    assert finding.noun and finding.noun in reply
    assert "ask openly" in finding.reason and finding.noun in finding.reason


def test_spec_example_is_a_finding_and_the_same_after_ac_repair_is_not() -> None:
    first = _found("AC units ya spare parts?", "", "ru")
    assert first is not None and first.noun == "AC"
    assert _found("AC units ya spare parts?", "I do AC repair", "ru") is None
    assert (
        _found("AC units ya spare parts?", ["hello", "we do AC repair"], "ru") is None
    )  # list form
    assert check("AC units ya spare parts?", "", trade_confirmed=True, language="ru") is None


@pytest.mark.parametrize(("reply", "owner", "confirmed"), EXCUSED)
def test_stated_confirmed_or_own_words_are_never_blocked(reply, owner, confirmed) -> None:
    assert check(reply, owner, trade_confirmed=confirmed, language="") is None


@pytest.mark.parametrize("word", irg.GENERIC_WORDS)
def test_generic_words_are_not_industry_nouns(word) -> None:
    assert _found(f"Tell me about the {word}?", "", "en") is None
    assert irg.nouns_in(word) == []


def test_the_owner_words_are_not_blocked_but_another_trade_is() -> None:
    # the owner said bakery: cake is theirs; an AC noun is a different trade and is still a Finding
    assert _found("Do your cakes sell well?", "I have a bakery", "en") is None
    other = _found("Do your AC units sell well?", "I have a bakery", "en")
    assert other is not None and other.noun == "AC"


def test_whole_words_only() -> None:
    # "ac" inside "practical" and "exact" is not the word "ac"
    assert _found("Which place is the most practical for you?", "", "en") is None
    assert _found("What is the exact reason for the delay?", "", "en") is None
    assert (
        _found("Is the hotel-style service the problem?", "", "en") is not None
    )  # a real hotel noun


def test_stems_catch_plural_and_article_forms() -> None:
    assert _found("How many trucks do you run?", "", "en") is not None
    assert _found("How many truck do you run?", "", "en") is not None
    assert _found("आपके पास कितने रेस्टोरेंटों में काम है?", "", "hi") is not None
    assert _found("كم عدد المطاعم عندك؟", "", "ar") is not None
    assert _found("هل لديك مطعم؟", "", "ar") is not None
    assert _found("ہسپتال میں کتنے مریض ہیں؟", "", "ur") is not None


def test_short_arabic_derived_words_are_not_trade_nouns() -> None:
    # "لان" (a cloth in Urdu, "because" in Arabic) and "حج" are in the packs but too short to trust
    assert _found("لان الوقت متأخر الآن", "", "ar") is None


def test_lexicon_keys_are_real_pack_keys() -> None:
    packs = ip.load_packs()
    assert [k for k in irg.TRADE_NOUNS if k not in packs] == []
    assert len(irg._lexicon()) > 500


def test_false_positive_control_on_ordinary_replies(capsys) -> None:
    hits = [(lang, reply) for lang, reply in ORDINARY if _found(reply, "", lang) is not None]
    with capsys.disabled():
        per = {}
        for lang, reply in ORDINARY:
            per.setdefault(lang, [0, 0])[0] += 1
            per[lang][1] += _found(reply, "", lang) is not None
        print(
            f"\nL1-8 false positives on ordinary replies: n={len(ORDINARY)} "
            + " ".join(f"{k}={v[1]}/{v[0]}" for k, v in sorted(per.items()))
        )
    assert hits == []
    assert len(ORDINARY) == 30


def test_recall_per_language_with_n(capsys) -> None:
    per: dict[str, list[int]] = {}
    for lang, reply, owner, _noun in POSITIVES:
        per.setdefault(lang, [0, 0])[0] += 1
        per[lang][1] += _found(reply, owner, lang) is not None
    with capsys.disabled():
        print("\nL1-8 trade noun recall (author's own table, no native review):")
        for lang, (n, hit) in sorted(per.items()):
            print(f"  {lang}: n={n} recall={hit / n:.2f}")
        total = sum(h for _, h in per.values())
        print(f"  all: n={len(POSITIVES)} recall={total / len(POSITIVES):.2f}")
    assert len(POSITIVES) == 25
    assert set(per) == {"en", "ru", "ur", "hi", "ar"}
    assert all(n == hit and n >= 4 for n, hit in per.values())


def test_mutation_without_the_detector_the_tables_fail(monkeypatch) -> None:
    """Mutation check: with the lexicon emptied (the detector removed in effect) no positive is
    found, so the recall table above would fail on every row; with a detector that always fires,
    the ordinary-reply control fails on every row. Both directions are covered."""
    monkeypatch.setattr(irg, "_lexicon", lambda: {})
    assert [r for _l, r, o, _n in POSITIVES if _found(r, o, "en") is not None] == []
    assert irg.nouns_in("AC units ya spare parts?") == []
    monkeypatch.setattr(
        irg,
        "nouns_in",
        lambda text, need_context=True: [("anything", frozenset({"hotels"}))] if text else [],
    )
    fired = [r for _l, r in ORDINARY if _found(r, "", "en") is not None]
    assert len(fired) == len(ORDINARY)
