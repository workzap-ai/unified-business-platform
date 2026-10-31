# ruff: noqa: E501
"""PS-3 round 3: what the owner already tried. The outcome decides (failed = a repeat, worked = not a
failed repeat, unset = a repeat to ask about), and a REWORDED repeat is caught by the concepts of the
tried item (object + remedy), in five languages, not by shared words. 100 fresh repeat pairs and 100
fresh different-remedy pairs written before tuning, plus the exact inputs the integrated check found."""

import pytest

from app.modules.pi.idea_relevance import IdeaKind, evaluate_idea

LANGS = ("en", "roman_ur", "ur", "ar", "hi")
PROBLEM = [
    {
        "id": "p1",
        "title": "Customer files get mixed up",
        "user_words": ["files mix ho gaye"],
        "category": "operations_process",
    }
]

# concept -> lang -> (what the owner tried, a REWORDED repeat of it, an idea with a different remedy)
PAIRS: dict[str, dict[str, tuple[str, str, str]]] = {
    "colour_folder": {
        "en": (
            "colour coded folders",
            "Use colour-coded folders for each customer.",
            "Send a reminder to each customer.",
        ),
        "roman_ur": (
            "rang wale folder",
            "Colour wale files rakho.",
            "Har customer ko reminder bhejein.",
        ),
        "ur": (
            "رنگین فولڈر",
            "ہر گاہک کے لیے رنگ والی فائلیں رکھیں۔",
            "ہر گاہک کو یاد دہانی بھیجیں۔",
        ),
        "ar": ("ملفات ملونة", "استخدموا مجلدات ملونة لكل عميل.", "أرسلوا تذكيرا لكل عميل."),
        "hi": ("रंगीन फोल्डर", "हर ग्राहक के लिए रंग वाली फाइलें रखें।", "हर ग्राहक को रिमाइंडर भेजें।"),
    },
    "reminder": {
        "en": (
            "reminder messages",
            "Remind customers by message before the date.",
            "Give a discount for early payment.",
        ),
        "roman_ur": (
            "yaad dihani ke message",
            "Date se pehle customers ko yaad dilayein.",
            "Jaldi ada karne par discount dein.",
        ),
        "ur": (
            "یاد دہانی کے پیغام",
            "تاریخ سے پہلے گاہکوں کو یاد دلائیں۔",
            "جلد ادائیگی پر ڈسکاؤنٹ دیں۔",
        ),
        "ar": ("رسائل تذكير", "ذكروا العملاء قبل الموعد.", "قدموا خصما عند الدفع المبكر."),
        "hi": ("रिमाइंडर संदेश", "तारीख से पहले ग्राहकों को याद दिलाएं।", "जल्दी भुगतान पर छूट दें।"),
    },
    "discount": {
        "en": ("gave a discount", "Offer a price cut to buyers.", "Hire an extra assistant."),
        "roman_ur": ("discount diya", "Customers ko chhoot dein.", "Ek aur assistant hire karein."),
        "ur": ("ڈسکاؤنٹ دیا", "گاہکوں کو رعایت دیں۔", "ایک اور اسسٹنٹ بھرتی کریں۔"),
        "ar": ("قدمنا خصما", "اعطوا الزبائن تخفيضا.", "وظفوا مساعدا إضافيا."),
        "hi": ("छूट दी", "ग्राहकों को डिस्काउंट दें।", "एक और असिस्टेंट की भर्ती करें।"),
    },
    "ads": {
        "en": ("paid ads", "Run some adverts on Facebook.", "Train the staff on the process."),
        "roman_ur": (
            "ishtihar chalaye",
            "Facebook par ads chalayein.",
            "Staff ko process ki training dein.",
        ),
        "ur": ("اشتہار چلائے", "فیس بک پر اشتہارات چلائیں۔", "عملے کو طریقہ کار کی تربیت دیں۔"),
        "ar": (
            "إعلانات مدفوعة",
            "شغلوا إعلانات على فيسبوك.",
            "قدموا تدريبا للموظفين على الإجراءات.",
        ),
        "hi": ("विज्ञापन चलाए", "फेसबुक पर विज्ञापन चलाएं।", "स्टाफ को प्रक्रिया की ट्रेनिंग दें।"),
    },
    "hire": {
        "en": ("hired a second person", "Recruit extra staff.", "Use a checklist at closing time."),
        "roman_ur": (
            "ek aur banda hire kiya",
            "Mazeed staff bharti karein.",
            "Band karte waqt checklist istemal karein.",
        ),
        "ur": (
            "ایک اور بندہ بھرتی کیا",
            "مزید عملہ بھرتی کریں۔",
            "بند کرتے وقت چیک لسٹ استعمال کریں۔",
        ),
        "ar": ("وظفنا شخصا ثانيا", "وظفوا موظفين إضافيين.", "استخدموا قائمة تحقق عند الاغلاق."),
        "hi": ("एक और आदमी भर्ती किया", "अतिरिक्त स्टाफ की भर्ती करें।", "बंद करते समय चेकलिस्ट इस्तेमाल करें।"),
    },
    "software": {
        "en": ("a new app", "Install a booking app.", "Give a bonus for the best month."),
        "roman_ur": (
            "naya software lagaya",
            "Ek app install karein.",
            "Behtareen mahine par bonus dein.",
        ),
        "ur": ("نیا سافٹ ویئر لگایا", "ایک ایپ انسٹال کریں۔", "بہترین مہینے پر بونس دیں۔"),
        "ar": ("برنامج جديد", "ثبتوا تطبيقا للحجز.", "اعطوا مكافأة لأفضل شهر."),
        "hi": ("नया सॉफ्टवेयर लगाया", "एक ऐप इंस्टॉल करें।", "सबसे अच्छे महीने पर बोनस दें।"),
    },
    "training": {
        "en": (
            "a training course",
            "Send the team on a short course.",
            "Offer a discount for new buyers.",
        ),
        "roman_ur": (
            "training karwayi",
            "Team ko chhota course karwayen.",
            "Naye gahakon ko discount dein.",
        ),
        "ur": ("ٹریننگ کروائی", "ٹیم کو ایک مختصر کورس کروائیں۔", "نئے گاہکوں کو ڈسکاؤنٹ دیں۔"),
        "ar": ("دورة تدريبية", "ارسلوا الفريق إلى دورة قصيرة.", "قدموا خصما للزبائن الجدد."),
        "hi": ("ट्रेनिंग करवाई", "टीम को एक छोटा कोर्स करवाएं।", "नए ग्राहकों को छूट दें।"),
    },
    "loyalty": {
        "en": (
            "a loyalty card",
            "Give points that turn into a reward.",
            "Photograph each receipt.",
        ),
        "roman_ur": (
            "loyalty card shuru kiya",
            "Points do jo inaam mein badal jayein.",
            "Har raseed ki tasveer lein.",
        ),
        "ur": (
            "لائلٹی کارڈ شروع کیا",
            "پوائنٹس دیں جو انعام میں بدل جائیں۔",
            "ہر رسید کی تصویر لیں۔",
        ),
        "ar": ("بطاقة ولاء", "امنحوا نقاطا تتحول إلى مكافأة.", "صوروا كل إيصال."),
        "hi": ("लॉयल्टी कार्ड शुरू किया", "ऐसे पॉइंट दें जो इनाम में बदल जाएं।", "हर रसीद की तस्वीर लें।"),
    },
    "register": {
        "en": (
            "a paper register",
            "Write everything in a ledger book.",
            "Send a reminder to the customer.",
        ),
        "roman_ur": (
            "kaghaz ka register",
            "Sab kuch khata copy mein likhein.",
            "Customer ko reminder bhejein.",
        ),
        "ur": ("کاغذی رجسٹر", "سب کچھ کھاتے میں لکھیں۔", "گاہک کو یاد دہانی بھیجیں۔"),
        "ar": ("سجل ورقي", "اكتبوا كل شيء في دفتر الحسابات.", "أرسلوا تذكيرا للعميل."),
        "hi": ("कागज का रजिस्टर", "सब कुछ खाते में लिखें।", "ग्राहक को रिमाइंडर भेजें।"),
    },
    "group_chat": {
        "en": ("a WhatsApp group", "Create a group chat for the team.", "Hire another driver."),
        "roman_ur": (
            "WhatsApp group banaya",
            "Team ka group chat banayein.",
            "Ek aur driver hire karein.",
        ),
        "ur": ("واٹس ایپ گروپ بنایا", "ٹیم کا گروپ چیٹ بنائیں۔", "ایک اور ڈرائیور بھرتی کریں۔"),
        "ar": ("مجموعة واتساب", "أنشئوا مجموعة دردشة للفريق.", "وظفوا سائقا آخر."),
        "hi": ("व्हाट्सएप ग्रुप बनाया", "टीम का ग्रुप चैट बनाएं।", "एक और ड्राइवर की भर्ती करें।"),
    },
    "camera": {
        "en": ("cctv cameras", "Put a camera over the counter.", "Train staff on the new process."),
        "roman_ur": (
            "camera lagwaye",
            "Counter ke upar camera lagayein.",
            "Staff ko naye process ki training dein.",
        ),
        "ur": ("کیمرے لگوائے", "کاؤنٹر کے اوپر کیمرہ لگائیں۔", "عملے کو نئے طریقے کی تربیت دیں۔"),
        "ar": (
            "كاميرات مراقبة",
            "ضعوا كاميرا فوق الصندوق.",
            "قدموا تدريبا للموظفين على الطريقة الجديدة.",
        ),
        "hi": ("कैमरे लगवाए", "काउंटर के ऊपर कैमरा लगाएं।", "स्टाफ को नए तरीके की ट्रेनिंग दें।"),
    },
    "checklist": {
        "en": (
            "a daily checklist",
            "Use a tick list for the closing steps.",
            "Run ads on Instagram.",
        ),
        "roman_ur": (
            "roz ki checklist",
            "Band karne ke marhalon ke liye tick list banayein.",
            "Instagram par ads chalayein.",
        ),
        "ur": (
            "روزانہ چیک لسٹ",
            "بند کرنے کے مراحل کے لیے ٹک لسٹ بنائیں۔",
            "انسٹاگرام پر اشتہارات چلائیں۔",
        ),
        "ar": (
            "قائمة تحقق يومية",
            "استخدموا قائمة تحقق لخطوات الاغلاق.",
            "شغلوا إعلانات على انستغرام.",
        ),
        "hi": ("रोज की चेकलिस्ट", "बंद करने के चरणों के लिए चेकलिस्ट बनाएं।", "इंस्टाग्राम पर विज्ञापन चलाएं।"),
    },
    "roster": {
        "en": ("a duty roster", "Write a shift timetable.", "Offer a loyalty card."),
        "roman_ur": (
            "duty roster banaya",
            "Shift ka time table likhein.",
            "Loyalty card shuru karein.",
        ),
        "ur": ("ڈیوٹی روسٹر", "شفٹ کا ٹائم ٹیبل لکھیں۔", "لائلٹی کارڈ شروع کریں۔"),
        "ar": ("جدول ورديات", "اكتبوا جدول مناوبات.", "ابدؤوا بطاقة ولاء."),
        "hi": ("ड्यूटी रोस्टर", "शिफ्ट का टाइम टेबल लिखें।", "लॉयल्टी कार्ड शुरू करें।"),
    },
    "token": {
        "en": (
            "token numbers",
            "Give each walk-in a queue number.",
            "Send a WhatsApp message when ready.",
        ),
        "roman_ur": (
            "token system",
            "Har walk-in ko line number dein.",
            "Tayyar hone par WhatsApp message bhejein.",
        ),
        "ur": (
            "ٹوکن سسٹم",
            "ہر واک اِن کو قطار کا نمبر دیں۔",
            "تیار ہونے پر واٹس ایپ پیغام بھیجیں۔",
        ),
        "ar": ("أرقام الدور", "اعطوا كل زائر رقم دور.", "أرسلوا رسالة واتساب عند الجاهزية."),
        "hi": ("टोकन सिस्टम", "हर वॉक-इन को कतार नंबर दें।", "तैयार होने पर व्हाट्सएप संदेश भेजें।"),
    },
    "bonus": {
        "en": ("a bonus", "Pay an incentive for on-time work.", "Install a camera."),
        "roman_ur": ("bonus diya", "Waqt par kaam par incentive dein.", "Camera lagayein."),
        "ur": ("بونس دیا", "وقت پر کام پر ترغیبی رقم دیں۔", "کیمرہ لگائیں۔"),
        "ar": ("مكافأة", "ادفعوا حوافز على العمل في الوقت.", "ركبوا كاميرا."),
        "hi": ("बोनस दिया", "समय पर काम के लिए प्रोत्साहन राशि दें।", "कैमरा लगाएं।"),
    },
    "courier_change": {
        "en": (
            "changed the courier",
            "Switch to another delivery company.",
            "Run a training course.",
        ),
        "roman_ur": (
            "courier badal diya",
            "Doosri delivery company par chale jayein.",
            "Training course karwayen.",
        ),
        "ur": ("کوریئر بدل دیا", "کسی دوسری ڈیلیوری کمپنی پر چلے جائیں۔", "ٹریننگ کورس کروائیں۔"),
        "ar": ("غيرنا شركة الشحن", "انتقلوا إلى شركة توصيل أخرى.", "نظموا دورة تدريبية."),
        "hi": ("कूरियर बदल दिया", "किसी दूसरी डिलीवरी कंपनी पर चले जाएं।", "ट्रेनिंग कोर्स करवाएं।"),
    },
    "price_raise": {
        "en": ("raised prices", "Increase the rates a little.", "Hire a driver."),
        "roman_ur": ("qeemat barha di", "Rates thoda barha dein.", "Ek driver hire karein."),
        "ur": ("قیمت بڑھا دی", "ریٹ تھوڑا بڑھا دیں۔", "ایک ڈرائیور بھرتی کریں۔"),
        "ar": ("رفعنا الأسعار", "ارفعوا الاسعار قليلا.", "وظفوا سائقا."),
        "hi": ("कीमत बढ़ा दी", "रेट थोड़ा बढ़ा दें।", "एक ड्राइवर की भर्ती करें।"),
    },
    "meeting": {
        "en": ("daily meetings", "Call a team meeting each morning.", "Use colour coded folders."),
        "roman_ur": (
            "roz meeting ki",
            "Har subah team meeting rakhein.",
            "Rang wale folder istemal karein.",
        ),
        "ur": ("روزانہ میٹنگ", "ہر صبح ٹیم میٹنگ رکھیں۔", "رنگ والے فولڈر استعمال کریں۔"),
        "ar": ("اجتماعات يومية", "اعقدوا اجتماعا للفريق كل صباح.", "استخدموا مجلدات ملونة."),
        "hi": ("रोज मीटिंग की", "हर सुबह टीम मीटिंग रखें।", "रंग वाले फोल्डर इस्तेमाल करें।"),
    },
    "label": {
        "en": ("labels on boxes", "Stick a tag on every box.", "Give a bonus."),
        "roman_ur": ("dabbon par label lagaya", "Har dabbe par tag lagayein.", "Bonus dein."),
        "ur": ("ڈبوں پر لیبل لگایا", "ہر ڈبے پر ٹیگ لگائیں۔", "بونس دیں۔"),
        "ar": ("ملصقات على الصناديق", "الصقوا بطاقة على كل صندوق.", "اعطوا مكافأة."),
        "hi": ("डिब्बों पर लेबल लगाया", "हर डिब्बे पर टैग लगाएं।", "बोनस दें।"),
    },
    "text_message": {
        "en": ("sms messages", "Text each customer a note.", "Raise the prices."),
        "roman_ur": ("sms bheje", "Har customer ko text message bhejein.", "Prices barha dein."),
        "ur": ("ایس ایم ایس بھیجے", "ہر گاہک کو ٹیکسٹ پیغام بھیجیں۔", "قیمتیں بڑھا دیں۔"),
        "ar": ("رسائل نصية", "ارسلوا رسالة نصية لكل عميل.", "ارفعوا الاسعار."),
        "hi": ("एसएमएस भेजे", "हर ग्राहक को टेक्स्ट संदेश भेजें।", "कीमतें बढ़ा दें।"),
    },
}
POS = [(k, lang) for k in PAIRS for lang in LANGS]


def _tried(what: str, outcome: str = "failed") -> list[dict]:
    return [{"what": what, "outcome": outcome, "msg": "m1"}]


def test_hundred_pairs_per_direction() -> None:
    assert len(POS) == 100


@pytest.mark.parametrize(("key", "lang"), POS, ids=[f"{k}-{lang}" for k, lang in POS])
def test_reworded_repeat_of_a_failed_attempt(key: str, lang: str) -> None:
    what, repeat, _ = PAIRS[key][lang]
    v = evaluate_idea(repeat, PROBLEM, None, _tried(what), lang)
    assert v.kind is IdeaKind.REPEATS_TRIED and v.reason == "tried_failed", (
        v.kind,
        v.reason,
        v.concepts,
    )


@pytest.mark.parametrize(("key", "lang"), POS, ids=[f"{k}-{lang}" for k, lang in POS])
def test_a_different_remedy_is_not_a_repeat(key: str, lang: str) -> None:
    what, _, other = PAIRS[key][lang]
    v = evaluate_idea(other, PROBLEM, None, _tried(what), lang)
    assert v.kind is not IdeaKind.REPEATS_TRIED, (v.kind, v.reason, v.concepts)


# ----- the outcome decides --------------------------------------------------------------------------------


def test_exact_inputs_from_the_integrated_check() -> None:
    probs = [
        {"id": "p1", "title": "Customer files get mixed up", "user_words": ["files mix ho gaye"]}
    ]
    tried = [{"what": "rang wale folder", "outcome": "failed"}]
    for idea in (
        "Colour wale files rakho",
        "colour-coded folders per customer",
        "Rang wale folder banayein",
    ):
        v = evaluate_idea(idea, probs, None, tried, "roman_ur")
        assert v.kind is IdeaKind.REPEATS_TRIED and v.reason == "tried_failed", (idea, v)
    v = evaluate_idea("Hire an extra assistant", probs, None, tried, "roman_ur")
    assert v.kind is not IdeaKind.REPEATS_TRIED


def test_a_worked_attempt_is_not_a_failed_repeat() -> None:
    probs = [
        {
            "id": "p1",
            "title": "Customer files get mixed up",
            "user_words": ["files mix ho gaye"],
            "category": "operations_process",
        }
    ]
    tried = [{"what": "rang wale folder", "outcome": "worked"}]
    v = evaluate_idea("Colour-coded folders per customer", probs, None, tried, "roman_ur")
    assert v.kind is not IdeaKind.REPEATS_TRIED
    assert v.tried_note == "already_tried_worked"


def test_an_unset_outcome_is_a_repeat_to_ask_about() -> None:
    for outcome in (None, "", "unclear", "unknown", "maybe"):
        tried = [{"what": "colour coded folders", "outcome": outcome}]
        v = evaluate_idea("Use colour-coded folders for each customer.", PROBLEM, None, tried)
        assert v.kind is IdeaKind.REPEATS_TRIED and v.reason == "tried_unclear", (outcome, v)
    v = evaluate_idea(
        "Use colour-coded folders for each customer.", PROBLEM, None, ["colour coded folders"]
    )
    assert v.reason == "tried_unclear"


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        ("failed", "tried_failed"),
        ("it got lost", "tried_failed"),
        ("no effect", "tried_failed"),
        ("did not help", "tried_failed"),
        ("kaam nahi kiya", "tried_failed"),
        ("فائدہ نہیں ہوا", "tried_failed"),
        ("لم ينجح", "tried_failed"),
        ("काम नहीं किया", "tried_failed"),
        ("unclear", "tried_unclear"),
        ("no time", "tried_unclear"),
    ],
)
def test_free_text_outcomes_are_read(outcome: str, reason: str) -> None:
    tried = [{"what": "colour coded folders", "outcome": outcome}]
    v = evaluate_idea("Use colour-coded folders for each customer.", PROBLEM, None, tried)
    assert v.reason == reason


@pytest.mark.parametrize(
    "outcome",
    ["worked", "it worked well", "helped a lot", "kaam kiya", "کام کیا", "نجح", "काम किया"],
)
def test_free_text_worked_outcomes(outcome: str) -> None:
    tried = [{"what": "colour coded folders", "outcome": outcome}]
    v = evaluate_idea("Use colour-coded folders for each customer.", PROBLEM, None, tried)
    assert v.kind is not IdeaKind.REPEATS_TRIED and v.tried_note == "already_tried_worked"


def test_a_failed_entry_beats_a_worked_one_for_the_same_remedy() -> None:
    tried = [
        {"what": "colour coded folders", "outcome": "worked"},
        {"what": "colour coded folders", "outcome": "failed"},
    ]
    v = evaluate_idea("Use colour-coded folders for each customer.", PROBLEM, None, tried)
    assert v.reason == "tried_failed"


def test_two_concept_tried_item_needs_both_concepts() -> None:
    tried = _tried("colour coded folders")
    assert (
        evaluate_idea("Keep one folder per customer.", PROBLEM, None, tried).kind
        is not IdeaKind.REPEATS_TRIED
    )
    assert (
        evaluate_idea("Use colours on the files.", PROBLEM, None, tried).kind
        is IdeaKind.REPEATS_TRIED
    )


def test_gate_violation_still_beats_a_repeat() -> None:
    def gate(i, c, lg):  # type: ignore[no-untyped-def]
        class V:
            status = "violates"
            rule = "tried_failed"
            reason = "x"

        return V()

    v = evaluate_idea(
        "Use colour-coded folders.",
        PROBLEM,
        None,
        _tried("colour coded folders"),
        constraint_gate=gate,
    )
    assert v.kind is IdeaKind.VIOLATES_CONSTRAINT


# ----- precedence, shapes and thresholds (found by the mutation pass) ----------------------------------------

IDEA = "Use colour-coded folders for each customer."


@pytest.mark.parametrize(
    ("outcomes", "reason"),
    [
        (("failed", "unclear"), "tried_failed"),
        (("unclear", "failed"), "tried_failed"),
        (("failed", "worked"), "tried_failed"),
        (("worked", "failed"), "tried_failed"),
        (("unclear", "worked"), "tried_unclear"),
        (("worked", "unclear"), "tried_unclear"),
    ],
)
def test_precedence_does_not_depend_on_order(outcomes: tuple[str, str], reason: str) -> None:
    tried = [{"what": "colour coded folders", "outcome": o} for o in outcomes]
    v = evaluate_idea(IDEA, PROBLEM, None, tried)
    assert v.kind is IdeaKind.REPEATS_TRIED and v.reason == reason


def test_worked_only_gives_a_note_and_normal_relevance() -> None:
    probs = [
        {
            "id": "p1",
            "title": "Customer files get mixed up",
            "user_words": ["files get mixed up"],
            "category": "operations_process",
        }
    ]
    v = evaluate_idea(IDEA, probs, None, [{"what": "colour coded folders", "outcome": "worked"}])
    assert v.kind is not IdeaKind.REPEATS_TRIED and v.tried_note == "already_tried_worked"
    v = evaluate_idea(
        "Send a reminder.", probs, None, [{"what": "colour coded folders", "outcome": "worked"}]
    )
    assert v.tried_note == ""


def test_tried_shapes_never_break_and_a_blank_item_is_skipped() -> None:
    for tried in (
        {"what": "colour coded folders"},
        5,
        [None, 5, {"what": 7}, {"what": "  "}, {"outcome": "failed"}],
    ):
        v = evaluate_idea(IDEA, PROBLEM, None, tried)
        assert v.kind is not IdeaKind.REPEATS_TRIED
    v = evaluate_idea(
        IDEA,
        PROBLEM,
        None,
        [None, {"what": ""}, {"what": "colour coded folders", "outcome": "failed"}],
    )
    assert v.reason == "tried_failed"


def test_the_channel_a_thing_was_done_in_is_not_the_thing() -> None:
    tried = _tried("a WhatsApp group")
    assert (
        evaluate_idea("Send the customer a WhatsApp message.", PROBLEM, None, tried).kind
        is not IdeaKind.REPEATS_TRIED
    )
    assert (
        evaluate_idea("Create a group chat for the team.", PROBLEM, None, tried).kind
        is IdeaKind.REPEATS_TRIED
    )
    tried = _tried("ads on Facebook")
    assert (
        evaluate_idea("Post on Facebook every day.", PROBLEM, None, tried).kind
        is not IdeaKind.REPEATS_TRIED
    )


def test_word_overlap_fallback_needs_two_words_and_most_of_the_tried_item() -> None:
    tried = _tried("phoned every overdue customer personally")
    assert (
        evaluate_idea("Phone every overdue customer personally.", PROBLEM, None, tried).kind
        is IdeaKind.REPEATS_TRIED
    )
    assert (
        evaluate_idea("Phone the supplier.", PROBLEM, None, tried).kind
        is not IdeaKind.REPEATS_TRIED
    )
    assert (
        evaluate_idea(
            "Phone every overdue account and every supplier and every agent.",
            PROBLEM,
            None,
            _tried("phoned overdue accounts suppliers agents drivers dealers"),
        ).kind
        is not IdeaKind.REPEATS_TRIED
    )


def test_a_three_concept_tried_item_needs_two_of_them() -> None:
    tried = _tried("colour coded folders with labels")
    assert (
        evaluate_idea("Put a tag on each file.", PROBLEM, None, tried).kind
        is IdeaKind.REPEATS_TRIED
    )
    assert (
        evaluate_idea("Put colours on the folders.", PROBLEM, None, tried).kind
        is IdeaKind.REPEATS_TRIED
    )
    assert (
        evaluate_idea("Give each customer a folder.", PROBLEM, None, tried).kind
        is not IdeaKind.REPEATS_TRIED
    )
