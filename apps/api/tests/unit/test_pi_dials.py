# ruff: noqa: E501
"""The four live dials (Book 5, spec 2.2 to 2.4): signals in eight languages, smoothing, signal
beats dial, and chat 3 of spec 8.1 replayed message by message."""

import pytest

from app.modules.pi import dials
from app.modules.pi.dials import Dials, Mode, Pace, Trust

FEELING = {
    "en": "I am so tired and overwhelmed by this",
    "roman_ur": "main bohat pareshan hoon, thak gaya hoon",
    "ur": "میں بہت پریشان ہوں",
    "hi": "मैं बहुत परेशान हूँ",
    "ar": "أنا متعب جدا من هذا",
    "fr": "je suis épuisé et stressé",
    "fa": "من خیلی خسته هستم",
    "es": "estoy muy cansado y agobiado",
}
HURRY = {
    "en": "just tell me quickly",
    "roman_ur": "jaldi batao, kab tak hoga",
    "ur": "جلدی بتائیں",
    "hi": "जल्दी बताओ",
    "ar": "أحتاج جوابا بسرعة",
    "fr": "dites-moi vite",
    "fa": "سریع بگو",
    "es": "dime rápido",
}
BUY = {
    "en": "how much will it cost, send me a quote",
    "roman_ur": "kitna lagega is mein",
    "ur": "کتنا لگے گا",
    "hi": "कितना लगेगा",
    "ar": "كم التكلفة",
    "fr": "combien ça coûte, un devis",
    "fa": "قیمت چقدر میشه",
    "es": "cuánto cuesta, un presupuesto",
}
FIX = {
    "en": "what can we do about it",
    "roman_ur": "solution dein, kya kar sakte hain",
    "ur": "حل بتائیں",
    "hi": "समाधान बताओ",
    "ar": "ما العمل",
    "fr": "que faire",
    "fa": "راه حل چیه",
    "es": "qué podemos hacer",
}
TRUST = {
    "en": "who are you and how does this work",
    "roman_ur": "aap kaun ho, ye kaise kaam karta hai",
    "ur": "آپ کون ہیں",
    "hi": "आप कौन हो",
    "ar": "من أنت",
    "fr": "qui êtes-vous",
    "fa": "شما کی هستید",
    "es": "quién eres",
}
CORRECTION = {
    "en": "no, that's not what I said",
    "roman_ur": "nahi, aisa nahi hai, ye galat hai",
    "ur": "نہیں ایسا نہیں",
    "hi": "नहीं ऐसा नहीं",
    "ar": "لا ليس هكذا",
    "fr": "non, pas ça",
    "fa": "نه اینطور نیست",
    "es": "no, así no",
}
SENSITIVE = {
    "en": "we cannot pay the salaries this month",
    "roman_ur": "suppliers ko udhaar chukana hai aur salary bhi",
    "ur": "تنخواہ دینی ہے",
    "hi": "वेतन देना है",
    "ar": "لا نستطيع دفع الرواتب",
    "fr": "on ne peut pas payer les salaires",
    "fa": "حقوق را نمی توانیم بدهیم",
    "es": "no podemos pagar los salarios",
}


@pytest.mark.parametrize("lang", sorted(FEELING))
def test_feeling_words_open_up_and_listen(lang: str) -> None:
    s = dials.read_signals(FEELING[lang])
    assert s.openness >= 1 and s.mode == Mode.LISTEN


@pytest.mark.parametrize("lang", sorted(HURRY))
def test_hurry_moves_pace_and_mode_to_fix(lang: str) -> None:
    s = dials.read_signals(HURRY[lang])
    assert s.pace == 1 and s.hurry and s.mode in (Mode.FIX, Mode.BUY)


@pytest.mark.parametrize("lang", sorted(BUY))
def test_price_questions_are_buy_mode(lang: str) -> None:
    assert dials.read_signals(BUY[lang]).mode == Mode.BUY


@pytest.mark.parametrize("lang", sorted(FIX))
def test_asking_for_solutions_is_fix_mode(lang: str) -> None:
    assert dials.read_signals(FIX[lang]).mode == Mode.FIX


@pytest.mark.parametrize("lang", sorted(TRUST))
def test_who_are_you_is_a_think_mode_trust_test(lang: str) -> None:
    s = dials.read_signals(TRUST[lang])
    assert s.mode == Mode.THINK and s.trust_test


@pytest.mark.parametrize("lang", sorted(CORRECTION))
def test_a_correction_moves_trust_down(lang: str) -> None:
    s = dials.read_signals(CORRECTION[lang])
    assert s.correction and s.trust == -1


@pytest.mark.parametrize("lang", sorted(SENSITIVE))
def test_sensitive_subjects_open_up_and_slow_down(lang: str) -> None:
    s = dials.read_signals(SENSITIVE[lang])
    assert s.openness >= 1 and s.pace == -1


def test_one_word_and_ok_replies_close_the_dial_and_speed_up() -> None:
    for text in ("ok", "hmm", "pata nahi", "cost"):
        s = dials.read_signals(text)
        assert s.openness == -1 and s.pace == 1 and s.low, text
    assert dials.read_signals("ok").ack and not dials.read_signals("cost").ack


def test_a_long_message_with_numbers_opens_up() -> None:
    assert dials.read_signals("30% sale lagayi thi").openness == 1
    assert (
        dials.read_signals(
            "Is mein bohat se cheezein hain jo mujhe ek ek karke batani hain aur phir dekhna hai"
        ).openness
        == 1
    )


def test_asking_pis_opinion_opens_up_in_think_mode() -> None:
    s = dials.read_signals("aap kya kehte hain?")
    assert s.openness == 1 and s.mode == Mode.THINK


def test_return_after_a_gap_raises_trust() -> None:
    assert dials.read_signals("hi", gap_hours=30).trust == 1
    assert dials.read_signals("hi", gap_hours=2).trust == 0


def test_a_good_repair_raises_trust_again() -> None:
    d = dials.update(Dials(), "nahi, aisa nahi hai")
    assert d.trust_trend == Trust.FALLING
    d = dials.update(d, "haan ab theek hai, aur sunein", repaired=True)
    assert d.trust_trend == Trust.FLAT


def test_a_dial_moves_one_notch_at_a_time() -> None:
    d = Dials(openness=0)
    for expected in (1, 2, 3, 4):
        d = dials.update(d, "main bohat pareshan hoon, aur ye bhi mushkil hai, aur 40 log hain")
        assert d.openness == expected


def test_a_jump_may_move_openness_two() -> None:
    first = dials.update(Dials(openness=0, messages_seen=0), SENSITIVE["en"])
    assert first.openness == 2  # a sensitive disclosure in the first message
    s = dials.read_signals("asal masla ye hai ke cash nahi")
    assert s.jump and s.openness == 2
    assert (
        dials.update(Dials(openness=0, messages_seen=3), "asal masla ye hai ke cash nahi").openness
        == 2
    )


def test_a_plain_message_never_jumps() -> None:
    d = dials.update(Dials(openness=1, messages_seen=3), "theek hai ye bhi dekhte hain")
    assert d.openness == 1


def test_without_a_signal_a_dial_stays_where_it_was() -> None:
    d = Dials(
        openness=3, pace=Pace.SLOW, mode=Mode.THINK, trust_trend=Trust.RISING, messages_seen=4
    )
    after = dials.update(d, "qeemat zyada hai shayad")
    assert (after.openness, after.pace, after.mode, after.trust_trend) == (
        3,
        Pace.SLOW,
        Mode.THINK,
        Trust.RISING,
    )


def test_the_signal_wins_over_the_dial() -> None:
    d = Dials(mode=Mode.LISTEN, messages_seen=5)
    assert dials.update(d, "kitna lagega").mode == Mode.BUY
    assert dials.update(d, "solution dein").mode == Mode.FIX


def test_dials_stay_in_range() -> None:
    d = Dials(openness=0, pace=Pace.FAST)
    for _ in range(5):
        d = dials.update(d, "ok")
    assert d.openness == 0 and d.pace == Pace.FAST
    d = Dials(openness=4, pace=Pace.SLOW, messages_seen=3)
    d = dials.update(d, SENSITIVE["en"] + " and I am so tired, 12 people depend on this")
    assert d.openness == 4 and d.pace == Pace.SLOW


def test_fatigue_on_ok_jaldi_and_repeated_short_replies() -> None:
    assert dials.update(Dials(messages_seen=3), "ok").fatigue
    assert dials.update(Dials(messages_seen=3), "jaldi batao").fatigue
    d = dials.update(Dials(messages_seen=3), "pata nahi")
    d = dials.update(d, "cost")
    assert d.low_streak == 2 and d.fatigue
    assert not dials.update(
        Dials(messages_seen=3), "cost"
    ).fatigue  # one short answer is not fatigue


def test_trust_warms_when_they_confide() -> None:
    d = Dials(openness=2, messages_seen=4)
    d = dials.update(d, SENSITIVE["roman_ur"] + ", bohat pareshan hoon")
    assert d.openness >= 3 and d.trust_trend == Trust.RISING


def test_estimate_is_a_replay_and_stores_nothing() -> None:
    texts = ["hi", "ok"]
    assert dials.estimate(texts) == dials.estimate(texts)
    assert dials.estimate([]) == Dials()


def test_postures_are_for_the_engine_only() -> None:
    assert dials.posture(Dials(openness=3, mode=Mode.LISTEN)) == "talker"
    assert dials.posture(Dials(openness=0, pace=Pace.FAST, mode=Mode.FIX)) == "tester"
    assert dials.posture(Dials(openness=3, pace=Pace.FAST, mode=Mode.BUY)) == "hurried"
    assert not hasattr(Dials(), "posture")  # never a field: nothing is stored about the person


def test_backing_off_moves_one_notch() -> None:
    assert dials.backed_off(Dials(openness=3)).openness == 2
    assert dials.backed_off(Dials(openness=0)).openness == 0


def test_language_is_read_with_the_repo_detector() -> None:
    assert dials.read_signals("aap kaun ho, ye kaise kaam karta hai").language == "roman_ur"


# Spec 8.1 chat 3: the owner is a Tester at first, becomes a Talker.
CHAT3 = [
    "Hi",
    "mera clothing brand hai mere baby and male cloths hain 6crore ka stock wo bechna hai",
    "cost",
    "warehouse and outlets, dono jagah. poore sets hain. lagbhag aik saal se",
    "qeemat zyada hai shayad, aur design purane ho gaye",
    "30% sale lagayi thi, thora bika, phir ruk gaya. solution dein ap",
    "haan taqreeban aadha pichle saal ka hai",
    "DHA wale outlet mein thora behtar bikta hai, wahan ke log zyada brand dekhte hain aur staff achha bechta hai",
    "haan bohat. suppliers ko payment late hoti hai aur kabhi kabhi salary bhi",
    "suppliers ke saath. wo ab udhaar maal dene se mana kar rahe hain",
    "outlets ka hisaab mujhe hafte baad milta hai, ye bhi bura hai",
    "haan bilkul, pata hi nahi chalta. sab se pehle stock, phir hisaab",
]


def _replay(n: int) -> Dials:
    return dials.estimate(CHAT3[:n])


def test_chat3_opens_as_a_tester() -> None:
    d = _replay(2)  # "Hi", then the 6 crore stock message
    assert d.openness == 1 and d.pace == Pace.FAST  # Tester: openness 0 to 1, pace fast
    assert dials.posture(d) in {"tester", "terse"}


def test_chat3_one_word_answer_closes_openness_and_is_not_fatigue() -> None:
    d = _replay(3)  # "cost"
    assert d.openness == 0 and d.pace == Pace.FAST and not d.fatigue


def test_chat3_long_answer_that_fills_slots_opens_again() -> None:
    assert _replay(4).openness == _replay(3).openness + 1


def test_chat3_solution_dein_is_fix_mode_and_fast() -> None:
    d = _replay(6)
    assert d.mode == Mode.FIX and d.pace == Pace.FAST


def test_chat3_the_sensitive_disclosure_jumps_openness_to_three_or_more() -> None:
    before, after = _replay(8), _replay(9)
    assert after.openness >= 3 and after.openness > before.openness
    assert after.pace <= before.pace  # slower: the sensitive subject slows the pace


def test_chat3_trust_is_rising_by_the_end_and_never_fell() -> None:
    d = dials.Dials()
    seen = []
    for text in CHAT3:
        d = dials.update(d, text)
        seen.append(d.trust_trend)
    assert seen[-1] == Trust.RISING and Trust.FALLING not in seen


def test_chat3_ends_as_a_talker() -> None:
    assert _replay(len(CHAT3)).openness >= 3
    assert dials.posture(_replay(len(CHAT3))) in {"talker", "hurried"}
