# ruff: noqa: E501
"""PS-3: the multilingual matrix for idea_relevance. Eight problem profiles in English, Roman Urdu,
Urdu, Arabic and Hindi (40 problems), each with two relevant ideas, one irrelevant, one generic and
one idea that answers ANOTHER profile's problem (200 ideas), then 60 adversarial script and shape
cases. The sentences are authored here; they are not taken from the PS-0 scenarios."""

import json
from pathlib import Path

import pytest

from app.modules.pi import idea_relevance as ir
from app.modules.pi import taxonomy
from app.modules.pi.idea_relevance import IdeaKind, evaluate_idea

LANGS = ("en", "roman_ur", "ur", "ar", "hi")

# profile -> category, then per language: (title, owner words, rel1, rel2, irrelevant, generic)
PROFILES: dict[str, dict] = {
    "collections": {
        "category": "cash_collections",
        "en": (
            "Shops pay our invoices very late",
            "shops pay our invoices after two months",
            "Send each shop a payment reminder three days before the invoice is due.",
            "Keep one list of overdue invoices with the date promised for each.",
            "Print new visiting cards with a gold logo.",
            "Use better software to improve your business.",
        ),
        "roman_ur": (
            "Dukandar hamare invoices bohat der se ada karte hain",
            "dukandar do mahine baad paisay dete hain",
            "Har dukandar ko invoice ki due date se teen din pehle payment ka reminder bhejein.",
            "Overdue invoices ki ek list rakhein aur har ek ka wada kiya hua din likhein.",
            "Sunehri logo wale naye visiting card chhapwayen.",
            "Behtar software istemal karein taake business behtar ho.",
        ),
        "ur": (
            "دکاندار ہمارے انوائس بہت دیر سے ادا کرتے ہیں",
            "دکاندار دو مہینے بعد ادائیگی کرتے ہیں",
            "ہر دکاندار کو انوائس کی آخری تاریخ سے تین دن پہلے ادائیگی کی یاد دہانی بھیجیں۔",
            "بقایا انوائسز کی ایک فہرست رکھیں اور ہر ایک کے لیے وعدہ کی گئی تاریخ لکھیں۔",
            "سنہرے لوگو والے نئے وزٹنگ کارڈ چھپوائیں۔",
            "بہتر سافٹ ویئر استعمال کریں تاکہ کاروبار بہتر ہو۔",
        ),
        "ar": (
            "المحلات تدفع فواتيرنا متأخرة جدا",
            "المحلات تدفع بعد شهرين",
            "أرسل لكل محل تذكيرا بالدفع قبل ثلاثة أيام من موعد استحقاق الفاتورة.",
            "احتفظ بقائمة واحدة بالفواتير المتأخرة مع التاريخ الذي وعد به كل عميل.",
            "اطبع بطاقات زيارة جديدة بشعار ذهبي.",
            "استخدم برنامجا أفضل لتحسين العمل.",
        ),
        "hi": (
            "दुकानदार हमारे बिल बहुत देर से चुकाते हैं",
            "दुकानदार दो महीने बाद भुगतान करते हैं",
            "हर दुकानदार को बिल की आखिरी तारीख से तीन दिन पहले भुगतान का रिमाइंडर भेजें।",
            "बकाया बिलों की एक सूची रखें और हर एक के लिए वादा की गई तारीख लिखें।",
            "सुनहरे लोगो वाले नए विजिटिंग कार्ड छपवाएं।",
            "बेहतर सॉफ्टवेयर का उपयोग करें ताकि व्यवसाय बेहतर हो।",
        ),
    },
    "stockout": {
        "category": "stock_inventory",
        "en": (
            "Fast selling items keep running out of stock",
            "we run out of our best sellers every week",
            "Set a minimum level for each fast seller and reorder when the shelf reaches it.",
            "Count the fast sellers every evening and write the numbers in one stock register.",
            "Repaint the shop front in brighter colours.",
            "Grow your business with social media marketing.",
        ),
        "roman_ur": (
            "Zyada bikne wali cheezein baar baar khatam ho jati hain",
            "hamari best selling cheezon ka stock har hafte khatam ho jata hai",
            "Har tez bikne wali cheez ka minimum level tay karein aur shelf us tak pohanchte hi dobara mangwayen.",
            "Har shaam tez bikne wali cheezein ginein aur ginti ek stock register mein likhein.",
            "Dukaan ke samne ko roshan rangon mein paint karwayen.",
            "Marketing behtar karein taake business barhe.",
        ),
        "ur": (
            "زیادہ بکنے والی چیزیں بار بار ختم ہو جاتی ہیں",
            "ہماری بہترین بکنے والی چیزوں کا اسٹاک ہر ہفتے ختم ہو جاتا ہے",
            "ہر تیز بکنے والی چیز کی کم از کم حد طے کریں اور شیلف وہاں پہنچتے ہی دوبارہ منگوائیں۔",
            "ہر شام تیز بکنے والی چیزوں کی گنتی کریں اور اعداد ایک اسٹاک رجسٹر میں لکھیں۔",
            "دکان کے سامنے کو روشن رنگوں میں پینٹ کروائیں۔",
            "مارکیٹنگ بہتر کریں تاکہ کاروبار بڑھے۔",
        ),
        "ar": (
            "السلع الأكثر مبيعا تنفد باستمرار",
            "تنفد أفضل بضائعنا مبيعا من المخزون كل أسبوع",
            "حدد حدا أدنى لكل سلعة سريعة البيع وأعد الطلب عندما يصل الرف إليه.",
            "اجرد السلع سريعة البيع كل مساء واكتب الأرقام في سجل مخزون واحد.",
            "اصبغ واجهة المحل بألوان أزهى.",
            "نمّوا عملكم بالتسويق عبر وسائل التواصل.",
        ),
        "hi": (
            "ज्यादा बिकने वाली चीजें बार बार खत्म हो जाती हैं",
            "हमारी सबसे ज्यादा बिकने वाली चीजों का स्टॉक हर हफ्ते खत्म हो जाता है",
            "हर तेज बिकने वाली चीज की न्यूनतम सीमा तय करें और शेल्फ वहां पहुंचते ही दोबारा मंगवाएं।",
            "हर शाम तेज बिकने वाली चीजें गिनें और संख्या एक स्टॉक रजिस्टर में लिखें।",
            "दुकान के सामने वाले हिस्से को पेंट करवाएं।",
            "मार्केटिंग बेहतर करें ताकि व्यवसाय बढ़े।",
        ),
    },
    "double_booking": {
        "category": "operations_process",
        "en": (
            "Two groups are booked for the same time slot",
            "we get double bookings every month",
            "Keep one shared calendar and mark each slot as soon as a booking is confirmed.",
            "Ask the front desk to check the diary before confirming any reservation.",
            "Offer cold drinks at the entrance.",
            "Use new technology to improve your work.",
        ),
        "roman_ur": (
            "Do groups ka ek hi time slot par booking ho jati hai",
            "har mahine double booking hoti hai",
            "Ek shared calendar rakhein aur booking confirm hote hi har slot par nishan lagayen.",
            "Reservation confirm karne se pehle front desk diary check kare.",
            "Darwaze par thande drinks pesh karein.",
            "Naye technology istemal karke kaam behtar karein.",
        ),
        "ur": (
            "دو گروپس کی ایک ہی وقت پر بکنگ ہو جاتی ہے",
            "ہر مہینے ڈبل بکنگ ہوتی ہے",
            "ایک مشترکہ کیلنڈر رکھیں اور بکنگ کنفرم ہوتے ہی ہر سلاٹ پر نشان لگائیں۔",
            "ریزرویشن کنفرم کرنے سے پہلے فرنٹ ڈیسک ڈائری چیک کرے۔",
            "دروازے پر ٹھنڈے مشروبات پیش کریں۔",
            "نئی ٹیکنالوجی استعمال کر کے کام بہتر کریں۔",
        ),
        "ar": (
            "تم حجز مجموعتين في نفس الموعد",
            "تحدث حجوزات مزدوجة كل شهر",
            "احتفظ بتقويم مشترك وضع علامة على كل موعد فور تأكيد الحجز.",
            "اطلب من الاستقبال مراجعة الدفتر قبل تأكيد أي حجز.",
            "قدم مشروبات باردة عند المدخل.",
            "استخدموا التكنولوجيا لتحسين العمل.",
        ),
        "hi": (
            "दो समूहों की एक ही समय पर बुकिंग हो जाती है",
            "हर महीने डबल बुकिंग होती है",
            "एक साझा कैलेंडर रखें और बुकिंग पक्की होते ही हर स्लॉट पर निशान लगाएं।",
            "आरक्षण पक्का करने से पहले फ्रंट डेस्क डायरी जांचे।",
            "दरवाजे पर ठंडे पेय पेश करें।",
            "नई तकनीक का उपयोग करके काम बेहतर करें।",
        ),
    },
    "late_delivery": {
        "category": "orders_fulfilment",
        "en": (
            "Our deliveries reach customers late",
            "parcels arrive two days late",
            "Ask the courier for a tracking number and message the customer when the parcel leaves.",
            "Give each rider a fixed route and a list of drop points.",
            "Hold an annual sports day with prizes.",
            "Improve your service to keep customers happy.",
        ),
        "roman_ur": (
            "Hamari deliveries gahakon ko der se pohanchti hain",
            "parcel do din der se aate hain",
            "Courier se tracking number mangein aur parcel nikalte hi customer ko message bhejein.",
            "Har rider ko ek tay shuda route aur drop points ki list dein.",
            "Saalana sports day inaam ke saath rakhein.",
            "Business ko behtar karein aur mehnat karein.",
        ),
        "ur": (
            "ہماری ڈیلیوری گاہکوں کو دیر سے پہنچتی ہے",
            "پارسل دو دن دیر سے آتے ہیں",
            "کوریئر سے ٹریکنگ نمبر مانگیں اور پارسل نکلتے ہی گاہک کو پیغام بھیجیں۔",
            "ہر رائیڈر کو ایک مقررہ روٹ اور ڈراپ پوائنٹس کی فہرست دیں۔",
            "سالانہ اسپورٹس ڈے انعامات کے ساتھ رکھیں۔",
            "کاروبار بہتر کریں اور محنت کریں۔",
        ),
        "ar": (
            "توصيلاتنا تصل إلى الزبائن متأخرة",
            "تصل الطرود متأخرة يومين",
            "اطلب من شركة الشحن رقم التتبع وأرسل رسالة للزبون عندما يخرج الطرد.",
            "أعط كل سائق مسارا ثابتا وقائمة بنقاط التسليم.",
            "نظم يوما رياضيا سنويا بجوائز.",
            "اعمل بجد لتحسين الاعمال.",
        ),
        "hi": (
            "हमारी डिलीवरी ग्राहकों तक देर से पहुँचती है",
            "पार्सल दो दिन देर से आते हैं",
            "कूरियर से ट्रैकिंग नंबर मांगें और पार्सल निकलते ही ग्राहक को संदेश भेजें।",
            "हर राइडर को एक तय रूट और ड्रॉप पॉइंट की सूची दें।",
            "वार्षिक स्पोर्ट्स डे इनाम के साथ रखें।",
            "व्यवसाय बेहतर करें और मेहनत करें।",
        ),
    },
    "staff_late": {
        "category": "people_staff",
        "en": (
            "Staff arrive late every morning",
            "half the team comes late to work",
            "Record each person's arrival time in a simple attendance sheet.",
            "Agree a clear shift roster so everyone knows the start time.",
            "Install new curtains in the waiting area.",
            "Make more money by working harder.",
        ),
        "roman_ur": (
            "Staff roz subah der se aata hai",
            "aadhi team kaam par late aati hai",
            "Har banda ke aane ka waqt ek simple attendance sheet mein likhein.",
            "Ek saaf shift roster banayen taake sab ko shuru hone ka waqt pata ho.",
            "Intezar wali jagah par naye parde lagwayen.",
            "Behtar management karein taake sab theek ho.",
        ),
        "ur": (
            "عملہ ہر صبح دیر سے آتا ہے",
            "آدھی ٹیم کام پر دیر سے آتی ہے",
            "ہر شخص کے آنے کا وقت ایک سادہ حاضری شیٹ میں لکھیں۔",
            "ایک واضح شفٹ روسٹر بنائیں تاکہ سب کو شروع ہونے کا وقت معلوم ہو۔",
            "انتظار کی جگہ پر نئے پردے لگوائیں۔",
            "بہتر مینجمنٹ کریں تاکہ سب ٹھیک ہو۔",
        ),
        "ar": (
            "الموظفون يتأخرون كل صباح",
            "نصف الفريق يتأخر عن العمل",
            "سجل وقت وصول كل شخص في جدول حضور بسيط.",
            "اتفقوا على جدول ورديات واضح ليعرف الجميع وقت البدء.",
            "ركب ستائر جديدة في منطقة الانتظار.",
            "اعمل بجد لتحسين الاعمال.",
        ),
        "hi": (
            "स्टाफ हर सुबह देर से आता है",
            "आधी टीम काम पर देर से आती है",
            "हर व्यक्ति के आने का समय एक सरल हाजिरी शीट में लिखें।",
            "एक साफ शिफ्ट रोस्टर बनाएं ताकि सबको शुरू होने का समय पता हो।",
            "इंतजार की जगह पर नए पर्दे लगवाएं।",
            "बेहतर प्रबंधन करें ताकि सब ठीक हो।",
        ),
    },
    "bad_reviews": {
        "category": "customers_retention",
        "en": (
            "Customers leave bad reviews about our service",
            "we get angry complaints and one-star reviews",
            "Reply to every complaint within a day and write down what went wrong.",
            "Ask each unhappy customer for feedback and fix the one thing they name.",
            "Put a mural on the side wall.",
            "Do better marketing.",
        ),
        "roman_ur": (
            "Gahak hamari service ke baare mein bure review dete hain",
            "humein gusse wali shikayatein aur kam rating milti hai",
            "Har shikayat ka ek din mein jawab dein aur likh lein kya ghalat hua.",
            "Har naraaz gahak se feedback lein aur jo ek cheez woh batayein use theek karein.",
            "Pehlu ki deewar par mural banwayen.",
            "Marketing behtar karein.",
        ),
        "ur": (
            "گاہک ہماری سروس کے بارے میں برے ریویو دیتے ہیں",
            "ہمیں غصے والی شکایات اور کم ریٹنگ ملتی ہے",
            "ہر شکایت کا ایک دن میں جواب دیں اور لکھ لیں کیا غلط ہوا۔",
            "ہر ناراض گاہک سے فیڈ بیک لیں اور جو ایک چیز وہ بتائیں اسے ٹھیک کریں۔",
            "ساتھ والی دیوار پر مورل بنوائیں۔",
            "مارکیٹنگ بہتر کریں۔",
        ),
        "ar": (
            "الزبائن يكتبون تقييمات سيئة عن خدمتنا",
            "نتلقى شكاوى غاضبة وتقييمات منخفضة",
            "رد على كل شكوى خلال يوم واكتب ما الذي حدث بشكل خاطئ.",
            "اطلب ملاحظات من كل زبون غير راض وأصلح الشيء الذي يذكره.",
            "ارسم جدارية على الجدار الجانبي.",
            "حسن التسويق.",
        ),
        "hi": (
            "ग्राहक हमारी सर्विस के बारे में बुरे रिव्यू देते हैं",
            "हमें गुस्से वाली शिकायतें और कम रेटिंग मिलती है",
            "हर शिकायत का एक दिन में जवाब दें और लिख लें क्या गलत हुआ।",
            "हर नाराज ग्राहक से फीडबैक लें और जो एक चीज वो बताएं उसे ठीक करें।",
            "बगल की दीवार पर भित्तिचित्र बनवाएं।",
            "मार्केटिंग बेहतर करें।",
        ),
    },
    "expiry": {
        "category": "stock_inventory",
        "en": (
            "Food spoils and gets thrown away before it is sold",
            "we waste a lot because items expire",
            "Put the oldest stock at the front and check expiry dates every Monday.",
            "Order smaller quantities of items that spoil quickly.",
            "Play soft music for customers.",
            "Be more efficient.",
        ),
        "roman_ur": (
            "Khana bikne se pehle kharab ho kar phenk diya jata hai",
            "expiry ki wajah se bohat zaya hota hai",
            "Purana maal aage rakhein aur har Monday expiry date check karein.",
            "Jo cheezein jaldi kharab hoti hain unka order chhota rakhein.",
            "Gahakon ke liye halki music chalayen.",
            "Business ko behtar karein.",
        ),
        "ur": (
            "کھانا بکنے سے پہلے خراب ہو کر پھینک دیا جاتا ہے",
            "ایکسپائری کی وجہ سے بہت ضائع ہوتا ہے",
            "پرانا مال آگے رکھیں اور ہر پیر ایکسپائری تاریخ چیک کریں۔",
            "جو چیزیں جلد خراب ہوتی ہیں ان کا آرڈر چھوٹا رکھیں۔",
            "گاہکوں کے لیے ہلکی موسیقی چلائیں۔",
            "کاروبار بہتر کریں۔",
        ),
        "ar": (
            "الطعام يفسد ويرمى قبل بيعه",
            "نهدر كثيرا لأن المنتجات تنتهي صلاحيتها",
            "ضع المخزون الأقدم في المقدمة وافحص تواريخ انتهاء الصلاحية كل اثنين.",
            "اطلب كميات أصغر من الأصناف التي تفسد بسرعة.",
            "شغل موسيقى هادئة للزبائن.",
            "استخدم التكنولوجيا لتحسين الاعمال.",
        ),
        "hi": (
            "खाना बिकने से पहले खराब होकर फेंक दिया जाता है",
            "एक्सपायरी की वजह से बहुत बर्बाद होता है",
            "पुराना माल आगे रखें और हर सोमवार एक्सपायरी तारीख जांचें।",
            "जो चीजें जल्दी खराब होती हैं उनका ऑर्डर छोटा रखें।",
            "ग्राहकों के लिए हल्का संगीत चलाएं।",
            "व्यवसाय बेहतर करें।",
        ),
    },
    "no_return": {
        "category": "customers_retention",
        "en": (
            "Customers do not come back after the first visit",
            "most new customers never return",
            "Call each new customer a week later to ask how it went and invite them back.",
            "Start a simple loyalty card that gives a reward on the fifth visit.",
            "Replace the old furniture in the office.",
            "Focus on customers.",
        ),
        "roman_ur": (
            "Gahak pehli visit ke baad wapas nahi aate",
            "zyada tar naye gahak dobara nahi aate",
            "Har naye gahak ko ek hafte baad call karke poochein kaisa laga aur wapas bulayen.",
            "Ek simple loyalty card shuru karein jo paanchvi visit par inaam de.",
            "Daftar ka purana furniture badal dein.",
            "Behtar karein taake gahak khush rahein.",
        ),
        "ur": (
            "گاہک پہلی وزٹ کے بعد واپس نہیں آتے",
            "زیادہ تر نئے گاہک دوبارہ نہیں آتے",
            "ہر نئے گاہک کو ایک ہفتے بعد کال کر کے پوچھیں کیسا لگا اور واپس بلائیں۔",
            "ایک سادہ لائلٹی کارڈ شروع کریں جو پانچویں وزٹ پر انعام دے۔",
            "دفتر کا پرانا فرنیچر بدل دیں۔",
            "بہتر کریں تاکہ گاہک خوش رہیں۔",
        ),
        "ar": (
            "الزبائن لا يعودون بعد الزيارة الأولى",
            "معظم الزبائن الجدد لا يعودون",
            "اتصل بكل زبون جديد بعد أسبوع لتسأله كيف كانت التجربة وادعه للعودة.",
            "ابدأ بطاقة ولاء بسيطة تمنح مكافأة في الزيارة الخامسة.",
            "استبدل الأثاث القديم في المكتب.",
            "اعمل بجد لتحسين الاعمال.",
        ),
        "hi": (
            "ग्राहक पहली विजिट के बाद वापस नहीं आते",
            "ज्यादातर नए ग्राहक दोबारा नहीं आते",
            "हर नए ग्राहक को एक हफ्ते बाद कॉल करके पूछें कैसा लगा और वापस बुलाएं।",
            "एक सरल लॉयल्टी कार्ड शुरू करें जो पांचवीं विजिट पर इनाम दे।",
            "ऑफिस का पुराना फर्नीचर बदल दें।",
            "बेहतर करें ताकि ग्राहक खुश रहें।",
        ),
    },
}
ORDER = list(PROFILES)


def _problem(key: str, lang: str) -> list[dict]:
    title, words, *_ = PROFILES[key][lang]
    return [
        {"id": "p1", "title": title, "user_words": [words], "category": PROFILES[key]["category"]}
    ]


def _cases() -> list[tuple[str, str, str, str, IdeaKind]]:
    out = []
    for i, key in enumerate(ORDER):
        other = ORDER[(i + 1) % len(ORDER)]
        for lang in LANGS:
            _, _, rel1, rel2, irr, gen = PROFILES[key][lang]
            cross = PROFILES[other][lang][2]
            out += [
                (key, lang, "rel1", rel1, IdeaKind.LINKED),
                (key, lang, "rel2", rel2, IdeaKind.LINKED),
                (key, lang, "irrelevant", irr, IdeaKind.UNLINKED),
                (key, lang, "generic", gen, IdeaKind.GENERIC),
                (key, lang, "other_problem", cross, IdeaKind.UNLINKED),
            ]
    return out


CASES = _cases()


def test_the_matrix_has_two_hundred_ideas() -> None:
    assert len(CASES) == 200
    assert {c[1] for c in CASES} == set(LANGS)


@pytest.mark.parametrize(
    ("key", "lang", "role", "idea", "kind"), CASES, ids=[f"{c[0]}-{c[1]}-{c[2]}" for c in CASES]
)
def test_matrix(key: str, lang: str, role: str, idea: str, kind: IdeaKind) -> None:
    v = evaluate_idea(idea, _problem(key, lang), None, None, lang)
    assert v.kind is kind, (v.kind, v.reason, v.evidence_words, v.concepts)
    if kind is IdeaKind.LINKED:
        assert v.linked_problem_ids == ("p1",) and v.evidence_words
    else:
        assert v.linked_problem_ids == ()


def test_matrix_agreement_per_language_is_total() -> None:
    for lang in LANGS:
        rows = [c for c in CASES if c[1] == lang]
        ok = sum(
            evaluate_idea(c[3], _problem(c[0], lang), None, None, lang).kind is c[4] for c in rows
        )
        assert ok == len(rows), (lang, ok, len(rows))


def test_the_same_idea_is_judged_the_same_in_every_language_pair() -> None:
    """A relevant idea is LINKED in each language when the problem is in another language: the
    concept, not the word, carries the link."""
    for key in ORDER:
        for pl in LANGS:
            for il in LANGS:
                idea = PROFILES[key][il][2]
                v = evaluate_idea(idea, _problem(key, pl), None, None, il)
                assert v.kind is IdeaKind.LINKED, (key, pl, il, v)


# ----- adversarial script and shape cases ------------------------------------------------------------

LATE = [
    {
        "id": "p1",
        "title": "Deliveries reach customers late",
        "user_words": ["parcels arrive late"],
        "category": "orders_fulfilment",
    }
]

ADV = [
    # (idea, expected kind)
    ("Ask the courier for a TRACKING NUMBER!!!", IdeaKind.LINKED),
    ("ask the courier for a tracking number", IdeaKind.LINKED),
    ("Ask   the\tcourier\nfor a tracking number.", IdeaKind.LINKED),
    ("Ask the courier for a tracking-number.", IdeaKind.LINKED),
    ("Ask the courier’s tracking number", IdeaKind.LINKED),
    ("Ask the cöurier for a trácking number", IdeaKind.LINKED),
    ("Ask the courier for a tracking number ​‌‍", IdeaKind.LINKED),
    ("‮Ask the courier for a tracking number‬", IdeaKind.LINKED),
    ("😀 Ask the courier for a tracking number 😀", IdeaKind.LINKED),
    ("Courier se tracking number mangein", IdeaKind.LINKED),
    ("COURIER SE TRACKING NUMBER MANGEIN", IdeaKind.LINKED),
    ("کوریئر سے ٹریکنگ نمبر مانگیں", IdeaKind.LINKED),
    ("كوريير سے ٹریکنگ نمبر مانگیں", IdeaKind.LINKED),
    ("کُورِیئر سے ٹریکنگ نمبر مانگیں", IdeaKind.LINKED),
    ("ـاطلبوا ـمن شركة الشحن رقم التتبع", IdeaKind.LINKED),
    ("اطلبوا من شركة الشحن رقم التتبع ٣ مرات", IdeaKind.LINKED),
    ("اطلب من شركة الشحن رقم التتبع لكل طرد", IdeaKind.LINKED),
    ("وبالتوصيل المتأخر نبدأ بالتتبع", IdeaKind.LINKED),
    ("कूरियर से ट्रैकिंग नंबर मांगें", IdeaKind.LINKED),
    ("कूरियर से ट्रैकिंग नंबर मांगें, १० पार्सल के लिए", IdeaKind.LINKED),
    ("Ask courier se tracking number मांगें", IdeaKind.LINKED),  # code-switched Latin, Devanagari
    ("Tracking number کوریئر سے لیں and message the customer", IdeaKind.LINKED),
    ("Give each rider a fixed route.", IdeaKind.LINKED),
    ("Give each ٹرک ڈرائیور a fixed route.", IdeaKind.LINKED),
    ("Repaint the walls.", IdeaKind.UNLINKED),
    ("REPAINT THE WALLS!!", IdeaKind.UNLINKED),
    ("دیواروں کو پینٹ کریں", IdeaKind.UNLINKED),
    ("दीवारों को पेंट करें", IdeaKind.UNLINKED),
    ("Hold a lucky draw with prizes.", IdeaKind.UNLINKED),
    ("لکی ڈرا رکھیں اور انعام دیں", IdeaKind.UNLINKED),
    ("Use better software to improve your business", IdeaKind.GENERIC),
    ("USE BETTER SOFTWARE TO IMPROVE YOUR BUSINESS!!!", IdeaKind.GENERIC),
    ("  Use   better software\n to improve   your business  ", IdeaKind.GENERIC),
    ("بہتر سافٹ ویئر استعمال کریں تاکہ کاروبار بہتر ہو", IdeaKind.GENERIC),
    ("बेहतर सॉफ्टवेयर का उपयोग करें ताकि व्यवसाय बेहतर हो", IdeaKind.GENERIC),
    ("请每天给客户发送订单跟踪信息", IdeaKind.UNKNOWN),
    ("Отправляйте клиентам номер отслеживания", IdeaKind.UNKNOWN),
    ("お客様に追跡番号を送ってください", IdeaKind.UNKNOWN),
    ("แจ้งหมายเลขติดตามพัสดุให้ลูกค้า", IdeaKind.UNKNOWN),
    ("1234567890", IdeaKind.UNKNOWN),
    ("!!! ??? ...", IdeaKind.UNKNOWN),
    ("😀😀😀", IdeaKind.UNKNOWN),
    ("", IdeaKind.UNKNOWN),
    ("a", IdeaKind.UNKNOWN),
    ("Zorp the flibber", IdeaKind.UNKNOWN),
    ("ٱ ٱ ٱ ٱ", IdeaKind.UNKNOWN),
    ("ء ء ء", IdeaKind.UNKNOWN),
    ("​​​", IdeaKind.UNKNOWN),
    ("ऑ ऑ ऑ", IdeaKind.UNKNOWN),
    ("Courier ko call karein, tracking number lein.", IdeaKind.LINKED),
]


def test_adversarial_script_and_shape_cases() -> None:
    assert len(ADV) >= 50
    for idea, kind in ADV:
        v = evaluate_idea(idea, LATE, None, None, None)
        assert v.kind is kind, (idea, v.kind, v.reason)


def test_adversarial_never_links_unknown_script() -> None:
    for idea in (
        "请每天给客户发送订单跟踪信息",
        "Отправляйте клиентам номер отслеживания",
        "お客様に追跡番号を送ってください",
    ):
        assert evaluate_idea(idea, LATE).kind is not IdeaKind.LINKED


def test_mixed_script_with_half_unsupported_letters_is_unknown() -> None:
    # more than half of the letters are Chinese: not judged
    assert (
        evaluate_idea("tracking 请每天给客户发送订单跟踪信息和更多的内容", LATE).kind
        is IdeaKind.UNKNOWN
    )


def test_language_hint_does_not_change_the_verdict() -> None:
    for lang in (None, "", "en", "ur", "ar", "hi", "roman_ur", "xx", "EN-gb", 5):
        v = evaluate_idea("Ask the courier for a tracking number", LATE, None, None, lang)  # type: ignore[arg-type]
        assert v.kind is IdeaKind.LINKED


# ----- the lexicon itself ------------------------------------------------------------------------------


def test_every_taxonomy_category_reaches_a_concept() -> None:
    for cat in taxonomy.CATEGORIES:
        if cat.key == taxonomy.OTHER:
            continue
        assert ir._TAXO_CAT.get(cat.key), cat.key


def test_every_master_subtype_resolves_to_some_concept() -> None:
    for cat in taxonomy.CATEGORIES:
        for sub in cat.subtypes:
            assert ir._TAXO_SUB.get(sub) or ir._TAXO_CAT.get(cat.key), (cat.key, sub)


def test_taxonomy_labels_in_four_languages_map_to_their_own_category() -> None:
    """The category names the owner sees (en, roman_ur, ur, ar) are not all in the lexicon, but a
    category's own English label must land on a concept of that category, where one exists."""
    hits = 0
    for cat in taxonomy.CATEGORIES:
        if cat.key == taxonomy.OTHER:
            continue
        found = {
            i
            for i, _ in ir._MAIN.scan(
                ir.normalize_text(f"{cat.en} {cat.roman_ur} {cat.ur} {cat.ar}").split()
            )
        }
        if found & ir._TAXO_CAT.get(cat.key, frozenset()):
            hits += 1
    assert hits >= 12  # of 18


def test_the_lexicon_terms_all_parse_and_every_concept_has_five_scripts() -> None:
    for concept in ir._CONCEPTS:
        joined = concept.terms
        assert any("؀" <= ch <= "ۿ" for ch in joined), concept.key
        assert any("ऀ" <= ch <= "ॿ" for ch in joined) or concept.key in ir.lex.EXTRA_TERMS, (
            concept.key
        )
        assert any(ch.isascii() and ch.isalpha() for ch in joined), concept.key


def test_pack_problem_phrases_get_a_concept_that_agrees_with_their_category() -> None:
    packs = Path(ir.__file__).parent / "packs" / "industry"
    total = anyc = ok = 0
    for path in sorted(packs.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data.get("problems", []):
            words = ir.normalize_text(row.get("phrase", "")).split()
            hits = {i for i, _ in ir._MAIN.scan(words)}
            total += 1
            anyc += bool(hits)
            ok += bool(hits & ir._TAXO_CAT.get(row.get("category"), frozenset()))
    assert total > 4000
    assert anyc / total >= 0.85, anyc / total
    assert ok / total >= 0.60, ok / total
