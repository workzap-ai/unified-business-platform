"""L1-7a: figure corrections, already-answered asks and list items in Hindi, Arabic, Urdu script,
Roman Urdu and English.

HONEST LIMIT. Every sentence below was written by one author. No native speaker of Hindi, Urdu or
Arabic has reviewed them, and they are not real owner messages. The tables are small (n is printed
by the summary test and asserted, so a table cannot shrink unnoticed). Recall and precision are
measured on these tables only: they show the recogniser does what its author meant, not how it does
on real traffic. The shared fixtures in evalkit/cases/*.json are not touched (their counts are
pinned); the new cases live here.
"""

import re

import pytest

from app.modules.pi import figure_correction as fc
from app.modules.pi import list_items as li
from app.modules.pi import reply_gates as rg
from app.modules.pi import script_words as sw

# (language, latest message, earlier owner messages, expected (wrong, right) or None)
CORRECTIONS: list[tuple[str, str, list[str], tuple[str, str] | None]] = [
    # English
    ("en", "Not 10, 100", [], ("10", "100")),
    ("en", "Sorry, not 10, it was 100 clients.", ["We lost about 10 clients."], ("10", "100")),
    ("en", "100, not 10", [], ("10", "100")),
    ("en", "Actually 15 kg, I checked.", ["We waste about 5 kg of rice."], ("5", "15")),
    ("en", "No wait, it is 5 lakh", ["We spend 2 lakh a month"], None),  # other words: no guess
    ("en", "Not 2 lakh, 5 lakh", [], ("200000", "500000")),
    ("en", "No, I have 3 shops.", ["We lost about 10 clients."], None),
    ("en", "We have 100 clients.", ["We lost about 10 clients."], None),
    # Roman Urdu
    ("ru", "10 nahi, 100", [], ("10", "100")),
    ("ru", "Nahi 20 nahi, 12 staff hain.", ["20 staff hain"], ("20", "12")),
    ("ru", "nahi 10 balki 100", [], ("10", "100")),
    ("ru", "100 hai, 10 nahi", [], ("10", "100")),
    ("ru", "10 nahi 5 hazar", [], ("10", "5000")),
    ("ru", "galat, 12 staff hain", ["Mere 20 staff hain"], ("20", "12")),
    ("ru", "yeh kaam nahi karta", ["10 log hain"], None),
    ("ru", "mashine nahi chalti, 3 din se", ["10 din se band hai"], ("10", "3")),
    ("ru", "nahi, wo 5 staff hain", ["Mere 20 shops hain"], None),
    # Urdu script
    ("ur", "نہیں 10 نہیں، 100", [], ("10", "100")),
    ("ur", "10 نہیں، 100", [], ("10", "100")),
    ("ur", "نہیں 10 بلکہ 100", [], ("10", "100")),
    ("ur", "100 ہے، 10 نہیں", [], ("10", "100")),
    ("ur", "غلط، ۱۲ ملازم ہیں", ["میرے ۲۰ ملازم ہیں"], ("20", "12")),
    ("ur", "نہیں 2 لاکھ نہیں 5 لاکھ", [], ("200000", "500000")),
    ("ur", "10 ہزار نہیں، 20 ہزار", [], ("10000", "20000")),
    ("ur", "یہ کام نہیں ہوتا", ["۱۰ لوگ ہیں"], None),
    ("ur", "نہیں، ہمارے 3 ملازم ہیں", ["ہمارے 10 دکانیں ہیں"], None),
    # Hindi (Devanagari)
    ("hi", "10 नहीं, 100", [], ("10", "100")),
    ("hi", "नहीं 10 नहीं, 100", [], ("10", "100")),
    ("hi", "नहीं 10 बल्कि 100", [], ("10", "100")),
    ("hi", "100 है, 10 नहीं", [], ("10", "100")),
    ("hi", "गलत, १२ कर्मचारी हैं", ["मेरे २० कर्मचारी हैं"], ("20", "12")),
    ("hi", "दरअसल 15 किलो है", ["हम 5 किलो चावल बर्बाद करते हैं"], ("5", "15")),
    ("hi", "2 लाख नहीं, 5 लाख", [], ("200000", "500000")),
    ("hi", "10 हज़ार नहीं, 20 हज़ार", [], ("10000", "20000")),
    ("hi", "३ करोड़ नहीं, 2 करोड़", [], ("30000000", "20000000")),
    ("hi", "यह काम नहीं करता", ["10 लोग हैं"], None),
    ("hi", "नहीं, मेरे 3 कर्मचारी हैं", ["मेरी 10 दुकानें हैं"], None),
    # Arabic
    ("ar", "لا 10 بل 100", [], ("10", "100")),
    ("ar", "ليس 10 بل 100", [], ("10", "100")),
    ("ar", "100 وليس 10", [], ("10", "100")),
    ("ar", "لا ١٠ بل ١٠٠", [], ("10", "100")),  # Arabic-Indic digits
    ("ar", "لا 10 بل ١٠٠", [], ("10", "100")),  # mixed digit systems
    ("ar", "لا 2 مليون بل 5 مليون", [], ("2000000", "5000000")),
    ("ar", "لا 3 ألف بل 4 ألف", [], ("3000", "4000")),
    ("ar", "خطأ، عندي ١٢ موظف", ["عندي ٢٠ موظف"], ("20", "12")),
    ("ar", "لا أعرف، ما عدد الموظفين؟", ["عندي 20 موظف"], None),  # a question with لا
    ("ar", "هل لا يزال عندك 5 موظفين؟", ["عندي 10 محلات"], None),
    ("ar", "لا، عندي 3 فروع", ["عندي 10 موظفين"], None),
    # Mixed English and Hindi digits
    ("mix", "not १० , 100", [], ("10", "100")),
]
NEGATIVES = sum(1 for c in CORRECTIONS if c[3] is None)
POSITIVES = len(CORRECTIONS) - NEGATIVES


def _per_language() -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for lang, latest, earlier, expected in CORRECTIONS:
        got = fc.numeric_correction(latest, earlier)
        s = stats.setdefault(lang, {"n": 0, "pos": 0, "found": 0, "right": 0, "returned": 0})
        s["n"] += 1
        s["pos"] += expected is not None
        s["found"] += expected is not None and got == expected
        s["returned"] += got is not None
        s["right"] += got is not None and got == expected
    return stats


@pytest.mark.parametrize(
    ("lang", "latest", "earlier", "expected"), CORRECTIONS, ids=lambda v: str(v)[:40]
)
def test_correction_table(lang, latest, earlier, expected) -> None:
    assert fc.numeric_correction(latest, earlier) == expected


def test_correction_recall_and_precision_with_n(capsys) -> None:
    stats = _per_language()
    with capsys.disabled():
        print("\nL1-7a figure correction (author's own table, no native review):")
        for lang, s in sorted(stats.items()):
            recall = s["found"] / s["pos"] if s["pos"] else float("nan")
            precision = s["right"] / s["returned"] if s["returned"] else float("nan")
            print(
                f"  {lang}: n={s['n']} positives={s['pos']} recall={recall:.2f} "
                f"precision={precision:.2f}"
            )
        total = {
            k: sum(s[k] for s in stats.values()) for k in ("n", "pos", "found", "right", "returned")
        }
        print(
            f"  all: n={total['n']} recall={total['found'] / total['pos']:.2f} "
            f"precision={total['right'] / total['returned']:.2f}"
        )
    assert sum(s["n"] for s in stats.values()) == len(CORRECTIONS) == 49
    assert {"en", "ru", "ur", "hi", "ar"} <= stats.keys()
    for lang in ("en", "ru", "ur", "hi", "ar"):
        s = stats[lang]
        assert s["pos"] >= 4, f"{lang}: too few positives to mean anything"
        assert s["found"] == s["pos"], f"{lang} recall below 1.0 on its own table"
        assert s["right"] == s["returned"], f"{lang} precision below 1.0 on its own table"
    assert POSITIVES + NEGATIVES == 49


@pytest.mark.parametrize(
    ("text", "figure"),
    [
        ("5 lakh", "500000"),
        ("5 لاکھ", "500000"),
        ("५ लाख", "500000"),
        ("2 crore", "20000000"),
        ("2 کروڑ", "20000000"),
        ("2 करोड़", "20000000"),
        ("10 hazar", "10000"),
        ("10 हज़ार", "10000"),
        ("10 ہزار", "10000"),
        ("10 ألف", "10000"),
        ("3 مليون", "3000000"),
        ("1.5 lakh", "150000"),
        ("10k", "10000"),
        ("١٢٣٫٥", "123.5"),
    ],
)
def test_scaled_and_eastern_figures_are_read(text, figure) -> None:
    assert fc.numbers_in(text) == [figure]


def test_a_kg_is_not_a_thousand() -> None:
    assert fc.numbers_in("10 kg") == ["10"]
    assert fc.numbers_in("10 km") == ["10"]


def test_replace_figure_with_scale_and_digits() -> None:
    assert fc.replace_figure("Hum 2 lakh kharch karte hain", "200000", "500000") == (
        "Hum 500000 kharch karte hain"
    )
    assert fc.replace_figure("हम १० लोग हैं", "10", "12") == "हम 12 लोग हैं"


def test_reply_problem_in_scripts() -> None:
    # the reply must use the new figure, and may mention the old one as an acknowledgement
    assert fc.reply_problem("ठीक है, 10 नहीं, 100 लोग।", "10", "100") is None
    assert fc.reply_problem("ٹھیک ہے، 10 نہیں، 100 لوگ۔", "10", "100") is None
    assert fc.reply_problem("حسنا، ١٠٠ موظف وليس 10.", "10", "100") is None
    assert fc.reply_problem("ठीक है, 10 लोग हैं।", "10", "100") is not None
    assert fc.reply_problem("ठीक है, 100 लोग और 10 दुकानें।", "10", "100") is not None


# --- reply_gates: asks the owner already answered ---------------------------------------------

ASKS: list[tuple[str, str, list[str], bool]] = [
    # (language, reply, owner texts, must be flagged)
    ("hi", "आपके पास कितनी दुकानें हैं?", ["मेरी 5 दुकानें हैं"], True),
    ("hi", "आपके पास कितनी दुकानें हैं?", ["मेरी पाँच दुकानें हैं"], True),
    ("hi", "ये कब से हो रहा है?", ["यह 3 महीने से हो रहा है"], True),
    ("hi", "कितने दिन से ऐसा है?", ["पिछले साल से"], True),
    ("hi", "कितनी बार होता है?", ["यह रोज़ होता है"], True),
    ("hi", "कितनी बार होता है?", ["दिन में 3 बार"], True),
    ("hi", "आपके पास कितनी दुकानें हैं?", ["मेरा काम धीमा है"], False),
    ("hi", "ये कब से हो रहा है?", ["मेरी 5 दुकानें हैं"], False),
    ("ur", "آپ کی کتنی دکانیں ہیں؟", ["میری 5 دکانیں ہیں"], True),
    ("ur", "یہ کب سے ہو رہا ہے؟", ["یہ 3 مہینے سے ہو رہا ہے"], True),
    ("ur", "کتنی بار ہوتا ہے؟", ["روزانہ ہوتا ہے"], True),
    ("ur", "آپ کی کتنی دکانیں ہیں؟", ["کام سست ہے"], False),
    ("ar", "كم عدد الموظفين؟", ["عندي 12 موظفين"], True),
    ("ar", "كم عدد الموظفين؟", ["عندي ١٢ موظفين"], True),
    ("ar", "منذ متى بدأ هذا؟", ["بدأ منذ 3 أشهر"], True),
    ("ar", "منذ متى بدأ هذا؟", ["بدأ منذ سنتين"], True),
    ("ar", "كم مرة يحدث هذا؟", ["يحدث كل يوم"], True),
    ("ar", "كم عدد الموظفين؟", ["المبيعات قليلة"], False),
    ("ar", "هل لا يزال لديك موظفون؟", ["عندي 12 موظفين"], False),  # no count asked
    ("ur", "کیا آپ کے پاس کم گاہک ہیں؟", ["میرے 5 گاہک ہیں"], False),  # Urdu کم is "few"
    # English and Roman Urdu keep working
    ("en", "How many shops do you have?", ["I have 4 shops"], True),
    ("ru", "Kitni dukaan hain?", ["Meri 3 dukaan hain"], True),
    ("en", "How often does it happen?", ["It is slow"], False),
]


@pytest.mark.parametrize(("lang", "reply", "owner", "flag"), ASKS, ids=lambda v: str(v)[:36])
def test_fact_already_given(lang, reply, owner, flag) -> None:
    assert bool(rg.fact_already_given(reply, owner)) is flag


def test_known_in_record_in_scripts() -> None:
    noted = [{"missing": ["cost"]}]  # since and how_often are not missing: the record holds them
    for question in (
        "ये कब से हो रहा है?",
        "یہ کب سے ہو رہا ہے؟",
        "منذ متى بدأ هذا؟",
        "when did it start? since when?",
    ):
        assert rg.known_in_record(question, noted)
    for question in ("कितनी बार होता है?", "کتنی بار ہوتا ہے؟", "كم مرة يحدث هذا؟"):
        assert rg.known_in_record(question, noted)
    missing = [{"missing": ["since", "how_often"]}]
    assert rg.known_in_record("ये कब से हो रहा है?", missing) is None
    assert rg.known_in_record("आपकी कितनी दुकानें हैं?", noted) is None


def test_asks_table_n(capsys) -> None:
    flagged = [a for a in ASKS if a[3]]
    clear = [a for a in ASKS if not a[3]]
    langs = {a[0] for a in ASKS}
    hit = sum(bool(rg.fact_already_given(a[1], a[2])) for a in flagged)
    false_alarm = sum(bool(rg.fact_already_given(a[1], a[2])) for a in clear)
    with capsys.disabled():
        print(
            f"\nL1-7a already-answered asks: n={len(ASKS)} (asked-and-said={len(flagged)}, "
            f"not-a-repeat={len(clear)}) recall={hit}/{len(flagged)} "
            f"false alarms={false_alarm}/{len(clear)}"
        )
    assert len(ASKS) == 23 and langs == {"hi", "ur", "ar", "en", "ru"}
    assert hit == len(flagged) and false_alarm == 0


# --- list_items: Devanagari, Urdu script and Arabic ---------------------------------------------


def test_devanagari_words_are_not_split_at_vowel_signs() -> None:
    assert [m.group(0) for m in sw.WORD.finditer("दुकानें, मेरी")] == ["दुकानें", "मेरी"]
    assert sw.tokens("दुकानें दुकानों दुकान") == ["दुकान"] * 3
    # the old \w+ splitting cut a Devanagari word into pieces
    assert len(re.findall(r"\w+", "दुकानें")) > 1


def test_arabic_marks_stay_inside_the_word() -> None:
    assert [m.group(0) for m in sw.WORD.finditer("مُوَظَّفُونَ؟")] == ["مُوَظَّفُونَ"]
    assert sw.tokens("الموظفين") == sw.tokens("موظفين")


HINDI_LIST = (
    "१. हमारी दुकान में बिजली बार-बार जाती है\n"
    "२. कर्मचारी समय पर नहीं आते हैं\n"
    "३. ग्राहक उधार लेकर पैसे नहीं देते हैं"
)
URDU_LIST = (
    "- ہماری دکان میں بجلی بار بار جاتی ہے\n"
    "- ملازمین وقت پر نہیں آتے ہیں\n"
    "- گاہک ادھار لے کر پیسے نہیں دیتے ہیں"
)
ARABIC_LIST = (
    "١. الكهرباء تنقطع كثيرا في المحل\n"
    "٢. الموظفون لا يحضرون في الوقت المحدد\n"
    "٣. الزبائن يأخذون بالدين ولا يدفعون"
)
ENGLISH_LIST = (
    "1. The power keeps going off in the shop\n"
    "2. Staff do not come on time\n"
    "3. Customers take credit and never pay"
)
LISTS = {"hi": HINDI_LIST, "ur": URDU_LIST, "ar": ARABIC_LIST, "en": ENGLISH_LIST}
# notes that cover items 1 and 2 only, in the same language: item 3 must be reported as dropped
NOTES = {
    "hi": ["दुकान में बिजली जाती है", "कर्मचारी समय पर नहीं आते"],
    "ur": ["دکان میں بجلی جاتی ہے", "ملازمین وقت پر نہیں آتے"],
    "ar": ["الكهرباء تنقطع في المحل", "الموظفون لا يحضرون في الوقت"],
    "en": ["power keeps going off in the shop", "staff do not come on time"],
}
FULL_NOTES = {
    "hi": [*NOTES["hi"], "ग्राहक उधार लेते हैं और पैसे नहीं देते"],
    "ur": [*NOTES["ur"], "گاہک ادھار لیتے ہیں اور پیسے نہیں دیتے"],
    "ar": [*NOTES["ar"], "الزبائن يأخذون بالدين ولا يدفعون"],
    "en": [*NOTES["en"], "customers take credit and never pay"],
}


@pytest.mark.parametrize("lang", sorted(LISTS))
def test_list_split_and_no_drop(lang) -> None:
    found = li.items(LISTS[lang])
    assert len(found) == 3
    missing = li.dropped([LISTS[lang]], NOTES[lang])
    assert [it.id for it in missing] == ["c3"], lang
    assert li.dropped([LISTS[lang]], FULL_NOTES[lang]) == []


def test_digit_systems_in_list_numbering_and_figures() -> None:
    inline = "١. बिजली जाती है यहाँ अक्सर ٢. कर्मचारी देर से आते हैं बहुत"
    assert len(li.items(inline)) == 2
    item = li.items("- हर महीने ५००० रुपये का नुकसान होता है\n- कर्मचारी देर से आते हैं रोज")[0]
    assert item.figures == ("5000",)
    assert li.covered(item, ["loss of 5000 rupees"])  # figure in another digit system
    assert li.items("- 5 lakh ka nuksan hota hai har mahine\n- staff late aata hai roz")[
        0
    ].figures == ("500000",)


def test_a_heading_is_not_an_item() -> None:
    # a line of fewer than three words is a heading in every script
    for message in (
        "समस्याएं:\n- बिजली बार बार जाती है यहाँ",
        "المشاكل:\n- الكهرباء تنقطع كثيرا هنا",
        "مسائل:\n- بجلی بار بار جاتی ہے",
    ):
        assert li.items(message) == []
    heading_plus_two = "समस्याएं:\n- बिजली बार बार जाती है यहाँ\n- कर्मचारी देर से आते हैं रोज"
    assert [it.text for it in li.items(heading_plus_two)][0].startswith("बिजली")
    assert len(li.items(heading_plus_two)) == 2


def test_stopwords_do_not_make_a_match() -> None:
    # a Hindi item made only of function words and a shared stopword must not count as covered
    item = li.Item("c1", "और है कि मेरा बहुत अभी", ())
    assert li._words(item.text) == set()
    assert li._words("बिजली जाती है") == {"बिजली", "जाती"}
    assert li._words("الكهرباء تنقطع في المحل") >= {"كهرباء"[:5], "تنقطع"[:5]}


def test_english_and_roman_urdu_lists_unchanged() -> None:
    roman = "- mera maal bik nahi raha hai\n- staff late aata hai roz\n- bijli bar bar jati hai"
    assert len(li.items(roman)) == 3
    assert li.dropped([roman], ["maal bik nahi raha", "staff late aata hai"])[0].id == "c3"
