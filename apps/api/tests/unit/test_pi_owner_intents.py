import asyncio
from types import SimpleNamespace

from app.modules.pi import owner_asks, owner_intents

ALL_FALSE = (
    '{"no_questions": false, "no_records": false, "asks_plan": false, '
    '"repeat_complaint": false, "asks_recall": false, "asks_suggest": false}'
)


def test_parse_reads_the_six_flags():
    flags = owner_intents.parse(ALL_FALSE.replace('"asks_plan": false', '"asks_plan": true'))
    assert flags is not None and flags["asks_plan"] and not flags["no_records"]


def test_parse_rejects_text_that_is_not_json():
    assert owner_intents.parse("sorry") is None
    assert owner_intents.parse("") is None
    assert owner_intents.parse("{}") is None


def test_needed_only_for_languages_the_banks_do_not_cover():
    assert not owner_intents.needed("please no more questions right now")
    assert not owner_intents.needed("abhi mujh se aur sawal na karein")
    assert owner_intents.needed("من فضلك لا مزيد من الأسئلة الآن")
    assert owner_intents.needed("por favor, no más preguntas ahora")
    assert not owner_intents.needed("ok")  # too short to be an ask


def test_stored_and_merged_flags_carry_across_messages():
    media = {"intents": {"no_records": True, "asks_plan": False}}
    assert owner_intents.stored(media) == {"no_records": True}
    assert owner_intents.merged("hola", media) == {"no_records": True}
    assert owner_intents.merged("no more questions", None) == {"no_questions": True}


def test_read_gives_positions_oldest_first():
    seen = owner_intents.read(
        [
            ("nous n'avons pas de registre", {"intents": {"no_records": True}}),
            ("bonjour", None),
            ("please explain the overall plan", None),
        ]
    )
    assert seen["no_records"] == [0]
    assert seen["asks_plan"] == [2]


def test_classify_returns_the_models_verdict_and_never_raises():
    class Manager:
        def __init__(self, text=None, boom=False):
            self.text, self.boom = text, boom

        async def complete(self, *a, **k):
            if self.boom:
                raise RuntimeError("down")
            return SimpleNamespace(text=self.text)

    said = "من فضلك لا مزيد من الأسئلة الآن"
    on = ALL_FALSE.replace('"no_questions": false', '"no_questions": true')
    got = asyncio.run(owner_intents.classify(Manager(on), None, said=said, conversation_id=None))
    assert got is not None and got["no_questions"]
    assert (
        asyncio.run(
            owner_intents.classify(Manager(boom=True), None, said=said, conversation_id=None)
        )
        is None
    )
    # English never reaches the model
    assert (
        asyncio.run(
            owner_intents.classify(
                Manager(on), None, said="no more questions please", conversation_id=None
            )
        )
        is None
    )


def test_english_recall_wordings():
    for text in ("I don't remember what we decided last time", "I can't recall what was agreed"):
        assert owner_asks.asks_for_recall(text)


def test_without_questions_in_cjk_and_arabic_punctuation():
    assert "？" not in owner_asks.without_questions("我们先从订单开始。你想先做哪一部分？")
    assert "؟" not in owner_asks.without_questions(
        "نبدأ بالطلبات أولاً هذا الأسبوع. ما الجزء الذي تريده؟"
    )


def test_one_marker_word_does_not_decide_the_language():
    from app.modules.pi.language import detect_language

    assert detect_language("nous n'avons pas de registre, je ne sais pas exactement") is None
    assert detect_language("por favor, no más preguntas ahora") is None
    assert detect_language("hamare paas record nahi hai") == "roman_ur"
    assert detect_language("we do not keep any records") == "en"
