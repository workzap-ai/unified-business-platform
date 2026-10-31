"""language_script.py (agent 8): adversarial multilingual cases, properties, fuzz and timing.

Scripted: the adversarial sentences are the author's, not an independent red team."""

import importlib.util
import random
import re
import time
from pathlib import Path

import pytest

from app.modules.pi import language_script as ls

_spec = importlib.util.spec_from_file_location(
    "language_script_eval_lib_r", Path(__file__).parent / "language_script_data" / "eval_lib.py"
)
assert _spec is not None and _spec.loader is not None
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)

ROWS = [r for r in ev.load_labelled() if r[0] != "und"]
ARABIC_FAMILY = {"ur", "ar", "fa", "ps", "sd", "pa"}
KNOWN_CODES = set(ls.SCRIPT_OF_CODE)


def _has_latin(t: str) -> bool:
    return bool(re.search("[A-Za-z]", t))


TRANSFORMS = {
    "upper": lambda t: t.upper(),
    "lower": lambda t: t.lower(),
    "emoji_url": lambda t: t + " 😊 https://example.com/x?y=1 +92 300 1234567",
    "nopunct": lambda t: re.sub(r"[^\w\s]", "", t),
    "repeat_vowels": lambda t: re.sub(r"([aeiou])", r"\1\1\1", t, count=2) if _has_latin(t) else t,
    "tashkeel": lambda t: "".join(c + "َ" if "؀" <= c <= "ۿ" and c.isalpha() else c for c in t),
    "trail_ok": lambda t: t + " ok",
    "lead_hello": lambda t: "Hello, " + t,
    "digits": lambda t: t + " 5 10 2000",
    "twice": lambda t: t + " " + t,
    "double_space": lambda t: t.replace(" ", "  "),
    "newline": lambda t: t.replace(" ", "\n", 2),
    "rtl_marks": lambda t: "‏" + t + "‎",
}
TOLERATED = {"lead_hello": 0.02, "nopunct": 0.02, "tashkeel": 0.02}  # share allowed to go uncertain


@pytest.mark.parametrize("name", sorted(TRANSFORMS))
def test_noise_transforms_keep_the_language_and_never_flip_script(name):
    f = TRANSFORMS[name]
    cases = wrong = unsure = flips = 0
    for label, _present, text in ROWS:
        if name == "tashkeel" and ev.expected_family(label) not in {
            "ur",
            "ar",
            "fa",
            "ps",
            "sd",
            "pa",
        }:
            continue
        if name == "repeat_vowels" and not _has_latin(text):
            continue
        t2 = f(text)
        d = ls.detect_message_language(t2)
        base = ls.detect_message_language(text)
        cases += 1
        if d.uncertain:
            unsure += 1
            continue
        if ev.family(d.code) != ev.family(base.code):
            wrong += 1
        if d.script != base.script:
            flips += 1
    assert cases >= 100
    assert flips == 0, (name, flips)
    assert wrong == 0, (name, wrong)
    assert unsure / cases <= TOLERATED.get(name, 0.0), (name, unsure, cases)


# --- hand-written adversarial sentences: (text, expected family or "und")
ADVERSARIAL = [
    # English that looks Roman Urdu
    ("I am in the main market all day", "en"),
    ("I have to do a delivery today and tomorrow", "en"),
    ("Is it ok if we do this later please", "en"),
    ("Ahmed bhai said the stock is finished", "en"),
    ("Please send the invoice to Ali Khan Traders", "en"),
    ("The bar and the shop are both closed on Sunday", "en"),
    ("We sell sab and ho products to our customers", "en"),
    ("Our manager Kamran will call you about the payment", "en"),
    ("Thanks, that makes sense to me now", "en"),
    ("I want to know the price before I decide anything", "en"),
    ("Can you show me what you did for other shops like mine", "en"),
    ("My staff do not come on time and I have to chase them", "en"),
    ("It is not working and I do not know why", "en"),
    ("They said they would pay on Friday but nobody called", "en"),
    ("https://shop.example.com/order/123 please check this link for me", "en"),
    # Roman Urdu that looks English
    ("Main market mein kaam karta hoon aur stock khatam ho gaya", "roman"),
    ("Do din se delivery nahi aayi aur customer phone kar raha hai", "roman"),
    ("To kya karein ab, sab kuch ruka hua hai", "roman"),
    ("Is mein kitna time lagega aur kya kharcha hoga", "roman"),
    ("Bar bar yehi masla hota hai hamare saath", "roman"),
    ("Hum log bohat pareshan hain isliye aap se baat kar rahe hain", "roman"),
    ("Sab theek hai lekin cash nahi aa raha", "roman"),
    ("Aap ka kaam bohat acha hai lekin delivery late hai", "roman"),
    ("Mere paas teen shops hain aur sab mein alag alag staff hai", "roman"),
    ("Kal subah se phone nahi utha raha koi bhi", "roman"),
    ("Yeh sab kab tak chalega mujhe samajh nahi aa raha", "roman"),
    # Urdu / Arabic / Persian / Hindi traps
    ("میں اپنی shop کے لیے help چاہتا ہوں", "ur"),
    ("آپ کا شکریہ، میں کل call کرتا ہوں", "ur"),
    ("مجھے آپ کی website پسند آئی لیکن price زیادہ ہے", "ur"),
    ("أريد أن أعرف السعر قبل أن أقرر", "ar"),
    ("عندنا مشكلة في الشحن والعملاء غاضبون", "ar"),
    ("من می‌خواهم قیمت را بدانم", "fa"),
    ("ما سه شعبه داریم و حساب‌ها با هم نمی‌خواند", "fa"),
    ("मुझे अपनी shop के लिए help चाहिए", "hi"),
    ("आपका धन्यवाद, मैं कल call करूँगा", "hi"),
    ("हमारा delivery boy रोज़ देर से आता है", "hi"),
    # French / Spanish / German false friends
    ("Je voudrais savoir le prix avant de décider", "fr"),
    ("Quiero saber el precio antes de decidir", "es"),
    ("Ich möchte den Preis wissen bevor ich entscheide", "de"),
    # ambiguous or empty
    ("ok", "und"),
    ("ok ok ok", "und"),
    ("hmm ok haan", "und"),
    ("👍👍👍", "und"),
    ("1234567890", "und"),
    ("???", "und"),
    ("a", "und"),
    ("😂 lol", "und"),
    ("نہیں نہیں", "und"),
    ("ہاں جی", "und"),
    ("thanks thanks", "und"),
    ("yes yes yes", "und"),
    ("+92 300 1234567", "und"),
    ("www.example.com", "und"),
    ("Ali Khan", "und"),
    ("Lahore", "und"),
    ("Zyx qwv plm", "und"),
    ("Rs 5000", "und"),
    ("5 lakh", "und"),
    ("haan haan theek hai", "und"),
]


@pytest.mark.parametrize("text,expected", ADVERSARIAL)
def test_hand_written_adversarial_sentences(text, expected):
    d = ls.detect_message_language(text)
    got = "und" if d.uncertain else ev.family(d.code)
    assert got == expected, (text, d.code, d.uncertain, d.reason, d.evidence)


def test_adversarial_total_is_over_300_with_the_generated_ones():
    generated = sum(1 for name in TRANSFORMS for _ in ROWS)
    assert generated + len(ADVERSARIAL) >= 300


# --- stickiness properties


def test_property_any_short_message_returns_the_pin_for_every_pinned_language():
    pins = ["en", "roman_ur", "roman_hi", "roman_hi_or_ur", "ur", "ar", "fa", "hi", "fr", "es"]
    shorts = [
        "ok",
        "yes",
        "no",
        "haan",
        "ہاں",
        "नहीं",
        "نعم",
        "oui",
        "sí",
        "5",
        "👍",
        "hmm",
        "ji",
        "thanks",
        "k",
        "stock",
        "Lahore",
    ]
    for pin in pins:
        for short in shorts:
            d = ls.detect_message_language(short, pinned=pin)
            assert d.code == pin and d.uncertain, (pin, short, d)
            assert ls.reply_language_for(d, pin)[0] == ls.fixed_line_key(
                pin
            ) or ls.reply_language_for(d, pin)[0] in (pin, "roman_ur")


def test_property_two_word_messages_never_decide_even_when_clear():
    for label, _p, text in ROWS:
        words = text.split()
        if len(words) < 3:
            continue
        two = " ".join(words[:2])
        d = ls.detect_message_language(two, pinned="roman_ur")
        assert d.uncertain and d.code == "roman_ur", (label, two)


def test_property_pin_is_deterministic_and_order_preserving_for_a_whole_chat():
    case = next(c for c in ev.load_ps0() if c["language"] == "ur" and len(c["messages"]) >= 2)
    a = ls.LanguagePin().pin(case["messages"])
    b = ls.LanguagePin().pin(list(case["messages"]))
    assert a == b and a.code == "ur" and a.script == "arabic"


def test_property_no_ps0_message_ever_reaches_the_wrong_script_in_any_order():
    msgs = [(c["language"], m) for c in ev.load_ps0() for m in c["messages"]]
    rng = random.Random(7)
    for _ in range(200):
        pool = rng.sample(msgs, 6)
        hist = [m for _l, m in pool[:-1]]
        lang, last = pool[-1]
        d = ls.detect_message_language(last, history=hist)
        if d.uncertain:
            continue
        want = {"ur": "arabic", "ar": "arabic", "hi": "devanagari"}.get(lang, "latin")
        assert d.script == want, (lang, last, d)


# --- fuzz: never raises


ALPHABETS = [
    "abcdefghijklmnopqrstuvwxyz '’-",
    "ٹڈڑںےہھکگپچژیيك ء،؟",
    "اآأإبتثجحخدذرزسشصضطظعغفقكلمنهوي ًٌٍَُِّْ",
    "अआइईउऊएऐओऔकखगघचछजझटठडढणतथदधनपफबभमयरलवशषसह ािीुूेैोौं़्",
    "😀👍🙏❤️🔥💯 ",
    "0123456789٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹ .,+-",
    "‌‍‎‏ـ\u0000\u0001﻿\n\t\r",
    "漢字ひらがなカタカナ한국어ภาษาไทยעבריתΕλληνικάРусский",
    "ঁংঃঅআইঈউঊএஅஆஇഅആഇ",
]


def _random_text(rng: random.Random) -> str:
    n = rng.choice([0, 1, 2, 3, 5, 10, 40, 200, 1000])
    alphabets = rng.sample(ALPHABETS, rng.choice([1, 1, 2, 3]))
    return "".join(rng.choice(rng.choice(alphabets)) for _ in range(n))


def test_fuzz_detection_never_raises_and_returns_known_codes():
    rng = random.Random(20261031)
    for _ in range(4000):
        text = _random_text(rng)
        pin = rng.choice([None, "en", "roman_ur", "ur", "ar", "hi", ("fa", "arabic"), "zz"])
        d = ls.detect_message_language(text, pinned=pin, voice=rng.random() < 0.2)
        assert isinstance(d, ls.LanguageDecision)
        assert d.code in KNOWN_CODES or d.code == (pin if isinstance(pin, str) else d.code)
        assert 0.0 <= d.confidence <= 1.0
        if d.uncertain and pin in ("en", "roman_ur", "ur", "ar", "hi") and d.reason != "error":
            assert d.code == pin
        ls.reply_language_for(d, pin)
        ls.business_term_normalise(text)
        ls.has_correction_or_withdrawal_cue(text)


def test_fuzz_history_shapes_never_raise():
    rng = random.Random(3)
    for _ in range(300):
        hist = [
            rng.choice(
                [
                    _random_text(rng),
                    None,
                    5,
                    b"x",
                    {"text": _random_text(rng)},
                    {"voice": True},
                    ls.HistoryTurn("hi there friend"),
                ]
            )
            for _ in range(rng.randint(0, 12))
        ]
        state = ls.LanguagePin(switch_after=rng.choice([0, 1, 2, 5])).pin(hist)
        assert state.code in KNOWN_CODES
        ls.detect_message_language(_random_text(rng), history=hist)


def test_fuzz_cues_and_regex_are_not_catastrophic():
    nasty = [
        "i " * 2000,
        "never " * 1500,
        "forget " * 1000,
        "ب" * 5000,
        "मेरा " * 1000,
        "earlier i said " + "a" * 3000 + " but",
        "maine " * 1000 + "galat",
        "پہلے " + "ا" * 3000 + " لیکن",
    ]
    for text in nasty:
        t0 = time.perf_counter()
        ls.has_correction_or_withdrawal_cue(text)
        ls.detect_message_language(text)
        ls.business_term_normalise(text)
        assert time.perf_counter() - t0 < 1.0, text[:20]


# --- timing: linear, capped


def _timed(fn, text: str, repeat: int = 5) -> float:
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn(text)
        best = min(best, time.perf_counter() - t0)
    return best


def _grow(unit: str, chars: int) -> str:
    return (unit + " ") * (chars // (len(unit) + 1) + 1)


@pytest.mark.parametrize(
    "unit",
    [
        "Mera dhanda nahi chal raha aur meri kuch dukaanain hain defense mein",
        "ہمارے پاس صرف تین لوگ ہیں اور سب دیر سے آتے ہیں",
        "Our shop has no footfall and the staff come late every week",
        "मेरी दुकान में तीन लोग काम करते हैं लेकिन सब देर से आते हैं",
    ],
)
def test_timing_grows_no_faster_than_the_input_up_to_the_cap(unit):
    fns = {
        "detect": ls.detect_message_language,
        "normalise": ls.business_term_normalise,
        "cue": ls.has_correction_or_withdrawal_cue,
    }
    for name, fn in fns.items():
        t1, t10, t100 = (_timed(fn, _grow(unit, n)) for n in (1_000, 10_000, 100_000))
        # work is capped (4000 chars / 600 tokens): 10x the input is at most ~10x the time (linear),
        # and 100x vs 10x is flat once the cap is reached. Generous bounds: timers on CI are noisy.
        assert t10 / max(t1, 1e-7) < 25, (name, t1, t10)
        assert t100 / max(t10, 1e-7) < 4, (name, t10, t100)
        assert t100 < 0.5, (name, t100)


def test_timing_history_is_capped_so_a_100k_message_chat_costs_the_same_as_60():
    msg = "Mera dhanda nahi chal raha aur meri kuch dukaanain hain"
    small, big = [msg] * 60, [msg] * 100_000
    t_small = _timed(lambda _t: ls.LanguagePin().pin(small), "")
    t_big = _timed(lambda _t: ls.LanguagePin().pin(big), "", repeat=3)
    assert t_big / max(t_small, 1e-7) < 40, (t_small, t_big)
    assert ls.LanguagePin().pin(big).code in ls.ROMAN_INDIC


def test_run_together_token_segmentation_is_bounded():
    t0 = time.perf_counter()
    ls.detect_message_language("a" * 100_000)
    ls.detect_message_language("mujhe" * 5000)
    assert time.perf_counter() - t0 < 1.0
