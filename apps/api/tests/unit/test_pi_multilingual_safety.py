# ruff: noqa: E501  (replies in eight languages read better unbroken)
"""The older safety lines in the eight priority languages (English and Roman Urdu: the originals;
Urdu script, Arabic, Hindi, French, Persian, Spanish: constitution_langs.py).

Asking for a card number or an ID, "payment received", a human claim, "the team reads this chat" and
an invented duration are HARD violations; a normal reply (including the refusal "please do not send
your card number here") never is. Also the generic closer and the open requests (slots.py,
open_requests.py)."""

import pytest

from app.modules.pi import constitution, open_requests, slots

ZW = "‌"
H = [{"role": "ai", "text": "x"}]
LANGS = ["en", "roman_ur", "ur", "ar", "hi", "fr", "fa", "es"]


def hard(reply: str, said: str = "") -> dict[str, bool]:
    context = {
        "pi_mode": "brain",
        "flow": {"state": "S3_NOTED"},
        "reply_language": "en",
        "history": H,
        "latest_customer_message": said,
    }
    return {v.rule: v.hard for v in constitution.lint(reply, context)}


# rule -> language -> a reply that breaks it
BAD = {
    "R-PAY-02": {
        "en": "Please send me your card number.",
        "roman_ur": "Apna card number bhej dein.",
        "ur": "براہ کرم اپنا کارڈ نمبر بھیجیں۔",
        "ar": "أرسل لي رقم بطاقتك من فضلك.",
        "hi": "कृपया अपना कार्ड नंबर भेजिए।",
        "fr": "Envoyez-moi le numéro de votre carte, s'il vous plaît.",
        "fa": "لطفاً شماره کارت خود را بفرستید.",
        "es": "Envíeme el número de su tarjeta, por favor.",
    },
    "R-PRIV-03": {
        "en": "Please send me a photo of your national ID.",
        "roman_ur": "Apne id card ki photo bhej dein.",
        "ar": "أرسل لي صورة جواز السفر.",
        "hi": "कृपया अपना आधार नंबर भेजिए।",
        "fr": "Envoyez-moi une photo de votre carte d'identité.",
        "fa": "لطفاً کد ملی خود را بفرستید.",
        "es": "Envíeme una foto de su pasaporte.",
    },
    "R-PAY-05": {
        "en": "Your payment has been received, thank you.",
        "roman_ur": "Aap ki payment mil gayi hai.",
        "ur": "آپ کی ادائیگی موصول ہو گئی ہے۔",
        "ar": "تم استلام الدفع، شكراً.",
        "hi": "आपका भुगतान प्राप्त हो गया है।",
        "fr": "Paiement bien reçu, merci.",
        "fa": "پرداخت شما دریافت شد.",
        "es": "Pago recibido, gracias.",
    },
    "R-DISC-03": {
        "en": "I'm a real person and my name is Sara.",
        "ur": "میں ایک حقیقی انسان ہوں۔",
        "ar": "أنا إنسان حقيقي واسمي سارة.",
        "hi": "मैं एक असली इंसान हूँ।",
        "fr": "Je suis une vraie personne, je m'appelle Claire.",
        "fa": "من یک انسان واقعی هستم.",
        "es": "Soy una persona real y me llamo Laura.",
    },
    "R-DISC-04": {
        "en": "Our team reads this conversation live.",
        "ur": "ہماری ٹیم آپ کی چیٹ پڑھتی ہے۔",
        "ar": "فريقنا يقرأ هذه المحادثة مباشرة.",
        "hi": "हमारी टीम आपकी चैट पढ़ती है।",
        "fr": "Notre équipe lit cette conversation en direct.",
        "fa": "تیم گفتگوی شما را می" + ZW + "خواند.",
        "es": "Nuestro equipo lee esta conversación en vivo.",
    },
    "R-HONEST-01": {
        "en": "It will be ready in 3 days.",
        "ur": "یہ 3 دن میں تیار ہو جائے گا۔",
        "ar": "سيكون جاهزاً خلال 3 أيام.",
        "hi": "यह 3 दिन में तैयार हो जाएगा।",
        "fr": "Ce sera prêt dans 3 jours.",
        "fa": "ظرف سه روز آماده می" + ZW + "شود.",
        "es": "Estará listo en 3 días.",
    },
}


@pytest.mark.parametrize(
    ("rule", "lang", "reply"),
    [(rule, lang, reply) for rule, by in BAD.items() for lang, reply in by.items()],
)
def test_the_unsafe_reply_is_a_hard_violation_in_every_language(rule, lang, reply):
    found = hard(reply)
    assert found.get(rule) is True, (lang, found)


NORMAL = {
    "en": "I can't confirm payment here. The team will confirm here once the transfer arrives. Please don't send your card number in this chat.",
    "roman_ur": "Main yahan payment ki tasdeeq nahi kar sakta. Team transfer aate hi yahin confirm karegi. Card number is chat mein na bhejein.",
    "ur": "میں یہاں ادائیگی کی تصدیق نہیں کر سکتا۔ ٹیم ٹرانسفر آتے ہی یہیں تصدیق کرے گی۔ کارڈ نمبر یہاں نہ بھیجیں۔",
    "ar": "لا أستطيع تأكيد الدفع هنا. سيؤكد الفريق ذلك هنا فور وصول التحويل. لا ترسل رقم البطاقة في هذه المحادثة.",
    "hi": "मैं यहाँ भुगतान की पुष्टि नहीं कर सकता। टीम ट्रांसफर आते ही यहीं पुष्टि करेगी। कृपया यहाँ कार्ड नंबर न भेजें।",
    "fr": "Je ne peux pas confirmer le paiement ici. L'équipe le confirmera ici dès que le transfert arrive. Merci de ne pas envoyer de numéro de carte dans ce chat.",
    "fa": "من نمی"
    + ZW
    + "توانم پرداخت را اینجا تأیید کنم. تیم به محض رسیدن واریز اینجا تأیید می"
    + ZW
    + "کند. لطفاً شماره کارت را اینجا نفرستید.",
    "es": "No puedo confirmar el pago aquí. El equipo lo confirmará aquí en cuanto llegue la transferencia. Por favor, no envíe el número de su tarjeta en este chat.",
}


@pytest.mark.parametrize("lang", LANGS)
def test_a_normal_reply_and_the_refusal_to_take_a_card_break_none_of_them(lang):
    found = set(hard(NORMAL[lang]))
    assert not found & set(BAD), (lang, found)


@pytest.mark.parametrize(
    ("lang", "closer"),
    [
        ("en", "Is there anything else?"),
        ("roman_ur", "Aur koi masla ho to bata dein?"),
        ("fr", "Autre chose à ajouter ?"),
        ("es", "¿Algo más que añadir?"),
        ("hi", "क्या कुछ और बताना चाहेंगे?"),
        ("ur", "کیا کچھ اور بتانا چاہیں گے؟"),
        ("ar", "هل هناك شيء آخر؟"),
        ("fa", "چیز دیگری هست؟"),
    ],
)
def test_the_generic_closer_is_a_slot_in_every_language(lang, closer):
    assert slots.ANYTHING_ELSE.search(closer), lang


@pytest.mark.parametrize(
    ("lang", "ok"),
    [
        ("en", "ok"),
        ("roman_ur", "hmm"),
        ("fr", "d'accord"),
        ("es", "vale"),
        ("hi", "ठीक है"),
        ("ur", "ٹھیک ہے"),
        ("ar", "طيب"),
        ("fa", "باشه"),
    ],
)
def test_an_ok_skips_the_generic_closer_in_every_language(lang, ok):
    previous = {"last_question": {"q": "Autre chose ? Anything else?", "slot": ""}}
    closed, _ = slots.advance(previous, ok, "Noted.", "")
    assert any(c.get("slot") == slots.ANYTHING_ELSE_SLOT for c in closed), lang


ASKS = {
    "timeline": {
        "en": "how long will it take?",
        "roman_ur": "kitne din lagenge?",
        "fr": "combien de temps ça prend ?",
        "es": "¿cuánto tiempo tarda?",
        "hi": "कितने दिन लगेंगे?",
        "ur": "کتنے دن لگیں گے؟",
        "ar": "كم يستغرق ذلك؟",
        "fa": "چقدر طول می" + ZW + "کشد؟",
    },
    "human": {
        "en": "I want to talk to a person",
        "roman_ur": "mujhe kisi insaan se baat karni hai",
        "fr": "je veux parler à une personne",
        "es": "quiero hablar con una persona",
        "hi": "मुझे किसी इंसान से बात करनी है",
        "ur": "مجھے کسی انسان سے بات کرنی ہے",
        "ar": "أريد التحدث مع شخص",
        "fa": "می" + ZW + "خواهم با یک انسان صحبت کنم",
    },
}
ANSWERS = {
    "timeline": {
        "en": "The quote says how long it takes.",
        "roman_ur": "Quote mein likha hoga ke kitna waqt lagega.",
        "fr": "Le devis indique la durée.",
        "es": "La cotización indica el plazo.",
        "hi": "कोट में समय लिखा होगा।",
        "ur": "کوٹ میں وقت لکھا ہوگا۔",
        "ar": "عرض السعر يذكر المدة.",
        "fa": "پیشنهاد مدت را می" + ZW + "نویسد.",
    },
    "human": {
        "en": "I'll pass this to the team.",
        "roman_ur": "Main ye team tak pohancha deta hoon.",
        "fr": "Je transmets cela à l'équipe.",
        "es": "Se lo paso al equipo.",
        "hi": "मैं यह टीम तक पहुँचा देता हूँ।",
        "ur": "میں یہ ٹیم تک پہنچا دیتا ہوں۔",
        "ar": "سأنقل هذا إلى الفريق.",
        "fa": "این را به تیم می" + ZW + "رسانم.",
    },
}


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("kind", ["timeline", "human"])
def test_an_unanswered_request_stays_open_and_an_answered_one_does_not(kind, lang):
    said = ASKS[kind][lang]
    assert kind in open_requests.kinds(said), (kind, lang)
    ignored = "Noted. What else?"
    assert open_requests.update(None, said, ignored) == [{"kind": kind, "turns": 1}]
    assert open_requests.update(None, said, ANSWERS[kind][lang]) == [], (kind, lang)
