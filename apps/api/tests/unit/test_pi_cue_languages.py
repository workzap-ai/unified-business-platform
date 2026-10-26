# ruff: noqa: E501  (the owners' phrases read better unbroken)
"""The router finds the library category from the owner's own words in the eight priority languages.

The same 14 common problems as tests/unit/test_pi_cross_industry_routing.py, put in Hindi, Urdu,
Arabic, French, Persian and Spanish, and a second wording of each in English and Roman Urdu that
the cue words were not written from. Words alone (no category from the model). Add phrases; never
edit one to make it pass."""

import pytest

from app.modules.pi import solution_library as lib

# category -> {language: phrase}
PHRASES: dict[str, dict[str, str]] = {
    "loss_security": {
        "en2": "someone at the counter is taking money from the till",
        "ro2": "galla se paisay ghaib ho rahe hain, shak hai kisi worker par, chori ka dar hai",
        "hi": "मुझे लगता है कर्मचारी चोरी कर रहे हैं और माल कम निकलता है",
        "ur": "مجھے لگتا ہے عملہ چوری کر رہا ہے اور مال کم نکلتا ہے",
        "ar": "أظن أن الموظفين يسرقون والبضاعة تختفي",
        "fr": "je pense que mes employés volent et que la marchandise disparaît",
        "fa": "فکر می‌کنم کارمندانم دزدی می‌کنند و کالا گم می‌شود",
        "es": "creo que mis empleados roban y que la mercancía desaparece",
    },
    "cash_collections": {
        "en2": "clients owe me a lot of money and I cannot collect it",
        "ro2": "bohat se log udhaar le gaye hain aur paisay wapas nahi karte",
        "hi": "ग्राहक देर से भुगतान करते हैं और मैं बार-बार वसूली के लिए पीछे पड़ता हूँ",
        "ur": "گاہک ادائیگی دیر سے کرتے ہیں اور میں بار بار وصولی کے لیے پیچھے پڑتا ہوں",
        "ar": "العملاء يتأخرون في الدفع وأنا أطارد المتأخرات باستمرار",
        "fr": "mes clients paient en retard et je dois sans cesse relancer pour être payé",
        "fa": "مشتری‌ها دیر پرداخت می‌کنند و من مدام باید پیگیری وصول کنم",
        "es": "los clientes pagan tarde y tengo que estar cobrando todo el tiempo",
    },
    "stock_inventory": {
        "en2": "we ordered too much and the goods are sitting unsold in the godown",
        "ro2": "godown mein bohat maal bik nahi raha aur expiry ka dar hai",
        "hi": "मेरा बहुत सारा माल गोदाम में पड़ा है और बिक नहीं रहा",
        "ur": "میرا بہت سارا مال گودام میں پڑا ہے اور بک نہیں رہا",
        "ar": "لدي الكثير من البضاعة الراكدة في المستودع ولا تُباع",
        "fr": "j'ai beaucoup de stock invendu dans l'entrepôt",
        "fa": "کالای زیادی در انبار مانده و فروش نمی‌رود",
        "es": "tengo mucho stock sin vender en el almacén",
    },
    "sales_revenue": {
        "en2": "buyers ask about the price in DM and then stop replying",
        "ro2": "log rate poochte hain aur phir reply dena band kar dete hain, sale nahi ho rahi",
        "hi": "लोग कीमत पूछते हैं और फिर जवाब ही नहीं देते, ऑर्डर नहीं आते",
        "ur": "لوگ قیمت پوچھتے ہیں پھر جواب ہی نہیں دیتے، آرڈر نہیں آتے",
        "ar": "الناس يسألون عن السعر ثم لا يردون ولا يطلبون",
        "fr": "les gens demandent le prix puis ne répondent plus et ne commandent pas",
        "fa": "مردم قیمت را می‌پرسند و بعد جواب نمی‌دهند و سفارش نمی‌دهند",
        "es": "la gente pregunta el precio y luego no responde ni compra",
    },
    "marketing_leads": {
        "en2": "my reels get thousands of views but nobody messages to ask",
        "ro2": "instagram par views bohat hain magar koi inquiry nahi karta",
        "hi": "मैं विज्ञापन चलाता हूँ, व्यूज आते हैं पर इंक्वायरी नहीं आती",
        "ur": "میں اشتہار چلاتا ہوں ویوز آتے ہیں لیکن انکوائری نہیں آتی",
        "ar": "أنشر إعلانات وتأتي مشاهدات لكن لا توجد استفسارات",
        "fr": "je fais de la publicité, j'ai des vues mais pas de demandes",
        "fa": "تبلیغ می‌کنم بازدید می‌آید ولی پرسشی نمی‌آید",
        "es": "hago anuncios y tengo vistas pero ninguna consulta",
    },
    "customers_retention": {
        "en2": "people try us once and we never see them again",
        "ro2": "gahak ek baar aata hai aur phir kabhi wapas nahi aata",
        "hi": "ग्राहक एक बार खरीदते हैं और दोबारा नहीं आते",
        "ur": "گاہک ایک بار خریدتے ہیں اور دوبارہ نہیں آتے",
        "ar": "العملاء يشترون مرة واحدة ولا يعودون",
        "fr": "les clients achètent une fois et ne reviennent pas",
        "fa": "مشتری‌ها یک بار می‌خرند و برنمی‌گردند",
        "es": "los clientes compran una vez y no vuelven",
    },
    "orders_fulfilment": {
        "en2": "many parcels come back undelivered and the courier is always late",
        "ro2": "parcel wapas aa jate hain aur rider delivery mein der karta hai",
        "hi": "पार्सल वापस आ जाते हैं और डिलीवरी में देरी होती है",
        "ur": "پارسل واپس آ جاتے ہیں اور ڈیلیوری میں دیر ہوتی ہے",
        "ar": "الطرود ترجع والتوصيل متأخر",
        "fr": "les colis reviennent et les livraisons sont en retard",
        "fa": "بسته‌ها مرجوع می‌شوند و تحویل دیر است",
        "es": "los paquetes vuelven devueltos y las entregas llegan tarde",
    },
    "people_staff": {
        "en2": "employees are absent without notice and nobody knows who is on shift",
        "ro2": "staff ki attendance ka masla hai aur tankhwah par jhagre hote hain",
        "hi": "स्टाफ देर से आता है और शिफ्ट में गड़बड़ है",
        "ur": "اسٹاف دیر سے آتا ہے اور شفٹ کا مسئلہ ہے",
        "ar": "الموظفون يتأخرون ونظام الورديات فوضى",
        "fr": "le personnel arrive en retard et les horaires sont un désordre",
        "fa": "کارمندان دیر می‌آیند و شیفت‌ها به هم ریخته است",
        "es": "el personal llega tarde y los turnos son un caos",
    },
    "suppliers_purchasing": {
        "en2": "our wholesaler keeps changing rates and delays every purchase order",
        "ro2": "supplier waqt par maal nahi bhejta aur quality bhi kabhi theek nahi hoti",
        "hi": "मेरा सप्लायर देर से माल देता है और क्वालिटी बदलती रहती है",
        "ur": "میرا سپلائر دیر سے مال دیتا ہے اور معیار بدلتا رہتا ہے",
        "ar": "المورد يتأخر في التسليم وتتغير الجودة",
        "fr": "mon fournisseur livre en retard et la qualité change",
        "fa": "تامین‌کننده من دیر تحویل می‌دهد و کیفیت تغییر می‌کند",
        "es": "mi proveedor entrega tarde y la calidad cambia",
    },
    "margin_cost": {
        "en2": "expenses are eating all the profit and the margin keeps shrinking",
        "ro2": "munafa nahi bachta kyun ke kharcha bohat zyada hai",
        "hi": "खर्च बढ़ता जा रहा है और मुनाफा कम हो रहा है",
        "ur": "خرچہ بڑھتا جا رہا ہے اور منافع کم ہو رہا ہے",
        "ar": "التكاليف ترتفع والربح ينخفض",
        "fr": "mes coûts augmentent et mon bénéfice baisse",
        "fa": "هزینه‌ها بالا می‌رود و سود کم می‌شود",
        "es": "mis costos suben y mi ganancia baja",
    },
    "quality_complaints": {
        "en2": "customers send back damaged goods and we redo the work",
        "ro2": "customers ki shikayat aati hai kyun ke product kharab nikalta hai",
        "hi": "ग्राहक खराब प्रोडक्ट की शिकायत करते हैं",
        "ur": "گاہک خراب پروڈکٹ کی شکایت کرتے ہیں",
        "ar": "العملاء يشتكون من منتجات معيبة",
        "fr": "les clients se plaignent de produits défectueux",
        "fa": "مشتری‌ها از محصولات معیوب شکایت می‌کنند",
        "es": "los clientes se quejan de productos defectuosos",
    },
    "operations_process": {
        "en2": "there is no proper process and every job is a bottleneck waiting for me",
        "ro2": "kaam ka koi tareeqa nahi hai aur sab uljha hua hai, sab mujh par",
        "hi": "सब कुछ मुझ पर निर्भर है और काम सुस्त और उलझा है",
        "ur": "سب کچھ مجھ پر ہے اور کام سست اور الجھا ہوا ہے",
        "ar": "كل شيء يعتمد علي والعمل بطيء وفوضوي",
        "fr": "tout dépend de moi et le travail est lent et désorganisé",
        "fa": "همه چیز به من وابسته است و کار کند و نابسامان است",
        "es": "todo depende de mí y el trabajo es lento y desordenado",
    },
    "tech_systems": {
        "en2": "the same entries go into excel and the software and the records never agree",
        "ro2": "hum excel aur software mein aik hi data dobara likhte hain aur record mel nahi khate",
        "hi": "हम एक ही डेटा कई जगह लिखते हैं और रिकॉर्ड मेल नहीं खाते",
        "ur": "ہم ایک ہی ڈیٹا کئی جگہ لکھتے ہیں اور ریکارڈ میل نہیں کھاتے",
        "ar": "ندخل نفس البيانات في أماكن كثيرة والسجلات لا تتطابق",
        "fr": "nous saisissons les mêmes données partout et les enregistrements ne concordent pas",
        "fa": "همان داده را در جاهای زیادی وارد می‌کنیم و سوابق نمی‌خواند",
        "es": "escribimos los mismos datos en muchos lugares y los registros no coinciden",
    },
    "communication_coordination": {
        "en2": "instructions get buried in the groups and nobody knows who is doing what",
        "ro2": "groups mein messages kho jate hain aur kisi ko pata nahi kaun kya kar raha hai",
        "hi": "ग्रुप में मैसेज खो जाते हैं और किसी को पता नहीं कौन क्या कर रहा है",
        "ur": "گروپ میں پیغامات کھو جاتے ہیں اور کسی کو پتا نہیں کون کیا کر رہا ہے",
        "ar": "الرسائل تضيع في المجموعات ولا أحد يعرف من يفعل ماذا",
        "fr": "les messages se perdent dans les groupes et personne ne sait qui fait quoi",
        "fa": "پیام‌ها در گروه‌ها گم می‌شود و هیچ‌کس نمی‌داند چه کسی چه می‌کند",
        "es": "los mensajes se pierden en los grupos y nadie sabe quién hace qué",
    },
}
CASES = [
    (category, language, phrase)
    for category, phrases in PHRASES.items()
    for language, phrase in phrases.items()
]
LANGUAGES = sorted({language for _c, language, _p in CASES})
FLOOR = {"hi": 0.9, "ur": 0.9, "ar": 0.9, "fr": 0.9, "fa": 0.9, "es": 0.9, "en2": 0.9, "ro2": 0.9}


def routed(phrase: str) -> str | None:
    noted = [{"title": phrase, "user_words": [phrase], "group": ""}]
    order = [c for c in lib.best_category(noted) if c]
    return order[0] if order else None


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_category_is_found_from_the_words_alone(language: str) -> None:
    mine = [(c, p) for c, lang, p in CASES if lang == language]
    right = sum(routed(p) == c for c, p in mine)
    wrong = [(c, routed(p)) for c, p in mine if routed(p) != c]
    assert right / len(mine) >= FLOOR[language], wrong


def test_every_library_category_has_cues_in_all_eight_languages() -> None:
    langs = {"en", "roman_ur", "hi", "ur", "ar", "fr", "fa", "es"}
    for category in lib.load():
        have = {
            lang
            for tier in lib.cues().get(category, {}).values()
            for lang, words in tier.items()
            if words
        }
        assert langs <= have, (category, sorted(langs - have))


def test_a_generic_word_alone_never_decides_the_category() -> None:
    assert routed("staff") is None
    assert routed("late") is None
    assert routed("stock") in (
        None,
        "stock_inventory",
    )  # a specific cue for stock, alone, is allowed


def test_the_models_group_beats_one_weak_cue_but_not_two_strong_ones() -> None:
    weak = [{"title": "stock problem", "user_words": ["stock"], "group": "margin_cost"}]
    assert lib.best_category(weak)[0] == "margin_cost"
    strong = [
        {
            "title": "theft",
            "user_words": ["staff stealing, goods missing, fraud"],
            "group": "margin_cost",
        }
    ]
    assert lib.best_category(strong)[0] == "loss_security"
