"""PS-2: number WORDS count as figures in five languages; false positives guarded.

Written by one author, not reviewed by a native speaker of Hindi, Urdu or Arabic.
"""

import random
import time

import pytest

from app.modules.pi import figure_correction as fc

CORRECTIONS = [
    ("en", "not ten, a hundred", [], ("10", "100")),
    ("en", "Sorry, not ten, it was a hundred clients.", [], ("10", "100")),
    ("en", "I said ten but I meant a hundred", [], ("10", "100")),
    ("en", "not fifty thousand, five lakh", [], ("50000", "500000")),
    ("en", "not two hundred fifty, three hundred", [], ("250", "300")),
    ("en", "No wait, it is twenty five kg", ["We waste about 5 kg of rice."], ("5", "25")),
    ("en", "typo, a hundred", ["we have 10 clients"], ("10", "100")),
    ("roman_ur", "dus nahi, sau", [], ("10", "100")),
    ("roman_ur", "dus nahi sau staff hain", [], ("10", "100")),
    ("roman_ur", "paanch sau nahi, dus hazaar", [], ("500", "10000")),
    ("roman_ur", "nahi dus, balki sau", [], ("10", "100")),
    ("roman_ur", "dedh sau nahi, dhai sau", [], ("150", "250")),
    ("roman_ur", "paanch lakh nahi, dus lakh", [], ("500000", "1000000")),
    ("roman_ur", "aath nahi assi kirayedar late dete hain, do sau flats mein se", [], ("8", "80")),
    ("roman_ur", "galti se dus likha, sau hain", [], ("10", "100")),
    ("ur", "دس نہیں سو", [], ("10", "100")),
    ("ur", "نہیں دس، بلکہ سو", [], ("10", "100")),
    ("ur", "پانچ سو نہیں، دس ہزار", [], ("500", "10000")),
    ("ur", "ڈیڑھ سو نہیں، ڈھائی سو", [], ("150", "250")),
    ("hi", "दस नहीं सौ", [], ("10", "100")),
    ("hi", "नहीं दस, बल्कि सौ", [], ("10", "100")),
    ("hi", "पाँच सौ नहीं, दस हज़ार", [], ("500", "10000")),
    ("hi", "पचास हज़ार नहीं, पाँच लाख", [], ("50000", "500000")),
    ("ar", "ليس عشرة بل مئة", [], ("10", "100")),
    ("ar", "ليس عشرين بل مئتين", [], ("20", "200")),
    ("ar", "لا عشرة بل مائة عميل", [], ("10", "100")),
    ("ar", "ليس خمسين ألف بل خمسمئة ألف", [], ("50000", "500000")),
    ("ar", "ليس خمسة وعشرون بل مئة وخمسون", [], ("25", "150")),
]


@pytest.mark.parametrize(("lang", "latest", "earlier", "expected"), CORRECTIONS)
def test_word_corrections_are_found_with_normalised_values(lang, latest, earlier, expected):
    assert fc.numeric_correction(latest, earlier) == expected


def test_arabic_la_after_the_first_figure_keeps_the_audited_direction():
    # "100، لا 10" is right-first in the audited L1 code; the same shape in words follows it.
    assert fc.numeric_correction("مئة لا عشرة", []) == ("10", "100")
    assert fc.numeric_correction("عشرة لا مئة", []) == ("100", "10")


@pytest.mark.parametrize(
    ("text", "figures"),
    [
        ("we have ten clients", ["10"]),
        ("two hundred fifty orders", ["250"]),
        ("a hundred and fifty staff", ["150"]),
        ("fifty thousand rupees", ["50000"]),
        ("five lakh", ["500000"]),
        ("twenty-five days", ["25"]),
        ("one million dollars", ["1000000"]),
        ("paanch sau log", ["500"]),
        ("dus hazaar rupay", ["10000"]),
        ("ek lakh pachas hazaar", ["150000"]),
        ("dedh sau", ["150"]),
        ("dhai hazaar rupay", ["2500"]),
        ("do din", ["2"]),
        ("پانچ لاکھ", ["500000"]),
        ("دس ہزار روپے", ["10000"]),
        ("ڈیڑھ لاکھ", ["150000"]),
        ("ڈھائی سو لوگ", ["250"]),
        ("पाँच लाख", ["500000"]),
        ("दस हज़ार रुपये", ["10000"]),
        ("एक सौ पचास", ["150"]),
        ("डेढ़ सौ", ["150"]),
        ("ثلاثة آلاف عميل", ["3000"]),
        ("عشرة آلاف", ["10000"]),
        ("ثلاثة عشر موظفا", ["13"]),
        ("مئة وخمسون", ["150"]),
        ("ثلاثمئة", ["300"]),
        ("مليون", ["1000000"]),
        ("5 hundred", ["500"]),
        ("5 sau", ["500"]),
    ],
)
def test_number_words_are_figures(text, figures):
    assert fc.numbers_in(text) == figures


@pytest.mark.parametrize(
    "forms",
    [
        ["5 lakh", "paanch lakh", "پانچ لاکھ", "पाँच लाख", "five lakh", "500000", "5,00,000"],
        ["100", "sau", "a hundred", "ek sau", "سو", "सौ", "مئة"],
        ["10", "dus", "ten", "دس", "दस", "عشرة"],
    ],
)
def test_same_value_in_different_forms_is_not_a_correction(forms):
    for a in forms:
        for b in forms:
            if a == b:
                continue
            assert fc.numeric_correction(f"not {a}, {b}", []) is None, (a, b)
            assert fc.numeric_correction(f"{a} nahi, {b}", []) is None, (a, b)


def test_same_value_forms_normalise_to_one_value():
    values = {
        tuple(fc.numbers_in(f"{f} clients"))
        for f in ["5 lakh", "paanch lakh", "پانچ لاکھ", "पाँच लाख", "five lakh", "500000"]
    }
    assert values == {("500000",)}


@pytest.mark.parametrize(
    "text",
    [
        "kar do",
        "mujhe batao, kar do jaldi",
        "ye kaam kar do nahi to",
        "one of my staff left",
        "not one of my staff",
        "I am the one who called",
        "no one came",
        "a hundred percent sure",
        "hundred percent",
        "sau percent sahi hai",
        "sau fisad theek",
        "a thousand times sorry",
        "thousand thanks",
        "lakh shukriya",
        "ek dukan hai",
        "ek banda aya tha",
        "ek",
        "Mr Das came",
        "Das Enterprises",
        "mere saath chalo",
        "saath mein hai",
        "saunf aur sauda",
        "arsaus and sausage",
        "dos and donts",
        "tendon",
        "chay peeni hai",
        "aik minute",
        "ایک دکان ہے",
        "دو نہیں",  # a lone word with no second figure is not a figure pair
        "سو جاؤ",
        "ہمارے ساتھ",
        "एक दुकान है",
        "मुझे दो",
        "واحد",
        "هو واحد من الموظفين",
        "ست الحبايب",
        "teen age bacche",
        "the teen center",
    ],
)
def test_ambiguous_words_are_not_figures(text):
    assert fc.numbers_in(text) == [], text
    assert fc.numeric_correction(text, ["we have 10 clients"]) is None, text


def test_the_figure_is_only_the_phrase_not_a_neighbouring_word():
    assert fc.numbers_in("das naam") == []  # ambiguous, no count noun
    assert fc.numbers_in("sau") == []  # one bare magnitude with no context
    assert fc.numbers_in("ten") == ["10"]
    assert fc.numbers_in("kar do sau rupay") == ["100"]  # the verb "do" is not the 2 of "do sau"


def test_replace_figure_with_words():
    assert fc.replace_figure("we lost ten clients", "10", "100") == "we lost 100 clients"
    assert fc.replace_figure("dus log aur 20 bags", "10", "100") == "100 log aur 20 bags"
    assert fc.replace_figure("پانچ سو لوگ", "500", "900") == "900 لوگ"
    assert fc.replace_figure("about a hundred staff", "100", "90") == "about 90 staff"
    assert fc.replace_figure("5 lakh and paanch lakh", "500000", "9") == "9 and 9"
    assert fc.replace_figure("one of us", "1", "2") == "one of us"


def test_expand_and_has_figure_and_reply_problem_with_words():
    assert fc.expand("not ten, a hundred") == "not 10, 100"
    assert fc.has_figure("sau clients", "100")
    assert fc.reply_problem("Noted: sau clients, not dus. What caused it?", "10", "100") is None
    assert fc.reply_problem("Noted: ten clients lost.", "10", "100")


def test_digit_behaviour_is_unchanged():
    assert fc.numeric_correction("not 10, 100", []) == ("10", "100")
    assert fc.numeric_correction("10 nahi, 100", []) == ("10", "100")
    assert fc.numbers_in("5 lakh, 12,50,000") == ["500000", "1250000"]


NON_STRINGS = [None, 5, b"ten", ["ten"], {"a": 1}, object()]


@pytest.mark.parametrize("bad", NON_STRINGS)
def test_never_raises_on_non_strings(bad):
    assert fc.numbers_in(bad) == []
    assert fc.expand(bad) == ""
    assert fc.replace_figure(bad, "10", "100") == ""
    assert fc.numeric_correction(bad, [bad, "ten"]) is None


def test_max_input_cap_still_holds():
    long = "dus nahi sau " + "x " * 3000
    assert fc.numeric_correction(long, []) is None


def test_fuzz_never_raises():
    rnd = random.Random(7)
    pieces = [
        "ten",
        "sau",
        "do",
        "ek",
        "lakh",
        "hazaar",
        "nahi",
        "not",
        "a",
        "and",
        "و",
        "عشرة",
        "مئة",
        "دس",
        "सौ",
        "दस",
        "5",
        "٥",
        "१०",
        ",",
        ".",
        "-",
        " ",
        "क",
        "ڈیڑھ",
        "dedh",
        "k",
        "%",
        "،",
    ]
    for _ in range(3000):
        text = "".join(rnd.choice(pieces) + rnd.choice([" ", "", "-", ","]) for _ in range(30))
        fc.numeric_correction(text, [text])
        fc.numbers_in(text)
        fc.replace_figure(text, "10", "100")
        fc.expand(text)


@pytest.mark.parametrize("n", [1_000, 10_000, 100_000])
@pytest.mark.parametrize(
    "unit",
    [
        "ten hundred thousand lakh ",
        "do sau hazaar nahi ",
        "عشرة مئة ألف ",
        "x" * 50 + " ",
        "و" * 9 + " ",
        "1,",
    ],
)
def test_linear_time(n, unit):
    text = (unit * (n // len(unit) + 1))[:n]
    t0 = time.perf_counter()
    fc.numbers_in(text)
    fc.expand(text)
    fc.replace_figure(text, "10", "100")
    fc.numeric_correction(text, [text])
    assert time.perf_counter() - t0 < 6.0


def test_time_grows_about_linearly():
    unit = "ten hundred thousand lakh dus sau nahi "

    def run(n):
        text = (unit * (n // len(unit) + 1))[:n]
        t0 = time.perf_counter()
        fc.numbers_in(text)
        return time.perf_counter() - t0

    run(10_000)
    small, big = min(run(20_000) for _ in range(3)), min(run(200_000) for _ in range(3))
    assert big < small * 10 * 4 + 0.05
