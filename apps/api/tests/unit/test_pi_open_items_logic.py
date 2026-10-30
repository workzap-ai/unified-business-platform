"""Platform spec v1.4, 17.7 (HO2, HO5, A43): open items are kept until answered or dropped by the
owner, named first on return in the owner's language, and coloured against the service level."""

import pytest

from app.modules.pi import open_items, open_requests

LANGUAGES = ("en", "roman_ur", "ur", "ar", "fr", "fa", "es")


def test_a_request_is_kept_past_three_replies_in_brain_mode_and_dropped_when_the_owner_lets_go():
    state = open_requests.update(None, "kitne din lagenge?", "Hmm.", persistent=True)
    for _ in range(open_requests.MAX_OPEN_TURNS + 4):
        state = open_requests.update(state, "ok", "Hmm.", persistent=True)
    assert [e["kind"] for e in state] == ["timeline"]  # HO5: it survives
    assert open_requests.update(state, "chhor do", "Hmm.", persistent=True) == []
    # the older behaviour is unchanged without the flag
    plain = open_requests.update(None, "kitne din lagenge?", "Hmm.")
    for _ in range(open_requests.MAX_OPEN_TURNS):
        plain = open_requests.update(plain, "ok", "Hmm.")
    assert plain == []


def test_owner_lets_go_only_in_a_short_message_and_not_about_a_problem():
    assert open_items.drops("chhor do")
    assert open_items.drops("never mind")
    assert open_items.drops("laisse tomber")
    assert not open_items.drops("ye masla chhor do")  # that parks a problem on the map
    assert not open_items.drops("never mind, but what I really need is " + "x" * 80)
    assert not open_items.drops("")


def test_a_promise_to_come_back_is_found_in_the_languages():
    assert open_items.promises("Main wapas aata hoon is par.")
    assert open_items.promises("I'll get back to you on that.")
    assert open_items.promises("Je reviens vers vous demain.")
    assert not open_items.promises("The quote says how long it takes.")


def test_a_question_is_answered_when_the_reply_carries_its_words():
    question = "what are your delivery charges for Lahore"
    assert open_items.answers(question, "Delivery charges for Lahore start at a flat fee.")
    assert not open_items.answers(question, "Which shop is worst?")
    assert not open_items.answers("price?", "price is on the quote")  # too few words to judge


def test_the_return_line_names_what_is_open_in_each_language_with_no_question_mark():
    items = [{"kind": "owner_question", "text": "Kitna kharcha hoga?"}]
    seen = set()
    for language in LANGUAGES:
        text = open_items.return_line_for(items, language)
        assert "Kitna kharcha hoga" in text and "?" not in text and "؟" not in text, language
        seen.add(text)
    assert len(seen) >= 6  # Urdu script is answered in Roman Urdu by the fixed-line rule
    assert open_items.return_line_for(items, "ur") == open_items.return_line_for(items, "roman_ur")
    assert "noted" not in open_items.return_line_for(items, "en").lower()
    assert open_items.return_line_for([], "en") == ""
    more = [{"kind": "owner_request", "text": f"thing {n}"} for n in range(5)]
    assert open_items.return_line_for(more, "en").count("still open") == open_items.MAX_SURFACED


def test_the_handoff_line_exists_in_every_language_and_is_never_english_for_the_others():
    for language in LANGUAGES:
        assert open_items.handoff_line(language)
    assert "Workzap team ko" in open_items.handoff_line("roman_ur")
    assert open_items.handoff_line("fr") != open_items.handoff_line("en")
    assert open_items.handoff_line("xx") == open_items.handoff_line("en")  # nothing else to use
    assert open_items.handoff_line("hi") == open_items.handoff_line("roman_ur")


@pytest.mark.parametrize(
    ("kind", "minutes", "colour"),
    [
        ("pending_handoff", 5, "green"),
        ("pending_handoff", 20, "amber"),
        ("pending_handoff", 31, "red"),
        ("owner_question", 100, "green"),
        ("owner_question", 200, "amber"),
        ("owner_question", 241, "red"),
        ("promised_followup", 1500, "red"),
    ],
)
def test_the_colour_is_against_the_service_level_of_the_kind(kind, minutes, colour):
    assert open_items.colour(minutes, open_items.sla_minutes(kind)) == colour


def test_every_kind_the_spec_names_has_a_service_level():
    assert set(open_items.SLA_MINUTES) == {
        "owner_question",
        "owner_request",
        "pending_handoff",
        "promised_followup",
    }
