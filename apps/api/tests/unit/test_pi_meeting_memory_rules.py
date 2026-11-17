"""Who pi is talking to before it uses what it remembers: a clear yes, in English, Roman Urdu or
Urdu script, unlocks the memory; a no, another person or anything unclear never does."""

import pytest

from app.modules.pi_meetings import meeting_memory, voice
from app.modules.pi_meetings.voice import Said

ASK = voice.opening("Ayesha")


@pytest.mark.parametrize(
    "reply",
    ["yes", "Yes, speaking", "yeah that's right", "ji haan", "haan bilkul", "جی ہاں", "ہاں"],
)
def test_a_clear_yes_confirms(reply):
    assert voice.classify(reply) == "confirmed"


@pytest.mark.parametrize(
    "reply",
    [
        "no",
        "No, this is her brother",
        "nahi, main unka bhai hoon",
        "nahin ye assistant hai",
        "نہیں",
        "not really",
        "yes but this is her wife",  # a yes that names someone else is not a confirmation
    ],
)
def test_a_no_or_another_person_never_confirms(reply):
    assert voice.classify(reply) == "denied"


@pytest.mark.parametrize(
    "reply",
    [
        "hello who is this",
        "what is this about",
        "ok",
        "",
        "mera naam Ali",
        "Who is speaking?",  # 'speaking' is a yes-word, but this is a question
        "ji, kaun?",
        "Yes, I'm Ali",  # a different name
        "yes I'm her friend",
        "yes I am the accountant",
        "know",  # a mis-heard 'no'
    ],
)
def test_anything_unclear_is_not_a_confirmation(reply):
    assert voice.classify(reply) == "unclear"


def test_the_asked_name_may_sit_inside_a_yes_but_no_other_name_may():
    assert voice.classify("Yes, this is Ayesha", "Ayesha") == "confirmed"
    assert voice.classify("ji haan main hi hoon", "Ayesha") == "confirmed"
    assert voice.classify("Yes, this is Ali", "Ayesha") == "unclear"


def test_the_name_asked_is_read_back_from_the_opening_line():
    talk = [Said(True, ASK), Said(False, "yes this is Ayesha")]
    assert voice.confirm_state(talk) == "confirmed"
    assert voice.confirm_state([Said(True, ASK), Said(False, "yes this is Sara")]) == "unclear"


def test_the_opening_with_a_name_says_it_is_an_ai_and_asks_one_question():
    assert ASK.count("?") == 1 and ASK.endswith("?")
    assert "AI" in ASK and "Am I speaking with Ayesha?" in ASK
    assert voice.allowed(ASK, voice.context([], "")) == ASK


def test_without_a_name_the_opening_is_the_normal_intake_question():
    plain = voice.opening("")
    assert voice.IDENTITY_MARK not in plain and plain == voice.opening()


def test_the_state_is_read_from_the_conversation_so_far():
    assert voice.confirm_state([]) == "none"
    assert voice.confirm_state([Said(True, voice.opening())]) == "none"  # never asked who it was
    assert voice.confirm_state([Said(True, ASK)]) == "pending"
    assert voice.confirm_state([Said(True, ASK), Said(False, "haan ji")]) == "confirmed"
    assert voice.confirm_state([Said(True, ASK), Said(False, "no")]) == "denied"
    # only the FIRST answer counts: a later "yes" cannot undo a no
    talk = [Said(True, ASK), Said(False, "no"), Said(True, voice.NOT_THEM), Said(False, "yes")]
    assert voice.confirm_state(talk) == "denied"


def test_the_not_them_line_is_itself_an_allowed_spoken_line():
    assert voice.allowed(voice.NOT_THEM, voice.context([Said(True, ASK)], "no")) == voice.NOT_THEM


def block(name_status="owner_said", text="name: Ayesha", source="facts"):
    record = {"kind": "name", "status": name_status, "text": text, "source": source}
    return {"records": [record]}


def test_only_a_name_the_person_gave_is_used_to_greet_them():
    assert meeting_memory.first_name(block()) == "Ayesha"
    assert meeting_memory.first_name(block(text="name: Ayesha Khan")) == "Ayesha"
    assert meeting_memory.first_name(block("pi_inferred")) == ""  # a pi guess
    assert meeting_memory.first_name(block("derived")) == ""
    assert meeting_memory.first_name(block("confirmed")) == "Ayesha"
    assert meeting_memory.first_name(block(source="staff")) == ""  # a staff-record copy
    assert meeting_memory.first_name(block("stated")) == ""  # not in the chat's allowlist
    assert meeting_memory.first_name({}) == ""
    assert meeting_memory.first_name({"records": [{"kind": "problem", "text": "x"}]}) == ""
    assert meeting_memory.first_name(block(text="name: 12345")) == ""  # not a name


def test_only_what_the_person_said_may_shape_what_pi_says():
    mixed = {
        "records": [
            {"kind": "problem", "status": "owner_said", "text": "P1 stock", "source": "problems"},
            {"kind": "problem", "status": "pi_inferred", "text": "P2 guess", "source": "problems"},
            {"kind": "x", "status": "derived", "text": "P3 scan", "source": "problems"},
        ],
        "summary": "a blend that may hold a guess",
        "ideas_they_said_no_to": ["a loyalty card"],
    }
    out = meeting_memory.speakable(mixed)
    assert [r["text"] for r in out["records"]] == ["P1 stock"]
    assert "summary" not in out and out["ideas_they_said_no_to"] == ["a loyalty card"]
    guesses = {
        "records": [{"kind": "p", "status": "pi_inferred", "text": "g", "source": "problems"}]
    }
    assert meeting_memory.speakable(guesses) == {}
    assert meeting_memory.speakable({}) == {}


MEMORY = {
    "records": [
        {"kind": "contact", "status": "owner_said", "text": "contact: Bilal", "source": "facts"},
        {"kind": "order", "status": "owner_said", "text": "order 4471 was late", "source": "x"},
    ]
}


def test_a_number_or_a_name_from_memory_is_not_spoken_unless_the_person_said_it():
    leaks = meeting_memory.leaks
    seen = "we sell tiles and stock runs out"
    assert leaks("How is order 4471 going?", seen, MEMORY)
    assert leaks("Does Bilal still count stock?", seen, MEMORY)
    assert not leaks("How often does the stock run out?", seen, MEMORY)
    # once they said it themselves in this conversation, it is theirs to hear back
    assert not leaks("How is order 4471 going?", seen + " order 4471", MEMORY)
    assert not leaks("Does Bilal still count stock?", seen + " bilal counts", MEMORY)
    # a number counts whole: 15 said does not make 5 or 4471 said
    assert leaks("How is order 5 going?", seen + " order 15", {"records": [{"text": "x"}]})
    # with no memory there is nothing to leak
    assert not leaks("How is order 4471 going?", seen, {})
