# ruff: noqa: E501
"""A language the owner asked for or wrote drives EVERY reply of the turn (live faults 2026-11-01):
Persian answered in English, Italian answered in English and Roman Urdu, Dari/Pashto claimed."""

import asyncio
from types import SimpleNamespace as N

from app.modules.pi import fixed_lines
from app.modules.pi import service_conversation as sc
from app.modules.pi.language import asked_language, declared_languages


def msg(body, who="customer"):
    return N(body=body, message_type="text", sender_type=who)


def lang(text, conversation=None, rows=()):
    conversation = conversation if conversation is not None else N(service_brief={})
    return sc.reply_language(conversation, msg(text), list(rows)), conversation


def has_arabic_script(text):
    return sum("؀" <= ch <= "ۿ" for ch in text) > len(text) // 3


class Manager:
    """Answers the model's rewrite call with the next canned text (the last one repeats)."""

    def __init__(self, *texts):
        self.texts = list(texts)
        self.calls = 0

    async def complete(self, *args, **kwargs):
        self.calls += 1
        text = self.texts[min(self.calls - 1, len(self.texts) - 1)]
        return N(text=text)


POLICY = N(ai_config={}, response_rules={})


def guard(turn, context, manager):
    asyncio.run(sc.pre_send_guard(turn, context, manager, None, POLICY, N(id=None)))


def ctx(message, other=None, **extra):
    c = {"pi_mode": "brain", "latest_customer_message": message, **extra}
    if other:
        c["reply_language_other"] = other
    else:
        c["reply_language"] = "en"
    return c


# ---- 1. Persian


def test_persian_requests_in_persian_script_choose_persian():
    for text in ["میشه فارسی گپ بزنی", "حالا فارسی بگو", "فارسی بگو", "سلام فارسی"]:
        assert lang(text)[0].get("reply_language_other") == "Persian", text


def test_an_english_request_for_persian_is_remembered_for_the_chat():
    first, conversation = lang("can you speak in persian please")
    assert first == {"reply_language_other": "Persian"}
    assert conversation.service_brief["requested_language"] == "Persian"
    later, _ = lang("what do you need from me", conversation)
    assert later == {"reply_language_other": "Persian"}  # not English any more


def test_asking_for_english_again_clears_the_request():
    _, conversation = lang("speak in persian")
    back, _ = lang("please talk in english", conversation)
    assert back["reply_language"] == "en"
    assert "requested_language" not in conversation.service_brief


def test_persian_reply_to_a_persian_owner_is_written_in_persian_when_the_draft_is_english():
    c = ctx("حالا فارسی بگو", other="Persian")
    t = sc.ServiceTurn(
        reply="Yes, we can speak in Persian. I am pi, an AI from Workzap. What is the biggest problem in your business?"
    )
    manager = Manager(
        "بله، می‌توانیم فارسی صحبت کنیم. من pi هستم، یک هوش مصنوعی از Workzap. بزرگ‌ترین مشکل کسب‌وکارتان چیست؟"
    )
    guard(t, c, manager)
    assert has_arabic_script(t.reply) and "Yes, we" not in t.reply and manager.calls >= 1


def test_a_failed_review_for_a_persian_owner_never_sends_the_english_fallback_line():
    c = ctx("لطفا سیستم یادآور", other="Persian")
    t = sc.ServiceTurn(reply="Yes, your reminder system has been delivered and is live now.")
    manager = Manager(
        "این فقط یک پیشنهاد است و هنوز چیزی را شروع نکرده‌ام. کدام بخش را اول بررسی کنیم؟"
    )
    guard(t, c, manager)
    assert has_arabic_script(t.reply)
    assert "suggestion so far" not in t.reply and "delivered" not in t.reply


# ---- 2. Italian


def test_italian_request_then_italian_and_unrelated_looking_messages_stay_italian():
    first, conversation = lang("talk in italian please")
    assert first == {"reply_language_other": "Italian"}
    for text in [
        "ma su che cosa mi aiuti",
        "ma quale attivita",
        "mma a me va bene tutto... devo fare i compiti",
        "ok",
    ]:
        got, _ = lang(text, conversation)
        assert got == {"reply_language_other": "Italian"}, text


def test_evident_italian_without_any_request_is_italian_not_english_or_roman_urdu():
    for text in ["ma su che cosa mi aiuti", "ma quale attivita"]:
        assert lang(text)[0] == {"reply_language_other": "Italian"}, text


def test_fixed_lines_for_a_language_without_a_table_are_not_the_detectors_guess():
    context = {
        "reply_language_other": "Italian",
        "language_decision": {"key": "roman_ur", "uncertain": False},
        "latest_customer_message": "ma quale attivita",
    }
    assert fixed_lines.code(context) == "en"  # the base text; the net writes it in Italian
    assert fixed_lines.code({**context, "reply_language_other": "Persian"}) == "fa"


def test_an_english_question_for_an_italian_owner_is_written_in_italian():
    c = ctx("ma quale attivita", other="Italian")
    t = sc.ServiceTurn(reply="What is the biggest problem in your business right now?")
    manager = Manager("Qual è il problema più grande della tua attività in questo momento?")
    guard(t, c, manager)
    assert t.reply.startswith("Qual") and manager.calls == 1


def test_a_roman_urdu_reply_to_an_italian_owner_is_written_in_italian():
    c = ctx("ma quale attivita", other="Italian")
    t = sc.ServiceTurn(
        reply="Shukriya, ye baat mere paas hai. Is mein sab se zyada nuqsan kis baat ka ho raha hai?"
    )
    guard(t, c, Manager("Grazie, questo lo so già. Qual è la cosa che ti fa perdere di più?"))
    assert t.reply.startswith("Grazie")


def test_when_the_model_cannot_write_the_language_the_reply_says_so_in_english():
    c = ctx("ma quale attivita", other="Italian")
    t = sc.ServiceTurn(reply="What is the biggest problem in your business right now?")
    guard(t, c, Manager("What is the biggest problem in your business right now?"))
    assert t.reply.startswith("I could not write this in Italian just now")
    assert "Shukriya" not in t.reply and t.reply.count("?") == 1


# ---- 3. Dari and Pashto


def test_declared_languages_are_read_from_a_statement():
    assert declared_languages("I con not English speaking. just pashto and dari") == [
        "Pashto",
        "Persian",
    ]
    assert asked_language("farsi please") == "Persian"
    assert declared_languages("I run a shop in Okara") == []


def test_pashto_and_dari_gives_dari_as_persian_and_an_honest_line_about_pashto():
    got, conversation = lang("I con not English speaking. just pashto and dari")
    assert got == {"reply_language_other": "Persian", "language_unsupported": "Pashto"}
    assert conversation.service_brief["requested_language"] == "Persian"
    t = sc.ServiceTurn(reply="سلام، من pi هستم. مشکل اصلی کسب‌وکارتان چیست؟")
    sc.language_notice(t, {**got})
    assert has_arabic_script(t.reply.split("\n")[0]) and "Pashto" not in t.reply.split("\n")[0]


def test_pashto_alone_is_never_claimed_the_reply_stays_english_with_an_honest_line():
    got, conversation = lang("please talk in pashto")
    assert got["reply_language"] == "en" and got["language_unsupported"] == "Pashto"
    assert "requested_language" not in conversation.service_brief
    t = sc.ServiceTurn(
        reply="Hello, I am pi, an AI from Workzap. What is the biggest problem in your business?"
    )
    sc.language_notice(t, got)
    assert t.reply.startswith("I can't write Pashto well enough") and "Dari" in t.reply
    assert t.reply.count("?") == 1
