"""Follow-ups, decisions, buttons, meetings and deal nudges in every language pi has a table for:
Roman Urdu for Roman Urdu, Urdu, Hindi (and, for follow-ups, Persian) chats, Arabic for Arabic,
English for the rest. One script per chat; Meta template names never change."""

import re
from types import SimpleNamespace

import pytest

from app.modules.pi import brain_followups, buttons, decisions, followup_policy, map_share, safety
from app.modules.pi.language import other_script
from app.modules.pi_saas import deal_followups, meetings

ARABIC = re.compile(r"[؀-ۿ]")
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
ROMAN_CHATS = ("roman_ur", "ur", "hi")


# --- 2. follow-ups and reminders ----------------------------------------------------------------


@pytest.mark.parametrize("kind", list(followup_policy.MESSAGES))
def test_every_followup_kind_has_english_roman_urdu_and_arabic(kind: str) -> None:
    assert {"en", "roman_ur", "ar"} <= set(followup_policy.MESSAGES[kind])


@pytest.mark.parametrize("language", [*ROMAN_CHATS, "fa"])
@pytest.mark.parametrize("kind", list(followup_policy.MESSAGES))
def test_urdu_hindi_and_persian_chats_get_the_roman_urdu_followup(kind: str, language: str) -> None:
    said = followup_policy.text_for(kind, language, n=3, when="Fri 10:00")
    assert said == followup_policy.text_for(kind, "roman_ur", n=3, when="Fri 10:00")
    assert not ARABIC.search(said) and not DEVANAGARI.search(said)


@pytest.mark.parametrize("kind", list(followup_policy.MESSAGES))
def test_an_arabic_chat_gets_arabic_followups(kind: str) -> None:
    said = followup_policy.text_for(kind, "ar", n=3, when="Fri 10:00")
    assert ARABIC.search(said), kind
    assert "{" not in said
    if kind in ("paused", "kickoff_24h", "kickoff_1h"):
        assert ("3" in said) or ("Fri 10:00" in said)
    assert said.count("؟") <= 1


@pytest.mark.parametrize("language", [None, "en", "fr", "es", "tr", "zh"])
def test_every_other_language_keeps_the_english_fallback(language: str | None) -> None:
    for kind in followup_policy.MESSAGES:
        assert followup_policy.text_for(kind, language, n=2, when="x") == (
            followup_policy.MESSAGES[kind]["en"].format(n=2, when="x")
        )


def test_no_followup_pressures_in_any_language() -> None:
    for table in followup_policy.MESSAGES.values():
        for said in table.values():
            assert not any(word in said.lower() for word in followup_policy.PRESSURE)


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("roman_ur", "roman_ur"),
        ("ur", "roman_ur"),
        ("hi", "roman_ur"),
        ("fa", "roman_ur"),
        ("ar", "ar"),
        ("en", "en"),
        ("fr", "en"),
        (None, "en"),
    ],
)
def test_the_followup_language_of_a_conversation(language: str | None, expected: str) -> None:
    assert brain_followups.language_of(SimpleNamespace(language=language)) == expected  # type: ignore[arg-type]


def test_the_meta_template_names_are_not_part_of_these_tables() -> None:
    """The approved template names live in the workspace's whatsapp_config, never in the code."""
    for table in followup_policy.MESSAGES.values():
        assert not any("template" in said.lower() for said in table.values())


def test_the_map_followup_in_a_hindi_or_urdu_chat_is_roman_urdu() -> None:
    for language in ("ur", "hi"):
        assert map_share.followup_text(language) == map_share.FOLLOWUP["roman_ur"]
        assert map_share.buttons(language) == list(map_share.BUTTONS["roman_ur"])
    assert map_share.followup_text("ar") == map_share.FOLLOWUP["ar"]
    assert map_share.followup_text("fr") == map_share.FOLLOWUP["fr"]


# --- 3. decisions -------------------------------------------------------------------------------


@pytest.mark.parametrize("key", list(decisions.TEXT))
def test_every_decision_text_has_an_arabic_version_with_the_same_placeholders(key: str) -> None:
    table = decisions.TEXT[key]
    assert ARABIC.search(table["ar"]), key
    holes = lambda t: sorted(re.findall(r"\{(\w+)\}", t))  # noqa: E731
    assert holes(table["ar"]) == holes(table["en"]), key
    assert table["ar"].count("؟") <= 1


def test_the_arabic_offer_is_the_fixed_offer_line() -> None:
    from app.modules.pi import fixed_lines

    assert decisions.TEXT["offer"]["ar"] == fixed_lines.LINES["offer"]["ar"]
    assert decisions.COST_ANSWER["ar"] == fixed_lines.LINES["cost"]["ar"]


@pytest.mark.parametrize("language", ROMAN_CHATS)
def test_urdu_and_hindi_chats_get_the_roman_urdu_decision_texts(language: str) -> None:
    for key in decisions.TEXT:
        values = {"business": "B", "quote": "Q-1", "total": "10", "changes": "c"}
        assert decisions.text(key, language, **values) == decisions.text(key, "roman_ur", **values)
    assert decisions.cost_answer(language) == decisions.COST_ANSWER["roman_ur"]
    assert decisions.with_consent("Ok.", language, {"ask_consent": True}).endswith(
        decisions.CONSENT_ASK["roman_ur"]
    )


def test_an_arabic_chat_gets_arabic_decision_texts_and_buttons() -> None:
    assert decisions.text("declined", "ar") == decisions.TEXT["declined"]["ar"]
    assert decisions.with_consent("حسناً.", "ar", {"ask_consent": True}).endswith(
        decisions.CONSENT_ASK["ar"]
    )
    offer = decisions.text("offer", "ar")
    assert decisions.buttons_for(offer) == decisions.OFFER_BUTTONS["ar"]
    assert (
        decisions.buttons_for(decisions.text("confirm_go", "ar")) == decisions.OFFER_BUTTONS["ar"]
    )
    assert decisions.buttons_for(decisions.text("re_offer", "ar")) == decisions.OFFER_BUTTONS["ar"]


def test_other_languages_keep_the_english_decision_text() -> None:
    assert decisions.text("declined", "fr") == decisions.TEXT["declined"]["en"]
    assert decisions.text("declined", None) == decisions.TEXT["declined"]["en"]


def test_the_english_and_roman_urdu_offer_buttons_still_ride_on_their_offers() -> None:
    assert (
        decisions.buttons_for(decisions.text("offer", "roman_ur"))
        == (decisions.OFFER_BUTTONS["roman_ur"])
    )
    assert decisions.buttons_for(decisions.text("offer", "en")) == decisions.OFFER_BUTTONS["en"]


# --- 5. buttons, meetings, deal nudges ----------------------------------------------------------


@pytest.mark.parametrize("language", ROMAN_CHATS)
def test_follow_up_and_consent_buttons_in_a_hindi_or_urdu_chat_are_roman_urdu(
    language: str,
) -> None:
    assert buttons.follow_up_buttons(language) == buttons.FOLLOW_UP["roman_ur"]


def test_follow_up_buttons_in_arabic_and_the_rest() -> None:
    assert buttons.follow_up_buttons("ar") == buttons.FOLLOW_UP["ar"]
    assert buttons.follow_up_buttons("fr") == buttons.FOLLOW_UP["en"]
    assert buttons.follow_up_buttons(None) == buttons.FOLLOW_UP["en"]
    assert all(len(t) <= 20 for v in buttons.FOLLOW_UP.values() for t in v)


MEETING = {
    "label": "Friday 10 July, 03:00 PM",
    "zone": "Asia/Karachi",
    "minutes": 30,
    "link": "https://meet.example.com/abc",
}


@pytest.mark.parametrize("language", ROMAN_CHATS)
def test_a_meeting_in_a_hindi_or_urdu_chat_is_roman_urdu(language: str) -> None:
    said = meetings.meeting_message(MEETING, language)
    assert said == meetings.meeting_message(MEETING, "roman_ur")
    assert "Pakistan ka waqt" in said and "Pakistan time" not in said
    assert not ARABIC.search(said) and not DEVANAGARI.search(said)


def test_an_arabic_meeting_has_the_time_the_link_and_arabic_words() -> None:
    said = meetings.meeting_message(MEETING, "ar")
    assert MEETING["label"] in said and MEETING["link"] in said
    assert "بتوقيت باكستان" in said and "Pakistan time" not in said
    place = meetings.meeting_message({**MEETING, "link": "", "place": "Lahore"}, "ar")
    assert "Lahore" in place and "https" not in place


def test_an_english_meeting_is_unchanged() -> None:
    assert meetings.meeting_message(MEETING, "en") == (
        "Your meeting is confirmed: *Friday 10 July, 03:00 PM* (Pakistan time), 30 minutes."
        "\nJoin here:\nhttps://meet.example.com/abc"
        "\nOpen the link at that time; it works in a browser or on your phone."
    )
    assert meetings.meeting_message(MEETING, "fr") == meetings.meeting_message(MEETING, "en")


@pytest.mark.parametrize("key", list(deal_followups.TEXTS))
def test_every_deal_nudge_has_arabic_with_the_same_placeholders(key: str) -> None:
    table = deal_followups.TEXTS[key]
    holes = lambda t: sorted(re.findall(r"\{(\w+)\}", t))  # noqa: E731
    assert holes(table["ar"]) == holes(table["en"]), key
    assert ARABIC.search(table["ar"])


@pytest.mark.parametrize("language", ROMAN_CHATS)
def test_a_deal_nudge_in_a_hindi_or_urdu_chat_is_roman_urdu(language: str) -> None:
    values = {
        "hi": " Sana", "number": "Q-1", "business": "B", "total": "10", "amount": "10",
        "due": "1 Jan", "pay": "",
    }  # fmt: skip
    for key in ("proposal_unopened", "proposal_unanswered", "invoice_due", "invoice_overdue"):
        assert deal_followups.text(key, language, **values) == deal_followups.text(
            key, "roman_ur", **values
        )


def test_deal_nudges_in_arabic_english_and_the_rest() -> None:
    values = {"hi": "", "number": "Q-1", "business": "B", "total": "10"}
    assert ARABIC.search(deal_followups.text("proposal_unopened", "ar", **values))
    assert deal_followups.text("proposal_unopened", "fr", **values) == deal_followups.text(
        "proposal_unopened", "en", **values
    )


# --- 7. Pashto, Punjabi (Gurmukhi) and Sindhi ----------------------------------------------------

PASHTO = "زه ډېر ښه یم او زما دوکان ټول ورځ ګډوډ دی"
GURMUKHI = "ਮੇਰੀ ਦੁਕਾਨ ਵਿੱਚ ਸਮਾਨ ਮੁੱਕ ਜਾਂਦਾ ਹੈ ਤੇ ਸਟਾਫ਼ ਲੇਟ ਆਉਂਦਾ ਹੈ"
SINDHI = "منهنجي دڪان ۾ سامان ختم ٿي وڃي ٿو ۽ عملو دير سان اچي ٿو"


@pytest.mark.parametrize("text", [PASHTO, GURMUKHI, SINDHI])
def test_pashto_gurmukhi_and_sindhi_get_the_polite_unsupported_line(text: str) -> None:
    assert safety.unsupported_language(text)


@pytest.mark.parametrize(
    "text",
    [
        "میرا مال ختم ہو جاتا ہے اور عملہ دیر سے آتا ہے",  # Urdu
        "من در مغازه‌ام مشکل دارم",  # Persian
        "أحتاج مساعدة في متجري",  # Arabic
        "मेरी दुकान में माल खत्म हो जाता है",  # Hindi
        "Mera maal khatam ho jata hai",
        "My shop is a mess",
        "",
    ],
)
def test_other_languages_are_not_unsupported(text: str) -> None:
    assert not safety.unsupported_language(text)


def test_the_unsupported_line_names_the_languages_and_asks_for_english_or_urdu() -> None:
    said = safety.UNSUPPORTED_TEXT
    assert "can't read Pashto well yet" in said  # the older integration test still holds
    assert "Punjabi" in said and "Sindhi" in said
    assert "English or Urdu" in said
    assert said.count("?") == 0
    assert not re.search(r"\b(?:sakta|sakti|raha|rahi)\b", said)  # R-GEN: no gendered verb


def test_gurmukhi_is_an_other_script() -> None:
    assert other_script(GURMUKHI) == "Punjabi (Gurmukhi)"
    assert other_script("Hello, I own a shop") is None
