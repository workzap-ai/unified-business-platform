"""People pause inside a sentence and the voice detector ends a turn at a pause: pi must answer the
whole sentence, not its first breath. Found live: a customer who spoke in two or three pieces got no
answer, because every piece but the last was heard while they were still talking and the last was
too short to count."""

from uuid import uuid4

from test_pi_room_speech import Manager, Out

from app.modules.pi_meetings import room_speech, voice
from app.modules.pi_meetings.room_speech import RoomSpeech, Session, Settings
from app.modules.pi_meetings.room_vad import Turn
from app.shared.scope import WorkspaceScope


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def build(*, customers=1, talking=lambda: False):
    clock = Clock()
    manager = Manager()
    speech = RoomSpeech(
        manager=manager,
        scope=WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "test"),
        session=Session(Settings(mode="speak", intake=True)),
        out=Out(),
        customers=lambda: customers,
        someone_speaking=talking,
        clock=clock,
    )
    return speech, manager, clock


async def say(speech, manager, words, who="g_1", *, keep_pause=False):
    manager.heard = words
    if not keep_pause:
        speech.session.last_spoke_at = None  # no pause between pi's turns unless a test asks
    return await speech.on_turn(Turn(who, b"\x10\x00" * 48000, 48000, 0.0, 1.0))


async def test_two_short_pieces_of_one_sentence_are_answered_together():
    speech, manager, clock = build()
    assert (
        await say(
            speech,
            manager,
            "hello",
        )
        == "not_addressed"
    )  # one word: too short alone
    clock.t += 2
    assert await say(speech, manager, "I run a small shop") == "disclosed"
    assert manager.tts and voice.opening() in manager.tts[0][0]


async def test_a_piece_heard_while_they_keep_talking_joins_their_next_piece():
    talking = {"now": True}
    speech, manager, clock = build(talking=lambda: talking["now"])
    assert await say(speech, manager, "hello, I run a small clothing shop") == "someone_speaking"
    assert manager.tts == []  # pi does not talk over them
    talking["now"] = False
    clock.t += 1.5
    assert await say(speech, manager, "and we sell online too") == "disclosed"


async def test_the_joined_words_reach_the_model_not_only_the_last_piece():
    speech, manager, clock = build()
    await say(speech, manager, "hello I run a small shop")  # disclosure
    sent = []
    original = manager.complete_structured

    async def spy(scope, model, **kw):
        sent.append(" ".join(m.content for m in kw["messages"]))
        return await original(scope, model, **kw)

    manager.complete_structured = spy
    clock.t += 20
    assert await say(speech, manager, "orders") == "not_addressed"
    clock.t += 2
    assert await say(speech, manager, "get missed when we are busy") == "spoke"
    assert "orders get missed when we are busy" in sent[0]


async def test_an_old_piece_is_not_joined_and_is_kept_in_the_history():
    speech, manager, clock = build()
    assert await say(speech, manager, "hello") == "not_addressed"
    clock.t += room_speech.CARRY_S + 1
    assert await say(speech, manager, "two words") == "not_addressed"  # only two words alone
    assert [h.text for h in speech.session.history] == ["hello"]


async def test_pieces_of_different_people_are_not_joined():
    speech, manager, clock = build(customers=2)
    assert await say(speech, manager, "hello", who="g_1") == "not_addressed"
    clock.t += 1
    # the second person's words stand alone: g_1's "hello" is not put in front of them
    assert await say(speech, manager, "I run a shop", who="g_2") == "disclosed"
    assert speech.session.carry["g_1"][0] == "hello"
    assert "g_2" not in speech.session.carry


async def test_a_long_run_of_pieces_never_grows_without_limit():
    speech, manager, clock = build(customers=2)  # nobody is named: every piece is held
    for _ in range(80):
        clock.t += 1
        await say(speech, manager, "blah blah blah blah blah blah")
    assert len(speech.session.carry["g_1"][0]) <= room_speech.CARRY_CHARS


async def test_with_two_customers_pi_introduces_itself_and_then_answers_whoever_answers_it():
    speech, manager, clock = build(customers=2)
    assert await say(speech, manager, "hello, we are two partners here", who="g_1") == "disclosed"
    clock.t += 4  # g_2 answers pi's question a few seconds later
    assert (
        await say(speech, manager, "we sell clothes online", who="g_2", keep_pause=True) == "spoke"
    )
    # talking among themselves, long after pi's last question, is left alone
    clock.t += 60
    said = await say(speech, manager, "did you pay the rent yet", who="g_1", keep_pause=True)
    assert said == "not_addressed"


async def test_staff_speaking_first_also_brings_the_introduction():
    speech, manager, clock = build(customers=1)
    assert await say(speech, manager, "welcome everyone to this call", who="s_1") == "disclosed"
    assert voice.opening() in manager.tts[0][0]


async def test_pi_does_not_answer_an_answer_in_the_same_breath():
    speech, manager, clock = build(customers=2)
    assert await say(speech, manager, "hello, we are two partners here", who="g_1") == "disclosed"
    speech.session.last_spoke_at = clock.t  # pi finished speaking just now
    manager.heard = "we sell clothes online"
    assert await speech.on_turn(Turn("g_2", b"\x10\x00" * 48000, 48000, 0.0, 1.0)) == "cooldown"


async def test_a_one_word_answer_to_pis_question_is_answered_but_a_murmur_later_is_not():
    """Found live: pi asked what the business does, the customer said one word, and pi stayed silent
    because one word is too short to start a conversation. An answer to pi's own question counts."""
    speech, manager, clock = build(customers=1)
    assert await say(speech, manager, "hello, I run a small shop") == "disclosed"
    clock.t += 4
    assert await say(speech, manager, "clothes", keep_pause=True) == "spoke"
    clock.t += room_speech.room_turns.ANSWER_S + 5
    assert await say(speech, manager, "ok", keep_pause=True) == "not_addressed"


async def test_pi_waits_a_moment_for_someone_who_is_still_talking_instead_of_dropping_its_answer(
    monkeypatch,
):
    import asyncio

    state = {"until": 0.0}
    loop_start = asyncio.get_event_loop().time()
    speech, manager, clock = build(
        talking=lambda: asyncio.get_event_loop().time() - loop_start < state["until"]
    )
    monkeypatch.setattr(room_speech, "START_WAIT_S", 1.0)
    state["until"] = 0.0  # nobody talking while pi decides ...
    original = manager.synthesize

    async def synthesize(*a, **k):
        state["until"] = (asyncio.get_event_loop().time() - loop_start) + 0.3  # ... a person starts
        return await original(*a, **k)

    manager.synthesize = synthesize
    assert await say(speech, manager, "hello, I run a small shop") == "disclosed"
    assert speech.out.written  # it waited for the person to finish, then spoke


async def test_hello_after_a_long_silence_picks_the_conversation_back_up_but_a_murmur_does_not():
    """Found live: after a quiet minute a customer said 'hello?' and pi, which counts three words
    as the least for a conversation, stayed silent: it looked dead."""
    speech, manager, clock = build(customers=1)
    assert await say(speech, manager, "hello, I run a small shop") == "disclosed"
    clock.t += room_speech.room_turns.ANSWER_S + 30
    assert await say(speech, manager, "ok", keep_pause=True) == "not_addressed"
    assert await say(speech, manager, "thank you", keep_pause=True) == "unheard"  # silence as words
    assert await say(speech, manager, "hello?", keep_pause=True) == "spoke"


async def test_a_phrase_the_speech_to_text_invented_is_not_heard_at_all():
    speech, manager, clock = build(customers=1)
    assert await say(speech, manager, "Thanks for watching!") == "unheard"
    assert manager.tts == []


async def test_pi_is_told_how_to_sound_and_a_fixed_line_is_spoken_from_memory_the_second_time():
    from test_pi_room_speech import Manager, Out  # noqa: F401 - the same fakes

    speech, manager, clock = build(customers=1)
    assert await say(speech, manager, "hello, I run a small shop") == "disclosed"
    assert room_speech.STYLE_EN in manager.tts[0][1]["instructions"]
    # a second call in the same process: the introduction needs no new synthesis
    speech2, manager2, clock2 = build(customers=1)
    assert await say(speech2, manager2, "hello, I run a small shop") == "disclosed"
    assert manager2.tts == [] and speech2.out.written  # heard from the kept audio


async def test_an_urdu_line_is_spoken_in_the_urdu_style():
    speech, manager, clock = build(customers=1)
    await speech._say("اچھا، آپ کا کاروبار کیا ہے؟")
    assert manager.tts[0][1]["instructions"] == room_speech.STYLE_UR


def test_silence_the_model_wrote_as_words_is_noise_but_real_short_words_are_not():
    from app.modules.pi_meetings import room_noise

    for invented in (
        "you",
        ".",
        "...",
        "Thank you.",
        "Thank you for watching",
        "Thanks for watching!",
    ):
        assert room_noise.is_invented(invented), invented
    for real in ("bye", "khuda hafiz", "yes", "ok", "no", "hello?", "Thank you, that helps a lot"):
        assert not room_noise.is_invented(real), real


async def test_a_dot_or_a_you_after_pi_spoke_does_not_make_pi_answer_again():
    """Found live: pi answered the same sentence twice (once in Urdu, once in English) because the
    model wrote 'you' for a moment of silence and that counted as the person's answer."""
    speech, manager, clock = build(customers=1)
    assert await say(speech, manager, "hello, I run a small shop") == "disclosed"
    clock.t += 4
    assert await say(speech, manager, "you", keep_pause=True) == "unheard"
    assert await say(speech, manager, ".", keep_pause=True) == "unheard"
    assert await say(speech, manager, "Thank you.", keep_pause=True) == "unheard"
    assert len(manager.tts) == 1  # only the introduction was ever spoken
    assert await say(speech, manager, "bargaining customers", keep_pause=True) == "spoke"


def test_the_language_is_decided_by_code_from_the_latest_words_then_the_earlier_ones():
    from app.modules.pi_meetings import voice

    pi = voice.Said(True, "Hi, I'm pi, an AI from Workzap. What does your business do?")
    urdu = voice.Said(False, "meri kapron ki dukaan hai aur orders miss ho jate hain")
    assert voice.reply_language([pi], "I run a small clothing shop") == "en"
    assert (
        voice.reply_language([pi], "meri kapron ki dukaan hai aur orders miss ho jate hain")
        == "roman_ur"
    )
    # one unclear word keeps the language they spoke before
    assert voice.reply_language([pi, urdu], "bargaining") == "roman_ur"
    assert voice.reply_language([pi, voice.Said(False, "I run a shop")], "ok") == "en"
    # nothing to go on: the room's setting, then English
    assert voice.reply_language([], "ok", "ur") == "roman_ur"
    assert voice.reply_language([], "ok") == "en"
    assert voice.opening_language("meri dukaan hai kapron ki", "") == "ur"
    assert voice.opening_language("I run a shop", "ur") == ""


def test_the_script_of_a_reply_must_match_the_language_and_two_questions_are_followed_by_none():
    from app.modules.pi_meetings import voice

    assert voice.in_reply_language("I see, that is hard.", "en")
    assert not voice.in_reply_language("اچھا، سمجھ گیا۔", "en")
    assert voice.in_reply_language("اچھا، سمجھ گیا۔", "roman_ur")
    assert not voice.in_reply_language("Achha, samajh gaya.", "roman_ur")
    q = voice.Said(True, "What does your business do?")
    s = voice.Said(True, "I see, bargaining hurts your margin.")
    assert voice.question_policy([q]) == "optional"
    assert voice.question_policy([q, voice.Said(False, "x"), q]) == "none"
    assert voice.question_policy([q, voice.Said(False, "x"), s]) == "optional"


async def test_a_wrong_language_reply_is_corrected_once_and_then_it_is_the_safe_line():
    from test_pi_room_speech import Manager  # noqa: F401

    from app.modules.pi_meetings import voice

    class Replies(Manager):
        def __init__(self, *replies):
            super().__init__()
            self.replies = list(replies)
            self.notes = []

        async def complete_structured(self, scope, model, **kw):
            payload = kw["messages"][-1].content
            self.notes.append("correction" in payload)
            reply = self.replies.pop(0) if self.replies else self.replies_last
            self.replies_last = reply
            return type("R", (), {"value": model(reply=reply)})()

    pi = voice.Said(True, voice.opening())
    scope = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "t")
    # English asked, Urdu written, then English: one correction fixes it
    first = Replies(
        "اچھا، سمجھ گیا۔ کیا آرڈر چھوٹ جاتے ہیں؟", "I see, orders get missed. How often?"
    )
    said = await voice.reply_to(first, scope, [pi], "orders get missed when we are busy")
    assert said.text == "I see, orders get missed. How often?" and first.notes == [False, True]
    # still wrong after the correction: the safe line, never the wrong language
    second = Replies("اچھا، سمجھ گیا۔ کیا آرڈر چھوٹ جاتے ہیں؟")
    said = await voice.reply_to(second, scope, [pi], "orders get missed when we are busy")
    assert said.fallback is True
    # two questions in a row: the next reply must carry no question
    q = voice.Said(True, "How often do orders get missed?")
    third = Replies("What does that cost you?", "I see, that costs you customers.")
    history = [pi, voice.Said(False, "we sell clothes"), q, voice.Said(False, "twice a week")]
    said = await voice.reply_to(third, scope, history, "about ten thousand rupees a month")
    assert "?" not in said.text and third.notes == [False, True]


async def test_the_introduction_is_in_the_language_the_person_first_spoke():
    speech, manager, clock = build(customers=1)
    assert await say(speech, manager, "meri kapron ki dukaan hai aur orders miss hote hain") == (
        "disclosed"
    )
    assert "مصنوعی ذہانت" in manager.tts[0][0]


async def test_when_the_person_starts_talking_again_while_pi_thinks_it_answers_the_whole_once():
    """Found live: pi answered the first half of a long sentence, and then the second half too: two
    answers in a row. If the same person is talking again when the answer is ready, it is thrown
    away and held with what they say next, and pi answers once."""
    speech, manager, clock = build(customers=1)
    assert await say(speech, manager, "hello, I run a small shop") == "disclosed"
    clock.t += 30  # a long pause: the next words are not an answer to the introduction
    manager.tts.clear()
    talking = {"again": True}
    speech.speaker_active = lambda who: talking["again"]  # they began talking while pi thought
    assert await say(speech, manager, "customers bargain a lot, they ask for discounts") == (
        "someone_speaking"
    )
    assert manager.tts == []  # nothing was said over them
    assert speech.session.carry["g_1"][0].startswith("customers bargain")
    talking["again"] = False
    clock.t += 3
    assert await say(speech, manager, "and sometimes ten customers a day") == "spoke"
    assert len(manager.tts) == 1  # one answer, to both halves together
