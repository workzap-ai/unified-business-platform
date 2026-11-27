"""pi's notes of one call: kept clean, kept small, and put back after an agent restart."""

from test_pi_room_speech import Manager

from app.modules.pi_meetings import room_recall, voice
from app.modules.pi_meetings.room_speech import Session, Settings


def test_a_fact_is_added_once_and_a_correction_replaces_the_old_one() -> None:
    facts: list[str] = []
    room_recall.merge_fact(facts, "team of four people")
    room_recall.merge_fact(facts, "one oven, sells bread")
    room_recall.merge_fact(facts, "team of five people", replaces="team of four people")
    assert facts == ["one oven, sells bread", "team of five people"]
    room_recall.merge_fact(facts, "sells bread, one oven")  # the same fact in other words
    assert len(facts) == 2
    room_recall.merge_fact(facts, "")
    assert len(facts) == 2


def test_the_notes_are_capped() -> None:
    facts: list[str] = []
    for n in range(100):
        room_recall.merge_fact(facts, f"fact number {n} about topic{n} and thing{n}")
    assert len(facts) == room_recall.KEEP_FACTS


def test_notes_survive_a_restart_into_a_fresh_session() -> None:
    old = Session(Settings(mode="speak"))
    old.history = [
        voice.Said(True, "Hi, I'm pi, an AI. What does your business do?"),
        voice.Said(False, "I run a bakery in Karachi"),
        voice.Said(True, "How many people work there?"),
    ]
    old.facts = ["bakery in Karachi"]
    old.language_pref = "ur"
    old.ideas = 1
    notes = room_recall.pack(old)
    assert notes["recent"] == [[0, "I run a bakery in Karachi"], [1, "How many people work there?"]]
    new = Session(Settings(mode="speak"))
    new.history = [voice.Said(True, voice.opening())]
    room_recall.restore(new, notes)
    assert new.facts == ["bakery in Karachi"] and new.language_pref == "ur" and new.ideas == 1
    assert [h.text for h in new.history][-2:] == [
        "I run a bakery in Karachi",
        "How many people work there?",
    ]
    # the last thing pi asked was a question: after a restart it still does not ask two in a row
    assert voice.question_policy(new.history) == "none"


def test_bad_or_empty_notes_change_nothing() -> None:
    session = Session(Settings(mode="speak"))
    for bad in (None, {}, {"facts": "x", "language": 5, "ideas": "many", "recent": [1, [2]]}):
        room_recall.restore(session, bad)
    assert session.facts == [] and session.language_pref == "" and session.history == []


def test_the_notes_never_grow_past_the_ceiling() -> None:
    session = Session(Settings(mode="speak"))
    session.facts = [("long fact " * 12) + str(n) for n in range(40)]
    session.history = [voice.Said(i % 2 == 0, "line " + "x" * 300) for i in range(30)]
    assert len(repr(room_recall.pack(session))) <= room_recall.NOTES_CHARS + 400


async def test_a_correction_in_the_model_reply_updates_the_session_notes() -> None:
    from uuid import uuid4

    from app.shared.scope import WorkspaceScope

    class Corrects(Manager):
        async def complete_structured(self, scope, model, **kw):
            from types import SimpleNamespace

            return SimpleNamespace(
                value=model(
                    reply="Five people, noted.",
                    learned="team of five people",
                    replaces="team of four people",
                )
            )

    scope = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "t")
    out = await voice.reply_to(
        Corrects(), scope, [voice.Said(True, "Hi, I'm pi, an AI.")], "no, we are five people"
    )
    facts = ["team of four people"]
    room_recall.merge_fact(facts, out.learned, out.replaces)
    assert facts == ["team of five people"]


def test_a_name_the_redactor_removed_is_never_kept_or_spoken() -> None:
    named = voice.ModelReply(reply="ok", learned="bakery is called Fast Baker")
    assert voice._fact(named) == ""  # "called someone" would be nonsense
    assert voice.has_tic("Got it, your bakery is called someone.")
    assert voice.has_tic("Your bakery is named someone.")
    assert voice._fact(voice.ModelReply(reply="ok", learned="sells bread, team of five")) != ""


def test_a_question_about_what_was_already_said_is_known() -> None:
    history = [
        voice.Said(True, "Hi, I'm pi, an AI. What does your business do?"),
        voice.Said(False, "I run a small bakery in Karachi with four people and one oven"),
    ]
    assert voice.asks_known("So you run a small bakery in Karachi with four people?", history, "")
    assert not voice.asks_known("How often do the morning orders go out late?", history, "")
    assert not voice.asks_known("Which city?", history, "")  # too short to judge
