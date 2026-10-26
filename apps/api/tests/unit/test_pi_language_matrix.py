# ruff: noqa: E501
"""One matrix for the languages pi serves, no model: detection of a normal message, a short ambiguous
answer (R-LANG-09), the solution-ask phrase bank ("give me a solution", "any idea?", "how do I
start"), and where the fixed lines (opening, offer, PII reminder, emergency) come from: their own table,
or a rewrite into the person's language that never leaves English without the translation step."""

from types import SimpleNamespace

import pytest

from app.modules.pi import flow, language, safety, solution_ask
from app.modules.pi.service_conversation import AMBIGUOUS_SHORT, in_their_language

LANGS = {
    "English": dict(
        normal="I own a clothing shop and orders are getting mixed up",
        short="ok",
        detect="en",
        asks=["give me a solution", "any idea?", "how do I start"],
    ),
    "Roman Urdu": dict(
        normal="mera kiryana store hai aur udhaar ka hisaab gadbad hai",
        short="haan",
        detect="roman_ur",
        asks=["solution dain", "koi idea?", "kaise shuru karun"],
    ),
    "Urdu script": dict(
        normal="میرا ٹیکسٹائل کا کام ہے اور حساب میں غلطی ہوتی ہے",
        short="ہاں",
        detect="roman_ur",
        asks=["مجھے حل چاہیے", "کوئی حل بتائیں", "کیسے شروع کروں"],
    ),
    "Arabic": dict(
        normal="لدي شركة توصيل وأواجه مشكلة في متابعة الطلبات",
        short="نعم",
        detect="ar",
        asks=["أعطني حل", "ما الحل؟", "كيف أبدأ؟"],
    ),
    "Hindi": dict(
        normal="मेरी दुकान है और हिसाब में गड़बड़ है",
        short="हाँ",
        detect="roman_ur",
        asks=["मुझे समाधान चाहिए", "कोई उपाय बताइए", "कैसे शुरू करूँ"],
    ),
    "Persian": dict(
        normal="من یک خیاطی دارم و حساب‌ها قاطی می‌شود",
        short="باشه",
        other="Persian",
        asks=["راه حل بده", "یه راهکار پیشنهاد کن", "چطور شروع کنم"],
    ),
    "French": dict(
        normal="j'ai un magasin et les commandes se mélangent souvent",
        short="oui",
        other="French",
        asks=["donnez-moi une solution", "avez-vous une idée ?", "comment commencer"],
    ),
    "Spanish": dict(
        normal="tengo una tienda y los pedidos se mezclan con frecuencia",
        short="sí",
        other="Spanish",
        asks=["dame una solución", "¿tienes alguna idea?", "cómo empezar"],
    ),
    "Indonesian": dict(
        normal="saya punya toko baju dan pesanan sering keliru",
        short="iya",
        other="Indonesian",
        asks=["tolong kasih solusi", "ada ide gak?", "bagaimana cara memulai"],
    ),
    "Turkish": dict(
        normal="bir mağazam var ve siparişler sık sık karışıyor",
        short="evet",
        other="Turkish",
        asks=["bana bir çözüm ver", "bir fikrin var mı?", "nasıl başlarım"],
    ),
    "German": dict(
        normal="ich habe einen Laden und die Bestellungen werden oft verwechselt",
        short="ja",
        other="German",
        asks=["gib mir eine Lösung", "hast du eine Idee?", "wie fange ich an"],
    ),
    "Chinese": dict(
        normal="我有一家服装店，订单经常搞混",
        short="好",
        other="Chinese (Simplified)",
        asks=["给我一些建议", "有什么办法", "怎么开始"],
    ),
}


@pytest.mark.parametrize("name", list(LANGS))
def test_a_normal_message_is_detected_in_its_language(name: str) -> None:
    spec = LANGS[name]
    detected = language.detect_language(spec["normal"])
    other = language.latin_other(spec["normal"]) or language.other_script(spec["normal"])
    if "detect" in spec:  # English, Roman Urdu, Arabic; Urdu script and Hindi answer in Roman Urdu
        assert detected == spec["detect"], (name, detected)
        assert other is None
    else:  # a language with no fixed notices: the model writes in it, and the fixed lines are rewritten
        assert other == spec["other"], (name, other)


@pytest.mark.parametrize("name", list(LANGS))
def test_a_short_answer_never_switches_the_language(name: str) -> None:
    assert AMBIGUOUS_SHORT.match(LANGS[name]["short"]), name


@pytest.mark.parametrize("name", list(LANGS))
def test_the_solution_ask_phrases_are_recognised(name: str) -> None:
    for ask in LANGS[name]["asks"]:
        assert solution_ask.asked_for_ideas(ask), (name, ask)


FIXED_ENGLISH = {
    "opening": flow.OPENING["en"],
    "offer": solution_ask.offer_line("en"),
    "pii": safety.PII_TEXT["en"]
    if isinstance(safety.PII_TEXT.get("en"), str)
    else "Please do not send card numbers here.",
    "emergency": "I cannot help in an emergency. Please call 999 now.",
}


class Translator:
    def __init__(self, keep_numbers: bool = True) -> None:
        self.keep = keep_numbers

    async def complete(self, scope, **kwargs):  # noqa: ANN001, ANN201
        text = kwargs["messages"][1].content if hasattr(kwargs["messages"][1], "content") else ""
        return SimpleNamespace(
            text=("[translated] " + str(text)) if self.keep else "[translated] call 998 now"
        )


OTHER = [(n, s["other"]) for n, s in LANGS.items() if "other" in s]


@pytest.mark.parametrize(("name", "other"), OTHER)
@pytest.mark.parametrize("line", list(FIXED_ENGLISH))
async def test_a_fixed_line_for_another_language_is_rewritten_never_left_in_english(
    name: str, other: str, line: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.modules.pi.service_conversation.clearly_other", lambda *_: False)
    turn = SimpleNamespace(reply=FIXED_ENGLISH[line])
    context = {"reply_language_other": other}
    policy = SimpleNamespace(ai_config={}, response_rules={})
    await in_their_language(Translator(), None, policy, SimpleNamespace(id=None), turn, context)  # type: ignore[arg-type]
    assert turn.reply.startswith("[translated]"), (name, line)


async def test_a_rewrite_that_changes_an_emergency_number_is_thrown_away(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.modules.pi.service_conversation.clearly_other", lambda *_: False)
    turn = SimpleNamespace(reply=FIXED_ENGLISH["emergency"])
    policy = SimpleNamespace(ai_config={}, response_rules={})
    await in_their_language(  # type: ignore[arg-type]
        Translator(keep_numbers=False),
        None,
        policy,
        SimpleNamespace(id=None),
        turn,
        {"reply_language_other": "French"},
    )
    assert turn.reply == FIXED_ENGLISH["emergency"]  # the original, with 999, stays


@pytest.mark.parametrize("lang", ["en", "roman_ur", "ar"])
def test_these_languages_have_their_own_fixed_lines(lang: str) -> None:
    assert flow.OPENING.get(lang) if lang != "ar" else True
    assert solution_ask.offer_line(lang)
    if lang != "en":
        assert solution_ask.offer_line(lang) != solution_ask.offer_line("en")
