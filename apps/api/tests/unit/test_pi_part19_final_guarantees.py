# ruff: noqa: E501  (the sentences are kept whole, in several scripts)
"""Spec v1.6 R-ASK-01 on the FINAL reply, sixth re-audit (B1 quotation smuggling, B2 narrow mandatory
content, B3 no silent disable). The question counter here is independent of the code under test: it does
not use part19's normaliser, placeholders or counters."""

import logging
import random
import re

import pytest

from app.modules.pi import constitution, part19

QUESTION_RUN = re.compile(r"[?؟？⁇⁈⁉;⸮፧][?؟？⁇⁈⁉;⸮፧!.…]*")
URL_RE = re.compile(r"https?://\S+")


def asked(text: str, embedded=()) -> int:
    """Questions put to the customer, counted without the code under test: a run of question marks is
    one question; links and the quotations known to sit inside a sentence are not counted."""
    for quote in embedded:
        text = text.replace(quote, "")
    return len(QUESTION_RUN.findall(URL_RE.sub("", text)))


def final(text: str, keep=None) -> str:
    return constitution.final_one_question(text, keep=keep)


# --- B1: quotations --------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        'Is it A? "Which city are you in?"',
        'Which shop? "Which city are you in?"',
        'Which shop? He asked "Which city are you in?"',
        'Which shop? He asked: "Which city are you in?".',
        "Which shop? “Which city are you in?”",
        "Which shop? «Which city are you in?»",
        'Which shop? "Which city?" "Which area?"',
    ],
)
def test_b1_a_quotation_that_is_a_sentence_or_ends_one_counts_as_a_question(text):
    out = final(text)
    assert asked(out) == 1, out
    assert (
        "Which shop" not in out and "Is it A" not in out
    )  # the last question survives, not the first


@pytest.mark.parametrize(
    "quote", ['"Which city are you in?"', "“Which city are you in?”", "«Which city are you in?»"]
)
def test_b1_the_words_inside_a_quotation_are_never_rewritten(quote):
    out = final(f"Is it A? Is it B? {quote}")
    assert quote in out and asked(out) == 1, out
    out = final(
        f"Noted. {quote} Which one?"
    )  # the quotation is a sentence: it gives way as a sentence
    assert asked(out) == 1 and out.rstrip().endswith("Which one?"), out


def test_b1_a_quotation_inside_a_sentence_is_still_left_alone():
    out = final('Noted "is it ready?" for later. Which shop? Which city?')
    assert '"is it ready?"' in out and asked(out, ['"is it ready?"']) == 1
    assert out.rstrip().endswith("Which city?")
    out = final('He said "why?", then left. Which city?')
    assert '"why?"' in out and asked(out, ['"why?"']) == 1


@pytest.mark.parametrize(
    "text",
    [
        'The tube is 5" long and 6" wide. Which one? Or which other?',
        'It is 5" tall. Is it A? Is it 6" wide?',
        'Size 5". Which one? Size 6". Which other?',
        'Roll 5" or 6" wide. Which one? Or "this" one?',
    ],
)
def test_b1_inch_marks_open_no_quotation_and_hide_no_question(text):
    out = final(text)
    assert asked(out, ['"this"']) == 1, out
    for inch in ('5"', '6"'):
        if inch in text:
            assert inch in out, out


# --- B2: narrow mandatory content --------------------------------------------------------------------
ORDINARY = [
    "Kya aap ka order nahi aaya?",
    "کیا آپ کی ادائیگی نہیں ہوئی؟",
    "Do you run a bot business?",
    "Kya aap ka AI chatbot ka business hai?",
    "Main AI chatbot business mein hoon, kya aap AI chahte hain?",
    "I am building an AI product, what should I price it?",
    "Which doctor has 1122 patients?",
    "Is the hospital open at 1122 Main Street?",
    "Is there no need for a refund?",
    "Without a card, how do customers pay?",
    "Kya aap ko card ki zaroorat hai?",
    "Mat batao, kya hua tha?",
]


@pytest.mark.parametrize("sentence", ORDINARY)
def test_b2_an_ordinary_question_that_only_looks_mandatory_stays_a_question(sentence):
    assert not part19.is_mandatory(sentence, [])
    out = final(f"{sentence} Which city?")
    assert out.rstrip().endswith("Which city?") and asked(out) == 1, out
    assert sentence[:-1] not in out  # it gave way as a question: it was not kept as a statement
    only = part19.statement_only(f"{sentence} Noted.")
    assert only == "Noted." and asked(only) == 0, only


@pytest.mark.parametrize("sentence", ORDINARY)
def test_b2_an_ordinary_question_alone_or_last_is_left_exactly_as_it_is(sentence):
    assert final(sentence) == sentence
    assert final(f"Noted. {sentence}") == f"Noted. {sentence}"


@pytest.mark.parametrize(
    "sentence",
    [
        "I am pi, an AI from Workzap, what does your business do?",
        "I'm an AI, not a person, what is your business?",
        "Main pi hoon, Workzap ka AI, aap ka business kya hai?",
        "میں pi ہوں، Workzap کا اے آئی، آپ کا کاروبار کیا ہے؟",
        "मैं pi हूँ, Workzap का आर्टिफिशियल इंटेलिजेंस, आपका व्यवसाय क्या है?",
        "I never ask for your CNIC or a bank account number, is that clear?",
        "Please never share your ID card or credit card details with me, okay?",
        "Main kabhi aap ka credit card ya OTP nahi maangta, theek hai?",
        "ہم کبھی آپ کا پاس ورڈ یا شناختی کارڈ نمبر نہیں مانگتے، ٹھیک ہے؟",
        "मैं कभी आपका डेबिट कार्ड या ओटीपी नहीं मांगता, ठीक है?",
        "Please call the police or an ambulance on 1122 now, is anyone hurt?",
        "Foran police ko call karein aur hospital jayen, kya koi zakhmi hai?",
        "فوراً پولیس کو کال کریں اور ہسپتال جائیں، کیا کوئی زخمی ہے؟",
        "तुरंत पुलिस को कॉल करें और अस्पताल जाएं, क्या कोई घायल है?",
        "اتصل بالشرطة أو بالإسعاف فورًا، هل هناك مصاب؟",
    ],
)
def test_b2_the_true_mandatory_questions_are_still_protected(sentence):
    assert part19.is_mandatory(sentence, [])
    out = final(f"{sentence} Which city?")
    assert f"{sentence[:-1]}." in out and out.rstrip().endswith("Which city?"), out
    assert asked(out) == 1
    only = part19.statement_only(f"{sentence} Noted.")
    assert f"{sentence[:-1]}." in only and asked(only) == 0, only


# --- never zero ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        "Which shop? Thanks for waiting.",
        "Is it A? Thanks. Is it B? Bye.",
        "Which shop?\n\nThanks for waiting.",
        "*Which shop?* Thanks.",
        "Which shop? 😊 Thanks!",
    ],
)
def test_a_reply_with_a_question_and_no_mandatory_sentence_keeps_exactly_one(text):
    out = final(text)
    assert asked(out) == 1 and out.rstrip().endswith("?"), out


def test_a_single_mandatory_question_that_is_not_last_is_kept_and_moved_not_removed():
    out = final("I am pi, an AI from Workzap, what do you do? Thanks.")
    assert asked(out) == 1 and "what do you do" in out, out


def test_when_every_question_is_mandatory_they_all_become_statements():
    # the one case with no question left: the mandatory text wins over the cap (reported as a limit)
    out = final(
        "I am pi, an AI from Workzap, what do you do? I never ask for a card number, is that clear?"
    )
    assert asked(out) == 0
    assert "what do you do." in out and "is that clear." in out


def test_a_mandatory_question_last_still_wins_over_an_earlier_ordinary_question():
    out = final("Which shop? I am pi, an AI from Workzap, what does your business do?")
    assert "I am pi, an AI from Workzap, what does your business do." in out
    assert out.rstrip().endswith("Which shop?") and asked(out) == 1


# --- B3: the check never disables itself silently ------------------------------------------------------
def test_b3_an_error_is_logged_with_its_type_only_and_the_cap_still_applies(monkeypatch, caplog):
    def boom(_keep):
        raise RuntimeError("secret customer words must not be logged")

    monkeypatch.setattr(part19, "keep_canon", boom)
    text = "Which shop? Is it A? Check https://x.com/a?b=1 and then which one?"
    with caplog.at_level(logging.WARNING, logger="app.modules.pi.part19"):
        out = final(text)
    assert asked(out) <= 1, out
    assert "https://x.com/a?b=1" in out  # a link is never rewritten, even in the fallback
    for word in ("Which shop", "Is it A", "which one"):
        assert word in out  # nothing dropped
    records = [r for r in caplog.records if r.name == "app.modules.pi.part19"]
    assert records and records[0].levelno == logging.WARNING
    assert records[0].error_type == "RuntimeError"
    assert "secret" not in caplog.text


def test_b3_even_when_the_fallback_itself_fails_the_reply_is_capped_and_sent(monkeypatch, caplog):
    def boom(*_args, **_kwargs):
        raise ValueError("another secret")

    monkeypatch.setattr(part19, "protect_urls", boom)
    with caplog.at_level(logging.WARNING, logger="app.modules.pi.part19"):
        out = final("Is it A? Which one? And you?")
    assert asked(out) == 1 and "Is it A" in out and "Which one" in out, out
    assert len([r for r in caplog.records if r.name == "app.modules.pi.part19"]) >= 2
    assert "secret" not in caplog.text


def test_b3_a_reply_that_cannot_be_checked_is_never_returned_unchanged_with_two_questions(
    monkeypatch,
):
    monkeypatch.setattr(constitution, "_one_question_last", lambda *_a, **_k: 1 / 0)
    out = final("Is it A? Is it B?")
    assert asked(out) == 1


# --- limits and added marks ----------------------------------------------------------------------------
@pytest.mark.parametrize("mark", [";", "⸮", "፧", "？", "⁇"])
def test_other_question_marks_that_can_be_mapped_safely_are_counted(mark):
    out = final(f"Is it A{mark} Which one?")
    assert asked(out) == 1, out


def test_known_limits_are_documented_not_hidden():
    # not counted: the Armenian question mark sits inside the word, an ASCII ";" is a semicolon, and a
    # question with no mark at all (Devanagari or any other script) cannot be told from a statement
    for text in ("ինչո՞ւ ոչ", "Is it A; which one", "आप कौन हैं"):
        assert part19.question_count(part19.normalise_question_marks(text)) == 0


# --- property: random texts, independent counter -------------------------------------------------------
PLAIN = [
    "Is it A",
    "Which one",
    "What next",
    "Shall we go",
    "Kya hua",
    "ما هو عملك",
    "आप कौन हैं",
    "Was ist das",
]
KEEP_SENTENCES = ["Your reference is A1", "Is that the right branch", "Shall I hold the order"]
MARKS = ["?", "؟", "?!", "?.", "?...", "?…", "？", "⁇", "?!?", "??", ";", "፧"]
GLUE = ["", " ", "​", "⁠", "﻿", "⁦", "⁩", "‌", "‍", "‏", "😊", "⭐", "⏰", "⃣", "〰", "\U000e0020", "✅"]
CLOSE = ["", ")", "*", "'", "»", "”", "_"]
JOIN = ["", " ", "\n", ". ", " - "]
MANDATORY_TEXT = [
    "I am pi, an AI from Workzap, what does your business do",
    "I never ask for a card number or a password, is that clear",
    "Please call the emergency number 1122 and an ambulance now, is anyone hurt",
]


def build(rng: random.Random):
    pieces: list[str] = []
    embedded: list[str] = []
    keeps: list[str] = []
    must = rng.sample(MANDATORY_TEXT, rng.randint(0, 3))
    for _ in range(rng.randint(2, 7)):
        kind = rng.choice(
            [
                "plain",
                "plain",
                "plain",
                "over",
                "whole",
                "embedded",
                "url",
                "decimal",
                "abbr",
                "keep",
            ]
        )
        mark = rng.choice(MARKS) + rng.choice(CLOSE) + rng.choice(GLUE)
        if kind == "plain":
            pieces.append(rng.choice(PLAIN) + mark)
        elif kind == "over":
            pieces.append(rng.choice(ORDINARY[:-1]).rstrip("?؟") + mark)
        elif kind == "whole":
            # a whole-sentence quotation: on a line of its own (words after it on the same line would
            # make it a quotation inside a sentence, which the rule leaves alone)
            pieces.append(f'\n"{rng.choice(PLAIN)}?"' + rng.choice(GLUE) + "\n")
        elif kind == "embedded":
            quote = f'"{rng.choice(PLAIN)}?"'
            phrase = f"He noted {quote} for later."
            embedded.append(
                phrase
            )  # the whole phrase: the same words may also stand alone elsewhere
            pieces.append(phrase)
        elif kind == "url":
            pieces.append(f"See https://x.com/p?id={rng.randint(1, 99)} now.")
        elif kind == "decimal":
            pieces.append("The fee is 3.5 percent.")
        elif kind == "abbr":
            pieces.append("See e.g. Rs. 500 here.")
        else:
            stem = rng.choice(KEEP_SENTENCES)
            keeps.append(stem + "?")
            pieces.append(stem + mark)
    for sentence in must:
        pieces.insert(
            rng.randint(0, len(pieces)),
            sentence + rng.choice(MARKS) + rng.choice(CLOSE) + rng.choice(GLUE),
        )
    text = ""
    for piece in pieces:
        text += piece + rng.choice(JOIN)
    return text, must, keeps, embedded


def present(stem: str, out: str) -> bool:
    return stem.casefold() in re.sub(r"\s+", " ", out).casefold()


@pytest.mark.parametrize("seed", range(8))
def test_property_one_question_no_mandatory_or_fixed_line_lost_and_never_zero(seed):
    rng = random.Random(61030 + seed)
    for _ in range(100):
        text, must, keeps, embedded = build(rng)
        out = final(text, keep=keeps)
        assert asked(out, embedded) <= 1, (text, out)
        for stem in [*must, *(k[:-1] for k in keeps)]:
            assert present(stem, out), (stem, text, out)
        if asked(text, embedded) >= 1 and not must and not keeps:
            assert asked(out, embedded) == 1, ("never zero", text, out)
        only = part19.statement_only(text)
        assert asked(only, embedded) == 0, (text, only)
        for stem in must:
            assert present(stem, only), (stem, text, only)
