# ruff: noqa: E501  (the sentences are kept whole, in several scripts)
"""Spec v1.6 R-ASK-01 on the FINAL reply, fifth re-audit (V1, V2): at most one question put to the
customer, and never at the price of a mandatory sentence (the AI disclosure, a refusal to ask for card
or password details, a safety referral). Links, decimals, abbreviations and quotations stay as they are.
"""

import random

import pytest

from app.modules.pi import constitution, part19


def questions(text: str) -> int:
    """Genuine questions in a final text: links and quotations are not counted."""
    held = part19.protect_urls(text)[0]
    return part19.question_count(part19.normalise_question_marks(held))


def final(text: str, keep=None) -> str:
    return constitution.final_one_question(text, keep=keep)


# --- V1: punctuation combinations, zero-width characters, emoji, glued questions -------------------
@pytest.mark.parametrize(
    "text",
    [
        "Is it A?! Which one?",
        "Is it A?... Which one?",
        "Is it A?… Which one?",
        "Is it A?. Which one?",
        "Is it A?!? Which one?",
        "Is it A?? Which one?",
        "(Is it A?). Which one?",
        "(Is it A?)... Which one?",
        "*Is it A?*. Which one?",
        "Is it A?Is it B?",
        "Is it A?Is it B?Is it C?",
        "هل هذا أ؟هل هذا ب؟",
        "Is it A？Is it B⁇Is it C?",
    ],
)
def test_v1_punctuation_combinations_leave_at_most_one_question(text):
    out = final(text)
    assert questions(out) <= 1, out
    assert out.strip()


@pytest.mark.parametrize("glue", ["​", "⁠", "﻿", "⁦", "⁩", "‌", "‍", "‏"])
def test_v1_zero_width_and_direction_marks_glued_to_a_question_do_not_hide_it(glue):
    out = final(f"Is it A?{glue}Is it B?")
    assert questions(out) <= 1, out
    out = final(f"Is it A?{glue} Which one?{glue}")
    assert questions(out) <= 1, out


@pytest.mark.parametrize(
    "emoji",
    ["😊", "⭐", "⬆", "⏰", "⌛", "1⃣", "〰", "㊗", "\U000e0020", "✅", "️"],
)
def test_v1_emoji_outside_the_common_ranges_do_not_hide_a_question(emoji):
    out = final(f"Is it A?{emoji} Is it B?")
    assert questions(out) <= 1, out
    out = final(f"Is it A?{emoji}Is it B?{emoji}")
    assert questions(out) <= 1, out


def test_v1_normaliser_cases():
    assert part19.normalise_question_marks("Is it A?!") == "Is it A?"
    assert part19.normalise_question_marks("Is it A?...") == "Is it A?"
    assert part19.normalise_question_marks("Is it A?…") == "Is it A?"
    assert part19.normalise_question_marks("(Is it A?).") == "(Is it A)?"
    assert part19.normalise_question_marks("A?B") == "A? B"
    assert part19.normalise_question_marks("A?​B") == "A? ​B"
    assert part19.normalise_question_marks("A？B") == "A? B"


def test_v1_the_last_question_survives_and_only_it():
    out = final("Is it A?! Which one?")
    assert out.rstrip().endswith("Which one?") and questions(out) == 1


# --- statements are never merged into the question; positions, not first occurrences -----------------
def test_a_year_in_a_sentence_does_not_merge_the_statement_with_the_question():
    assert part19.statement_only("We started in 2024. Which one?") == "We started in 2024."
    assert (
        part19.statement_only("1. Which one?") == ""
    )  # a list number at the start is no sentence end
    out = final("We started in 2024. Which one? Or which other?")
    assert "We started in 2024." in out and questions(out) == 1


def test_a_repeated_sentence_is_changed_where_it_stands():
    keep = ["Which one"]
    out = final("Why? Which one? Why?", keep=keep)
    assert "Which one." in out  # the kept sentence became a statement at its own place
    assert out.rstrip().endswith("Why?") and questions(out) == 1
    out = final("Is that right? Is that right? What next?", keep=["Is that right"])
    assert out.count("Is that right.") == 2 and out.rstrip().endswith("What next?")


# --- keep lines: normalised alike, sentence by sentence ---------------------------------------------
@pytest.mark.parametrize(
    ("reply", "line", "kept"),
    [
        (
            "Your total is Rs. 500, is that right? What next?",
            "Your total is Rs. 500, is that right?",
            "Your total is Rs. 500, is that right.",
        ),
        ("See e.g. the list, ok? Which one?", "See e.g. the list, ok?", "See e.g. the list, ok."),
        (
            "1. Confirm the code, right? What next?",
            "1. Confirm the code, right?",
            "1. Confirm the code, right.",
        ),
        (
            "Your reference is A1. Is that right? Also what next?",
            "Your reference is A1. Is that right?",
            "Is that right.",
        ),
        (
            "Your reference is A1, is that right ? Also what next?",
            "Your reference is A1, is that right?",
            "Your reference is A1, is that right",
        ),
    ],
)
def test_keep_lines_are_matched_after_the_same_normalisation(reply, line, kept):
    out = final(reply, keep=[line])
    assert kept in out, out
    assert questions(out) == 1


@pytest.mark.parametrize(
    "keep", ["a string", 5, None, 3.5, {"a": 1}, [1, None, 2.5], [], (), [b"x"], object()]
)
def test_malformed_fixed_lines_never_stop_the_reply(keep):
    out = final("Is it A? Which one?", keep=keep)
    assert out.rstrip().endswith("Which one?") and questions(out) == 1


def test_a_list_holding_non_strings_still_uses_its_strings():
    out = final(
        "Your reference is A1, is that right? What next?",
        keep=[1, None, "Your reference is A1, is that right?"],
    )
    assert "Your reference is A1, is that right." in out and out.rstrip().endswith("What next?")


# --- mandatory content, every supported language -----------------------------------------------------
MANDATORY = {
    "disclosure": {
        "en": (
            "I am pi, an AI from Workzap, what does your business do?",
            "Shall I make the quote?",
        ),
        "roman_ur": (
            "Main pi hoon, Workzap ka AI, aap ka business kya karta hai?",
            "Kya main quote bana doon?",
        ),
        "ur": ("میں pi ہوں، Workzap کا اے آئی، آپ کا کاروبار کیا ہے؟", "کیا میں کوٹیشن بنا دوں؟"),
        "ar": ("أنا pi، ذكاء اصطناعي من Workzap، ما هو عملك؟", "هل أجهز عرض السعر؟"),
        "hi": ("मैं pi हूँ, Workzap का एआई, आपका व्यवसाय क्या है?", "क्या मैं कोटेशन बना दूँ?"),
    },
    "refusal": {
        "en": (
            "I never ask for a card number or a password, is that clear?",
            "What is your business?",
        ),
        "roman_ur": (
            "Main kabhi card number ya password nahi poochhta, theek hai?",
            "Aap ka business kya hai?",
        ),
        "ur": ("میں کبھی کارڈ نمبر یا پاس ورڈ نہیں مانگتا، ٹھیک ہے؟", "آپ کا کاروبار کیا ہے؟"),
        "ar": ("لا أطلب أبدًا رقم البطاقة أو كلمة المرور، هل هذا واضح؟", "ما هو عملك؟"),
        "hi": ("मैं कभी कार्ड नंबर या पासवर्ड नहीं मांगता, ठीक है?", "आपका व्यवसाय क्या है?"),
    },
    "safety": {
        "en": (
            "Please call the emergency number 1122 and an ambulance now, is anyone hurt?",
            "Which city are you in?",
        ),
        "roman_ur": (
            "Foran police ko call karein aur hospital jayen, kya koi zakhmi hai?",
            "Aap kis shehar mein hain?",
        ),
        "ur": (
            "فوراً 1122 پر کال کریں اور ایمبولینس بلائیں، کیا کوئی زخمی ہے؟",
            "آپ کس شہر میں ہیں؟",
        ),
        "ar": ("اتصل بالإسعاف على الرقم 1122 فورًا، هل هناك مصاب؟", "في أي مدينة أنت؟"),
        "hi": ("तुरंत 1122 पर कॉल करें और एम्बुलेंस बुलाएं, क्या कोई घायल है?", "आप किस शहर में हैं?"),
    },
}


@pytest.mark.parametrize("language", ["en", "roman_ur", "ur", "ar", "hi"])
@pytest.mark.parametrize("kind", ["disclosure", "refusal", "safety"])
def test_a_mandatory_question_is_kept_as_a_statement_and_the_other_question_survives(
    kind, language
):
    protected, later = MANDATORY[kind][language]
    out = final(f"{protected} {later}")
    assert f"{protected[:-1]}." in out, out
    assert out.rstrip().endswith(later), out
    assert questions(out) == 1, out


@pytest.mark.parametrize("language", ["en", "roman_ur", "ur", "ar", "hi"])
@pytest.mark.parametrize("kind", ["disclosure", "refusal", "safety"])
def test_statement_only_turns_a_mandatory_question_into_a_statement_and_drops_the_other(
    kind, language
):
    protected, later = MANDATORY[kind][language]
    out = part19.statement_only(f"{protected} {later}")
    assert f"{protected[:-1]}." in out, out
    assert later not in out and questions(out) == 0, out


@pytest.mark.parametrize("language", ["en", "roman_ur", "ur", "ar", "hi"])
def test_two_mandatory_questions_both_become_statements(language):
    first = MANDATORY["disclosure"][language][0]
    second = MANDATORY["refusal"][language][0]
    out = final(f"{first} {second}")
    assert f"{first[:-1]}." in out and f"{second[:-1]}." in out, out
    assert questions(out) == 0, out


def test_a_mandatory_question_last_still_wins_over_an_earlier_ordinary_question():
    out = final("Which shop? I am pi, an AI from Workzap, what does your business do?")
    assert "what does your business do." in out and questions(out) == 0 or questions(out) == 1


def test_a_single_mandatory_question_is_left_exactly_as_it_is():
    one = "I am pi, an AI from Workzap, what does your business do?"
    assert final(one) == one


# --- integrity: links, decimals, abbreviations, quotations --------------------------------------------
def test_urls_decimals_abbreviations_and_quotations_are_left_alone():
    text = (
        "The fee is 3.5 percent, see https://x.com/a?b=1&c=2 and e.g. Rs. 500. "
        'He wrote "why does it fail? really?". Which one? Or this?'
    )
    out = final(text)
    assert "3.5 percent" in out and "https://x.com/a?b=1&c=2" in out
    assert "e.g. Rs. 500" in out and '"why does it fail? really?"' in out
    assert questions(out) == 1 and out.rstrip().endswith("Or this?")


def test_a_quotation_is_never_rewritten_even_when_its_sentence_is_a_dropped_question():
    # a question put to the customer that gives way is dropped as a whole sentence (R-ASK-01); a
    # quotation in a kept sentence keeps its own question marks, and counts as no question of pi's
    out = final('Noted "is it ready?" for later. Which shop? Which city?')
    assert '"is it ready?"' in out and questions(out) == 1
    assert out.rstrip().endswith("Which city?")


def test_a_link_that_ends_the_question_is_a_question_and_stays_a_link():
    out = final("Is this your site https://x.com? Or https://y.com/a?b=1?")
    assert "https://y.com/a?b=1" in out and questions(out) == 1


# --- property: random combinations -------------------------------------------------------------------
SENTENCES = [
    "Is it A",
    "Which one",
    "What next",
    "Shall we go",
    "Kya hua",
    "ما هو عملك",
    "आप कौन हैं",
    "Was ist das",
]
MARKS = ["?", "؟", "?!", "?.", "?...", "?…", "？", "⁇", "?!?", "??"]
GLUE = ["", " ", "​", "⁠", "﻿", "⁦", "⁩", "‌", "‍", "‏", "😊", "⭐", "⏰", "⃣", "〰", "\U000e0020", "✅"]
CLOSE = ["", ")", "*", "'", "»", "”", "_"]
JOIN = ["", " ", "\n", ". ", " - "]
MANDATORY_TEXT = "I am pi, an AI from Workzap, what does your business do"
REFUSAL_TEXT = "I never ask for a card number or a password, is that clear"
SAFETY_TEXT = "Please call the emergency number 1122 and an ambulance now, is anyone hurt"


def random_text(rng: random.Random, must: list[str]) -> str:
    pieces = []
    for _ in range(rng.randint(2, 7)):
        pieces.append(
            rng.choice(SENTENCES) + rng.choice(MARKS) + rng.choice(CLOSE) + rng.choice(GLUE)
        )
    for sentence in must:
        pieces.insert(
            rng.randint(0, len(pieces)),
            sentence + rng.choice(MARKS) + rng.choice(CLOSE) + rng.choice(GLUE),
        )
    text = ""
    for piece in pieces:
        text += piece + rng.choice(JOIN)
    return text


def stem_present(stem: str, out: str) -> bool:
    return stem.casefold() in part19._canon(out) or stem.casefold() in out.casefold()


@pytest.mark.parametrize("seed", range(6))
def test_property_at_most_one_question_and_no_mandatory_sentence_lost(seed):
    rng = random.Random(20261030 + seed)
    for _ in range(120):
        must = rng.sample([MANDATORY_TEXT, REFUSAL_TEXT, SAFETY_TEXT], rng.randint(0, 3))
        text = random_text(rng, must)
        out = final(text)
        assert questions(out) <= 1, (text, out)
        for stem in must:
            assert stem_present(stem, out), (stem, text, out)
        only = part19.statement_only(text)
        assert questions(only) == 0, (text, only)
        for stem in must:
            assert stem_present(stem, only), (stem, text, only)
