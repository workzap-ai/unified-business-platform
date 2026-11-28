"""The rules for when pi may speak in a video room."""

from dataclasses import replace

import pytest

from app.modules.pi_meetings.room_turns import (
    COOLDOWN_S,
    MAX_SPOKEN,
    RoomState,
    Utterance,
    addressed,
    decide,
)

BASE = RoomState(
    mode="speak",
    muted=False,
    disclosed=True,
    spoken=0,
    last_spoke_at=None,
    someone_speaking=False,
    customers=1,
    intake=False,
)


def say(text: str, speaker: str = "g_1", *, final: bool = True, at: float = 100.0) -> Utterance:
    return Utterance(speaker_id=speaker, text=text, final=final, at=at)


@pytest.mark.parametrize(
    "text",
    [
        "pi, what do you think?",
        "Pi can you note that down",
        "hey PI",
        "pi",
        "پائی یہ نوٹ کر لو",
        "पाई यह लिख लो",
    ],
)
def test_pi_is_addressed_by_name(text: str) -> None:
    assert addressed(text)
    assert decide(say(text), BASE).action == "speak"


@pytest.mark.parametrize("text", ["the pie was good", "pipeline is late", "spirit", "pin it"])
def test_other_words_are_not_pis_name(text: str) -> None:
    assert not addressed(text)
    assert decide(say(text), BASE).reason == "not_addressed"


def test_a_name_in_staff_speech_is_a_command_too() -> None:
    assert decide(say("pi, summarise the problems", "s_9"), BASE).action == "speak"


def test_the_first_turn_is_the_ai_disclosure() -> None:
    state = replace(BASE, disclosed=False)
    assert decide(say("pi, hello"), state).action == "disclose"
    assert decide(say("pi, hello"), BASE).action == "speak"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"mode": "off"}, "mode"),
        ({"mode": "suggest"}, "mode"),
        ({"muted": True}, "muted"),
        ({"spoken": MAX_SPOKEN}, "cap"),
        ({"someone_speaking": True}, "someone_speaking"),
        ({"last_spoke_at": 98.0}, "cooldown"),
    ],
)
def test_pi_stays_silent_when_a_gate_is_closed(change: dict, reason: str) -> None:
    out = decide(say("pi, what do you think?"), replace(BASE, **change))
    assert (out.action, out.reason) == ("silent", reason)


def test_after_the_cooldown_pi_may_speak_again() -> None:
    state = replace(BASE, last_spoke_at=100.0 - COOLDOWN_S - 1)
    assert decide(say("pi, and now?"), state).action == "speak"


def test_a_partial_or_unknown_speaker_is_never_answered() -> None:
    assert decide(say("pi, hello", final=False), BASE).reason == "not_final"
    assert decide(say("pi, hello", speaker=""), BASE).reason == "unknown_speaker"


@pytest.mark.parametrize("text", ["pi stop", "pi, be quiet please", "pi chup", "pi خاموش"])
def test_asking_pi_to_be_quiet_keeps_it_silent(text: str) -> None:
    assert decide(say(text, "s_9"), BASE).reason == "asked_to_be_quiet"


def test_no_one_named_pi_and_no_intake_means_silence() -> None:
    assert decide(say("we ship on Monday and it is late"), BASE).reason == "not_addressed"


def test_intake_speaks_after_a_lone_customers_turn_only() -> None:
    intake = replace(BASE, intake=True)
    turn = "my stock finishes every month and orders get late"
    assert decide(say(turn), intake).action == "speak"
    assert decide(say(turn, "s_9"), intake).reason == "not_addressed"  # a staff turn
    assert decide(say(turn), replace(intake, customers=2)).reason == "not_addressed"
    assert decide(say(turn), replace(intake, customers=0)).reason == "not_addressed"
    assert decide(say("ok hmm"), intake).reason == "not_addressed"  # too short
    assert decide(say(turn), BASE).reason == "not_addressed"  # intake is off


def test_intake_also_starts_with_the_disclosure() -> None:
    state = replace(BASE, intake=True, disclosed=False)
    assert decide(say("my stock finishes every month and orders get late"), state).action == (
        "disclose"
    )


def test_the_name_is_found_when_speech_to_text_spells_it_differently():
    for spelled in (
        "Pie, can you hear me?",
        "hey Pai what do you think",
        "P.I., hello",
        "Hello, Pai.",  # seen live: a comma after the greeting
        "hello pait hello",
        "Hi, pie. What can you do?",
        "Hello, bye.",  # seen live: "Hello, pi" heard as "bye"
    ):
        assert addressed(spelled)
    for not_the_name in ("ok bye then", "bye", "I will buy it", "good bye everyone"):
        assert not addressed(not_the_name)
    assert not addressed("I ate a piece of pizza")
