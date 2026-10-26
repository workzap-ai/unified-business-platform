# ruff: noqa: E501  (replies in six languages read better unbroken)
"""The reply linter's newer rules in Urdu script, Arabic, Hindi, French, Spanish and Persian.

Two checks per language: a normal reply breaks no rule (no misfire), and the reply the rule is for
is caught. Roman Urdu and English have their own tests (test_pi_live_chat_openers.py,
test_pi_answer_first_and_tone.py, test_pi_secrets.py)."""

import pytest

from app.modules.pi import constitution

H = [{"role": "ai", "text": "x"}]
ZW = "‌"


def lint(reply: str, said: str = "", state: str = "S3_NOTED", language: str = "en") -> set[str]:
    first = state == "S0_NEW"
    context = {
        "pi_mode": "brain",
        "flow": {"state": state},
        "reply_language": language,
        "history": [] if first else H,
        "latest_customer_message": said,
    }
    return {v.rule for v in constitution.lint(reply, context)}


# (language, first message, noted reply, what the person said, ideas reply)
NORMAL = {
    "en": (
        "Hi, I'm pi, an AI from Workzap. Tell me what's going wrong in your business and I'll start on it.",
        "Noted: customers are not coming back. How long has this been happening?",
        "customers have not come back for a month now",
    ),
    "roman_ur": (
        "Hi, main pi hoon, Workzap ka AI. Apne business ka masla batayein.",
        "Note kar liya, customers wapis nahi aa rahe. Ye kab se ho raha hai?",
        "customers ek mahine se wapis nahi aa rahe",
    ),
    "fr": (
        "Salut, je suis pi, une IA de Workzap. Dites-moi ce qui ne va pas dans votre activité et je m'en occupe.",
        "Noté : les clients ne reviennent pas. Depuis quand est-ce que cela dure ?",
        "les clients ne reviennent plus depuis un mois",
    ),
    "es": (
        "Hola, soy pi, una IA de Workzap. Cuénteme qué no va bien en su negocio y empiezo por ahí.",
        "Anotado: los clientes no vuelven. ¿Desde cuándo pasa esto?",
        "los clientes ya no vuelven desde hace un mes",
    ),
    "hi": (
        "नमस्ते, मैं pi हूँ, Workzap की ओर से एक AI। अपने बिज़नेस की समस्या बताइए।",
        "नोट कर लिया, ग्राहक वापस नहीं आ रहे। यह कब से हो रहा है?",
        "ग्राहक एक महीने से वापस नहीं आ रहे हैं",
    ),
    "ur": (
        "ہیلو، میں pi ہوں، Workzap کی طرف سے ایک مصنوعی ذہانت۔ اپنے کاروبار کا مسئلہ بتائیں۔",
        "نوٹ کر لیا، گاہک واپس نہیں آ رہے۔ یہ کب سے ہو رہا ہے؟",
        "گاہک ایک مہینے سے واپس نہیں آ رہے",
    ),
    "ar": (
        "مرحباً، أنا pi، ذكاء اصطناعي من Workzap. أخبرني ما الذي لا يسير على ما يرام في عملك.",
        "تم تسجيل ذلك: الزبائن لا يعودون. منذ متى يحدث هذا؟",
        "الزبائن لا يعودون منذ شهر كامل",
    ),
    "fa": (
        "سلام، من pi هستم، یک هوش مصنوعی از Workzap. مشکل کسب" + ZW + "وکارتان را بگویید.",
        "ثبت شد، مشتریان برنمی" + ZW + "گردند. این از کی شروع شده است؟",
        "مشتریان یک ماه است برنمی" + ZW + "گردند",
    ),
}


@pytest.mark.parametrize("lang", NORMAL)
def test_a_normal_reply_breaks_no_rule(lang):
    first, noted, said = NORMAL[lang]
    assert lint(first, state="S0_NEW") == set(), lang
    assert lint(noted, said) == set(), lang


@pytest.mark.parametrize(
    "reply",
    [
        "Je ne peux pas vous donner de garantie, mais le devis dit combien de temps cela prend. Quelle boutique vend le moins ?",
        "No puedo darle ninguna garantía, pero la cotización dice cuánto tarda. ¿Qué tienda vende menos?",
        "मैं कोई गारंटी नहीं दे सकता, पर कोट में समय लिखा होगा। कौन सी दुकान कम बिकती है?",
        "ہم کوئی گارنٹی نہیں دے سکتے، مگر کوٹ میں وقت لکھا ہوگا۔ کون سی دکان کم بکتی ہے؟",
        "لا يمكننا ضمان أي نتيجة، لكن العرض يذكر المدة. أي فرع يبيع أقل؟",
        "نمی"
        + ZW
        + "توانیم تضمین بدهیم، اما پیشنهاد مدت را می"
        + ZW
        + "نویسد. کدام شعبه کمتر می"
        + ZW
        + "فروشد؟",
    ],
)
def test_a_refusal_of_a_guarantee_is_not_a_promise(reply):
    assert "R-PROM-01" not in lint(reply, "pouvez-vous garantir ?")


BAD = [
    # (rule, language, reply, what they said)
    ("R-TONE-01", "fr", "C'est un vrai problème. Depuis quand cela dure-t-il ?", ""),
    ("R-TONE-01", "es", "Es un problema real. ¿Desde cuándo pasa esto?", ""),
    ("R-TONE-01", "hi", "यह एक असली समस्या है। यह कब से हो रहा है?", ""),
    ("R-TONE-01", "ur", "یہ ایک حقیقی مسئلہ ہے۔ یہ کب سے ہو رہا ہے؟", ""),
    ("R-TONE-01", "ar", "هذه مشكلة حقيقية. منذ متى يحدث هذا؟", ""),
    ("R-TONE-01", "fa", "این یک مشکل واقعی است. از کی شروع شده است؟", ""),
    ("R-TONE-01", "fr", "Votre entreprise va mal. Depuis quand ?", ""),
    ("R-TONE-01", "es", "Su negocio va mal. ¿Desde cuándo?", ""),
    ("R-TONE-01", "hi", "आपका धंधा खराब है। यह कब से है?", ""),
    ("R-TONE-01", "ur", "آپ کا کاروبار خراب ہے۔ یہ کب سے ہے؟", ""),
    ("R-TONE-01", "ar", "عملك فاشل. منذ متى؟", ""),
    ("R-TONE-01", "fa", "کسب" + ZW + "وکار شما بد است. از کی؟", ""),
    ("R-TONE-03", "fr", "Veuillez patienter, je note tout. Depuis quand ?", "c'est trop lent"),
    ("R-TONE-03", "es", "Tenga paciencia, estoy anotando. ¿Desde cuándo?", "es muy lento"),
    ("R-TONE-03", "hi", "कृपया धैर्य रखें। यह कब से हो रहा है?", "बहुत देर हो गई"),
    ("R-TONE-03", "ur", "براہ کرم صبر کریں۔ یہ کب سے ہو رہا ہے؟", "بہت دیر ہو گئی"),
    ("R-TONE-03", "ar", "يرجى التحلي بالصبر. منذ متى يحدث هذا؟", "تأخرتم كثيراً"),
    ("R-TONE-03", "fa", "لطفاً صبور باشید. از کی شروع شده؟", "خیلی دیر شد"),
    (
        "R-ASK-05",
        "fr",
        "Noté : les clients ne reviennent pas. Autre chose à ajouter ?",
        "les clients ne reviennent plus depuis un mois",
    ),
    (
        "R-ASK-05",
        "es",
        "Anotado: los clientes no vuelven. ¿Algo más que añadir?",
        "los clientes ya no vuelven desde hace un mes",
    ),
    (
        "R-ASK-05",
        "hi",
        "नोट कर लिया, ग्राहक वापस नहीं आ रहे। क्या कुछ और बताना चाहेंगे?",
        "ग्राहक एक महीने से वापस नहीं आ रहे हैं",
    ),
    (
        "R-ASK-05",
        "ur",
        "نوٹ کر لیا۔ کیا کچھ اور بتانا چاہیں گے؟",
        "گاہک ایک مہینے سے واپس نہیں آ رہے ہیں",
    ),
    ("R-ASK-05", "ar", "تم تسجيل ذلك. هل هناك شيء آخر؟", "الزبائن لا يعودون منذ شهر كامل تقريباً"),
    ("R-ASK-05", "fa", "ثبت شد. چیز دیگری هست؟", "مشتریان یک ماه است که برنمی" + ZW + "گردند"),
    (
        "R-ECHO-01",
        "fr",
        "Noté : les clients ne reviennent plus, les ventes baissent chaque semaine, le stock est plein et les employés partent un par un. Depuis quand ?",
        "",
    ),
    (
        "R-ECHO-01",
        "es",
        "Anotado: los clientes ya no vuelven, las ventas bajan cada semana, el stock está lleno y los empleados se van uno por uno. ¿Desde cuándo?",
        "",
    ),
    (
        "R-ECHO-01",
        "hi",
        "नोट कर लिया: ग्राहक वापस नहीं आ रहे हैं और बिक्री हर हफ्ते घट रही है और स्टॉक भी भरा पड़ा है। यह कब से है?",
        "",
    ),
    (
        "R-ECHO-01",
        "ur",
        "نوٹ کر لیا: گاہک واپس نہیں آ رہے ہیں اور سیل ہر ہفتے کم ہو رہی ہے اور اسٹاک بھی بھرا پڑا ہے۔ یہ کب سے ہے؟",
        "",
    ),
    (
        "R-ECHO-01",
        "ar",
        "تم تسجيل ذلك: الزبائن لا يعودون والمبيعات تنخفض كل أسبوع والمخزون ممتلئ والموظفون يغادرون واحداً تلو الآخر. منذ متى؟",
        "",
    ),
    (
        "R-ECHO-01",
        "fa",
        "ثبت شد: مشتریان برنمی"
        + ZW
        + "گردند و فروش هر هفته کم می"
        + ZW
        + "شود و انبار پر است و کارمندان یکی یکی می"
        + ZW
        + "روند و هزینه"
        + ZW
        + "ها بالاست: از کی؟",
        "",
    ),
    ("R-ECHO-01", "ur", "شکریہ۔ میں نے نوٹ کر لیا۔ یہ کب سے ہو رہا ہے؟", ""),
    (
        "A2-1.5-SECRETS",
        "fr",
        "Nous utilisons OpenAI pour écrire le devis. Quelle boutique vend le moins ?",
        "",
    ),
    (
        "A2-1.5-SECRETS",
        "es",
        "Usamos OpenAI para escribir la cotización. ¿Qué tienda vende menos?",
        "",
    ),
    ("A2-1.5-SECRETS", "hi", "हम OpenAI का उपयोग करते हैं। कौन सी दुकान कम बिकती है?", ""),
    ("A2-1.5-SECRETS", "ur", "ہم OpenAI استعمال کرتے ہیں۔ کون سی دکان کم بکتی ہے؟", ""),
    ("A2-1.5-SECRETS", "ar", "نستخدم OpenAI لكتابة العرض. أي فرع يبيع أقل؟", ""),
    (
        "A2-1.5-SECRETS",
        "fa",
        "ما از OpenAI استفاده می" + ZW + "کنیم. کدام شعبه کمتر می" + ZW + "فروشد؟",
        "",
    ),
    (
        "A2-1.5-SECRETS",
        "fr",
        "Notre logique de tarification dépend de votre taille. Quelle boutique ?",
        "",
    ),
    ("A2-1.5-SECRETS", "es", "Nuestra lógica de precios depende de su tamaño. ¿Qué tienda?", ""),
    ("A2-1.5-SECRETS", "hi", "प्राइसिंग लॉजिक आपके साइज़ पर निर्भर है। कौन सी दुकान?", ""),
    ("A2-1.5-SECRETS", "ur", "پرائسنگ لاجک آپ کے سائز پر ہے۔ کون سی دکان؟", ""),
    ("A2-1.5-SECRETS", "ar", "منطق التسعير يعتمد على حجمكم. أي فرع؟", ""),
    (
        "A2-1.5-SECRETS",
        "fa",
        "منطق قیمت" + ZW + "گذاری ما به اندازه شما بستگی دارد. کدام شعبه؟",
        "",
    ),
    ("R-PROM-01", "fr", "Vos ventes vont augmenter dès le mois prochain. Quelle boutique ?", ""),
    ("R-PROM-01", "fr", "Nous garantissons de nouveaux clients. Quelle boutique ?", ""),
    ("R-PROM-01", "es", "Las ventas aumentarán el próximo mes. ¿Qué tienda?", ""),
    ("R-PROM-01", "es", "Le garantizo nuevos clientes. ¿Qué tienda?", ""),
    ("R-PROM-01", "hi", "आपकी बिक्री बढ़ेगी। कौन सी दुकान?", ""),
    ("R-PROM-01", "hi", "हम नए ग्राहकों की गारंटी देते हैं। कौन सी दुकान?", ""),
    ("R-PROM-01", "ur", "آپ کی فروخت بڑھے گی۔ کون سی دکان؟", ""),
    ("R-PROM-01", "ur", "ہم نئے گاہکوں کی گارنٹی دیتے ہیں۔ کون سی دکان؟", ""),
    ("R-PROM-01", "ar", "ستزيد المبيعات في الشهر القادم. أي فرع؟", ""),
    ("R-PROM-01", "ar", "نضمن لك عملاء جدد. أي فرع؟", ""),
    ("R-PROM-01", "fa", "فروش شما حتماً افزایش می" + ZW + "یابد. کدام شعبه؟", ""),
    ("R-PROM-01", "fa", "ما مشتری جدید تضمین می" + ZW + "کنیم. کدام شعبه؟", ""),
]


@pytest.mark.parametrize(("rule", "lang", "reply", "said"), BAD)
def test_the_rule_catches_its_reply_in_every_language(rule, lang, reply, said):
    assert rule in lint(reply, said, language=lang), (lang, reply)


YES_NO = {
    "fr": ("pouvez-vous m'aider ?", "Merci, c'est noté. Quelle boutique vend le moins ?"),
    "es": ("¿puede ayudarme?", "Gracias, anotado. ¿Qué tienda vende menos?"),
    "hi": ("क्या आप मदद कर सकते हैं?", "धन्यवाद, नोट कर लिया। कौन सी दुकान सबसे कम बिकती है?"),
    "ur": ("کیا آپ مدد کر سکتے ہیں؟", "شکریہ، نوٹ کر لیا۔ کون سی دکان کم بکتی ہے؟"),
    "ar": ("هل يمكنك مساعدتي؟", "شكراً، تم تسجيل ذلك. أي فرع يبيع أقل؟"),
    "fa": ("آیا می" + ZW + "توانید کمک کنید؟", "ممنون، ثبت شد. کدام شعبه کمتر می" + ZW + "فروشد؟"),
}


@pytest.mark.parametrize("lang", YES_NO)
def test_a_thank_you_is_not_the_answer_to_a_yes_no_question(lang):
    said, reply = YES_NO[lang]
    assert "R-ANS-02" in lint(reply, said, language=lang)


@pytest.mark.parametrize("lang", ["fr", "es", "hi", "ur", "ar", "fa"])
def test_a_question_back_is_not_the_answer_to_a_question(lang):
    question = {
        "fr": "Quelle boutique vend le moins ?",
        "es": "¿Qué tienda vende menos?",
        "hi": "कौन सी दुकान कम बिकती है?",
        "ur": "کون سی دکان کم بکتی ہے؟",
        "ar": "أي فرع يبيع أقل؟",
        "fa": "کدام شعبه کمتر می" + ZW + "فروشد؟",
    }[lang]
    assert "R-ANS-01" in lint(question, "combien de temps ça prend ?", language=lang)


@pytest.mark.parametrize(
    ("lang", "reply"),
    [
        ("fr", "Voici deux idées à essayer. Quelle boutique vend le moins ? Et depuis quand ?"),
        ("es", "Aquí tiene dos ideas. ¿Qué tienda vende menos? ¿Y desde cuándo?"),
        ("hi", "ये दो विचार हैं। कौन सी दुकान कम बिकती है? और यह कब से है?"),
        ("ur", "یہ دو خیال ہیں۔ کون سی دکان کم بکتی ہے؟ اور یہ کب سے ہے؟"),
        ("ar", "هاتان فكرتان. أي فرع يبيع أقل؟ ومنذ متى؟"),
        ("fa", "این دو ایده است. کدام شعبه کمتر می" + ZW + "فروشد؟ و از کی؟"),
    ],
)
def test_two_questions_are_one_too_many_in_every_language(lang, reply):
    assert "R-VOICE-02" in lint(reply, language=lang)


@pytest.mark.parametrize(
    ("lang", "reply"),
    [
        (
            "fr",
            "Voici deux idées à essayer. Souhaitez-vous le document de solution et le devis ? Vous pouvez refuser.",
        ),
        (
            "es",
            "Aquí tiene dos ideas. ¿Quiere el documento de solución y la cotización? Puede decir que no.",
        ),
        ("hi", "ये दो विचार हैं। क्या आप सॉल्यूशन डॉक्यूमेंट और कोट चाहेंगे? आप मना भी कर सकते हैं।"),
        ("ur", "یہ دو خیال ہیں۔ کیا آپ سولیوشن ڈاکیومنٹ اور کوٹ چاہیں گے؟ آپ منع بھی کر سکتے ہیں۔"),
    ],
)
def test_the_offer_tail_in_another_language_is_not_a_second_question_slot(lang, reply):
    assert "R-VOICE-02" not in lint(reply, language=lang)
