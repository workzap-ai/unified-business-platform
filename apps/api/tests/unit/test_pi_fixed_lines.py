"""The fixed lines in the eight priority languages (owner order: en, roman_ur, ur, ar, hi, fr, fa,
es): the safe fallback is never English for a person writing one of them."""

import re

import pytest

from app.modules.pi import decisions, fixed_lines, safety, solution_ask
from app.modules.pi.constitution import opening_line

SAMPLES = {
    "en": "I need help with my shop, the stock keeps running out",
    "roman_ur": "Mera maal khatam ho jata hai aur staff late aata hai",
    "ur": "میرا مال ختم ہو جاتا ہے اور عملہ دیر سے آتا ہے",
    "ar": "أحتاج مساعدة في متجري والمخزون ينفد دائما",
    "hi": "मेरी दुकान में माल बार-बार खत्म हो जाता है",
    "fr": "J'ai un problème avec mon magasin, le stock est toujours épuisé et les clients",
    "fa": "من در مغازه‌ام مشکل دارم و موجودی همیشه تمام می‌شود",
    "es": "Tengo un problema con mi tienda, el stock siempre se acaba y los clientes esperan",
}


@pytest.mark.parametrize("lang", fixed_lines.PRIORITY)
def test_every_priority_language_has_every_line(lang: str) -> None:
    for key, table in fixed_lines.LINES.items():
        assert table.get(lang), (lang, key)


@pytest.mark.parametrize("lang", [x for x in fixed_lines.PRIORITY if x not in ("en", "roman_ur")])
def test_a_priority_language_line_is_not_the_english_one(lang: str) -> None:
    for key, table in fixed_lines.LINES.items():
        assert table[lang] != table["en"], (lang, key)


# Urdu and Hindi script are answered in Roman Urdu (the chat's reply language), so one chat never
# mixes scripts; only safety lines keep the person's own script (script=True).
FIXED_OF = {"ur": "roman_ur", "hi": "roman_ur"}


@pytest.mark.parametrize("lang", list(SAMPLES))
def test_the_language_of_a_message_picks_its_fixed_language(lang: str) -> None:
    expected = FIXED_OF.get(lang, lang)
    assert (
        fixed_lines.code_of_text(SAMPLES[lang], "en" if lang != "roman_ur" else "roman_ur")
        == expected
    )


@pytest.mark.parametrize("lang", ["ur", "hi"])
def test_safety_lines_keep_the_script_the_person_wrote(lang: str) -> None:
    assert fixed_lines.code_of_text(SAMPLES[lang], "roman_ur", script=True) == lang
    context = {"reply_language": "roman_ur", "latest_customer_message": SAMPLES[lang]}
    assert fixed_lines.code(context) == "roman_ur"
    assert fixed_lines.code(context, script=True) == lang


@pytest.mark.parametrize("lang", ["ur", "hi"])
def test_a_hindi_or_urdu_script_chat_gets_roman_urdu_fixed_lines(lang: str) -> None:
    context = {"reply_language": "roman_ur", "latest_customer_message": SAMPLES[lang]}
    roman = fixed_lines.LINES
    assert opening_line(context) == roman["opening"]["roman_ur"]
    assert solution_ask.offer_line("roman_ur", context) == roman["offer"]["roman_ur"]
    assert decisions.cost_answer("roman_ur", context) == roman["cost"]["roman_ur"]
    text, _ = safety.pii_notice(
        [safety.Pii.CARD], [], "roman_ur", fixed_lines.code_of_text(SAMPLES[lang], "roman_ur")
    )
    assert text == roman["card"]["roman_ur"]
    for key in ("opening", "offer", "cost", "card", "id", "ai_answer"):
        assert not re.search(r"[ऀ-ॿ؀-ۿ]", roman[key]["roman_ur"]), key


@pytest.mark.parametrize("lang", list(SAMPLES))
def test_the_opening_the_offer_and_the_cost_answer_follow_the_message(lang: str) -> None:
    base = (
        "roman_ur" if lang in ("roman_ur", "ur", "hi") else lang if lang in ("en", "ar") else "en"
    )
    expected = FIXED_OF.get(lang, lang)
    context = {"reply_language": base, "latest_customer_message": SAMPLES[lang]}
    assert opening_line(context) == fixed_lines.LINES["opening"][expected]
    assert solution_ask.offer_line(base, context) == fixed_lines.LINES["offer"][expected]
    assert decisions.cost_answer(base, context) == fixed_lines.LINES["cost"][expected]


def test_table_language_folds_urdu_and_hindi_and_falls_back_to_english() -> None:
    have = {"en": 1, "roman_ur": 2, "ar": 3}
    pick = fixed_lines.table_language
    assert [pick(x, have) for x in ("en", "roman_ur", "ur", "hi", "ar", None, "fr", "fa")] == [
        "en", "roman_ur", "roman_ur", "roman_ur", "ar", "en", "en", "en",
    ]  # fmt: skip
    assert pick("fa", have, persian=True) == "roman_ur"
    assert pick("ar-SA", have) == "ar"


@pytest.mark.parametrize("lang", ["fr", "fa", "es", "ur"])
def test_a_language_asked_for_by_name_gets_its_fixed_lines(lang: str) -> None:
    name = {v: k for k, v in fixed_lines.CODES.items()}[lang]
    context = {"reply_language_other": name, "latest_customer_message": "ok"}
    assert fixed_lines.code(context) == lang


@pytest.mark.parametrize("lang", ["ur", "fr", "fa", "es"])
def test_the_emergency_answer_is_in_the_language_with_the_local_numbers(lang: str) -> None:
    for kind in (
        safety.Emergency.FIRE,
        safety.Emergency.MEDICAL,
        safety.Emergency.VIOLENCE,
        safety.Emergency.GENERIC,
    ):
        known = safety.emergency_reply(kind, "PK", "en", lang)
        assert not re.search(r"I can't help", known), (lang, kind)
        assert "{" not in known
        unknown = safety.emergency_reply(kind, None, "en", lang)
        assert "your local emergency number" not in unknown and "Pakistan 15" in unknown
        assert "{" not in unknown


def test_an_emergency_in_english_is_unchanged() -> None:
    assert safety.emergency_reply(safety.Emergency.GENERIC, "PK", "en") == (
        "I can't help with emergencies. Please call 15 now."
    )


@pytest.mark.parametrize("lang", ["ur", "fr", "fa", "es", "ar"])
def test_the_card_and_id_reminders_follow_the_language(lang: str) -> None:
    text, told = safety.pii_notice([safety.Pii.CARD, safety.Pii.ID], [], "en", lang)
    assert fixed_lines.LINES["card"][lang] in text and fixed_lines.LINES["id"][lang] in text
    assert told == ["card", "id"]
    again, _ = safety.pii_notice([safety.Pii.CARD], told, "en", lang)
    assert again == ""  # one reminder per kind per conversation


def test_the_other_reminders_are_unchanged() -> None:
    text, _ = safety.pii_notice([safety.Pii.SECRET], [], "en", "fr")
    assert text == safety.PII_TEXT["en"][safety.Pii.SECRET]


GENDERED = {
    "hi": re.compile(r"सकता|सकती|रहा |रही |गया |गयी |गई "),
    "ur": re.compile(r"سکتا|سکتی|رہا |رہی |گیا |گئی "),
}
WRONG_QUOTE = {"hi": re.compile(r"कोट(?!ेशन)"), "ur": re.compile(r"کوٹ(?!یشن)")}


def every_line(lang: str) -> list[str]:
    lines = [table[lang] for table in fixed_lines.LINES.values()]
    return lines + list(fixed_lines.EMERGENCY.get(lang, {}).values())


@pytest.mark.parametrize("lang", ["ur"])
def test_no_hindi_or_urdu_fixed_line_has_a_gendered_first_person_form(lang: str) -> None:
    """R-GEN-01: pi has no gender, so no 'main ... sakta/sakti' style verb."""
    for text in every_line(lang):
        assert not GENDERED[lang].search(text), text


@pytest.mark.parametrize("lang", ["ur"])
def test_a_quote_is_a_quotation_not_a_coat(lang: str) -> None:
    for text in every_line(lang):
        assert not WRONG_QUOTE[lang].search(text), text


@pytest.mark.parametrize("lang", ["fr", "es"])
def test_no_french_or_spanish_line_is_gendered_by_agreement(lang: str) -> None:
    said = re.compile(r"\b(?:je suis|j'ai été|soy|estoy)\s+(?!pi\b|une\b|un\b|una\b)\w+", re.I)
    for text in every_line(lang):
        assert not said.search(text), text


def test_hindi_has_no_fixed_texts_but_keeps_its_emergency_line() -> None:
    # the owner removed Hindi from pi's texts (2026-10-28): understood, answered in Roman Urdu; an
    # emergency is still told in Hindi (it is about someone's safety)
    from app.modules.pi import fixed_lines

    assert "hi" not in fixed_lines.PRIORITY
    for table in fixed_lines.LINES.values():
        assert "hi" not in table
    assert "hi" in fixed_lines.EMERGENCY and "hi" in fixed_lines.LOCAL_NUMBER
    assert fixed_lines.code_of_text("मेरी दुकान में माल खत्म हो जाता है") == "roman_ur"
    assert fixed_lines.code_of_text("आग लगी है", script=True) == "hi"
