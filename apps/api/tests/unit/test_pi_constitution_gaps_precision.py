# ruff: noqa: E501  (one phrase per line reads better than wrapped strings)
"""Precision of the gap rules: normal replies must pass every one of them clean.

For each language family (English, Roman Urdu, Urdu script, Arabic, Hindi) at least 100 ordinary
replies are built from written phrases: a noted line about one problem plus one closed or choice
question, under a conversation with an earlier, different problem and question. A few hand-written
replies (a limit with a next step, an answer to a yes/no question, a neutral list) are added. None of
them may raise any rule in constitution_gaps. Run with -s to see the counts."""

import pytest

from app.modules.pi import constitution_gaps as gaps

AI = {"role": "ai", "text": "Hi, I'm pi, an AI from Workzap. What is going wrong?"}

FAMILIES = {
    "en": {
        "problems": [
            "stock running out",
            "cashiers coming late",
            "daily cash not matching",
            "customers waiting too long",
            "suppliers delivering late",
            "orders getting lost",
            "prices being unclear",
            "staff leaving often",
            "bills going unpaid",
            "returns piling up",
            "deliveries going to the wrong address",
            "reports taking days",
        ],
        "noted": ["Noted: {p}.", "Got it, {p}.", "That makes sense, {p} is clearly costing you."],
        "questions": [
            "Is it every shop, or only some?",
            "Does it happen daily, or weekly?",
            "Is it the main shop, or a smaller one?",
            "Is it mostly mornings, or evenings?",
            "Is it new, or has it always been like this?",
            "Is it a few items, or many?",
            "Does it cost you more in time, or in money?",
            "Is it mostly on weekdays, or at weekends?",
            "Is it the same people each time, or different ones?",
        ],
        "said": "Honestly the biggest thing for us is {p}, and it has been this way for months now",
        "brief": ["yes", "mostly", "daily", "two"],
        "extra": [
            (
                "I can't give tax advice, but I can note it for the team. Which shop is it?",
                "how much tax should I pay on this",
            ),
            (
                "Yes, I can help with stock. Is it every shop, or only some?",
                "Can you help with stock?",
            ),
            (
                "No, Workzap doesn't do payroll. Is the stock problem in every shop, or some?",
                "Do you do payroll?",
            ),
            ("That's a lot to carry. Which shop is hit hardest?", "I'm going bankrupt"),
            (
                "Share what you're comfortable with. Which shop is it?",
                "I'd rather not say the amount",
            ),
            (
                "Noted: the Gulberg branch running out. Is it every day, or weekly?",
                "the Gulberg branch runs out of stock",
            ),
            ("You decide where to start. Is it stock, or staff?", "I have three problems"),
            (
                "Would it help to count the slips each evening? Is it every shop, or some?",
                "cash does not match",
            ),
        ],
    },
    "roman_ur": {
        "problems": [
            "stock khatam ho jata hai",
            "cashier der se aate hain",
            "roz ka cash match nahi karta",
            "customer ko bohat intezar karna parta hai",
            "supplier maal der se bhejta hai",
            "orders kho jate hain",
            "qeematon ka pata nahi chalta",
            "staff aksar chora jata hai",
            "bills adaa nahi hote",
            "return ka maal jama ho raha hai",
            "delivery galat pate par chali jati hai",
            "reports ko din lag jate hain",
        ],
        "noted": ["Note kar liya: {p}.", "Samajh gaya, {p}.", "Theek hai, {p} ka asar saaf hai."],
        "questions": [
            "Har dukaan mein hota hai ya sirf kuch mein?",
            "Roz hota hai ya hafte mein?",
            "Bari dukaan par hota hai ya choti par?",
            "Zyada tar subah hota hai ya shaam ko?",
            "Ye naya hai ya hamesha se aisa hai?",
            "Kuch cheezon mein hai ya bohat si mein?",
            "Waqt ka nuksan zyada hai ya paise ka?",
            "Hafte ke din zyada hota hai ya weekend par?",
            "Har baar wohi log hote hain ya alag?",
        ],
        "said": "Sach batayen to hamara sab se bara masla yeh hai ke {p}, aur kai mahine se aisa hi chal raha hai",
        "brief": ["haan", "zyada tar", "roz", "do"],
        "extra": [
            (
                "Ye main nahi kar sakta, magar main team ko bata sakta hoon. Kaunsi dukaan hai?",
                "tax kitna dena chahiye",
            ),
            (
                "Haan, kar sakte hain. Har dukaan mein hota hai ya sirf kuch mein?",
                "kya aap stock ka masla theek kar sakte hain?",
            ),
            (
                "Ye bohat mushkil waqt hai. Kaunsi dukaan sab se zyada mutasir hai?",
                "business doob raha hai, dewaliya ho jaunga",
            ),
            (
                "Theek hai, jitna aap chahen utna batayen. Kaunsi dukaan se shuru karein?",
                "yeh batana nahi chahta",
            ),
        ],
    },
    "ur": {
        "problems": [
            "اسٹاک ختم ہو جاتا ہے",
            "کیشیئر دیر سے آتے ہیں",
            "روزانہ کا کیش نہیں ملتا",
            "گاہکوں کو بہت انتظار کرنا پڑتا ہے",
            "سپلائر مال دیر سے بھیجتا ہے",
            "آرڈر کھو جاتے ہیں",
            "قیمتوں کا پتہ نہیں چلتا",
            "عملہ اکثر چھوڑ جاتا ہے",
            "بل ادا نہیں ہوتے",
            "واپسی کا مال جمع ہو رہا ہے",
            "ڈیلیوری غلط پتے پر چلی جاتی ہے",
            "رپورٹوں میں دن لگ جاتے ہیں",
        ],
        "noted": ["نوٹ کر لیا: {p}۔", "سمجھ گیا، {p}۔", "ٹھیک ہے، {p} کا اثر واضح ہے۔"],
        "questions": [
            "کیا یہ ہر دکان میں ہوتا ہے یا صرف کچھ میں؟",
            "کیا یہ روز ہوتا ہے یا ہفتے میں؟",
            "کیا یہ بڑی دکان پر ہوتا ہے یا چھوٹی پر؟",
            "کیا یہ زیادہ تر صبح ہوتا ہے یا شام کو؟",
            "کیا یہ نیا ہے یا ہمیشہ سے ایسا ہے؟",
            "کیا یہ چند چیزوں میں ہے یا بہت سی میں؟",
            "کیا وقت کا نقصان زیادہ ہے یا پیسے کا؟",
            "کیا یہ ہفتے کے دن زیادہ ہوتا ہے یا اختتام ہفتہ پر؟",
            "کیا ہر بار وہی لوگ ہوتے ہیں یا مختلف؟",
        ],
        "said": "سچ پوچھیں تو ہمارا سب سے بڑا مسئلہ یہ ہے کہ {p}، اور کئی مہینوں سے ایسا ہی چل رہا ہے",
        "brief": ["جی ہاں", "زیادہ تر", "روز", "دو"],
        "extra": [
            ("میں یہ نہیں کر سکتا، مگر میں ٹیم کو بتا سکتا ہوں۔ کون سی دکان ہے؟", "ٹیکس کتنا دوں"),
            (
                "جی ہاں، کر سکتے ہیں۔ کیا یہ ہر دکان میں ہوتا ہے یا کچھ میں؟",
                "کیا آپ اسٹاک کا مسئلہ حل کر سکتے ہیں؟",
            ),
            ("یہ بہت مشکل وقت ہے۔ کون سی دکان زیادہ متاثر ہے؟", "میں دیوالیہ ہونے والا ہوں"),
            ("ٹھیک ہے، جتنا آپ چاہیں بتائیں۔ کون سی دکان سے شروع کریں؟", "یہ میں نہیں بتانا چاہتا"),
        ],
    },
    "ar": {
        "problems": [
            "نفاد المخزون",
            "تأخر الكاشيرات",
            "عدم تطابق النقد اليومي",
            "انتظار العملاء طويلاً",
            "تأخر المورد في التوصيل",
            "ضياع الطلبات",
            "غموض الأسعار",
            "كثرة مغادرة الموظفين",
            "الفواتير غير المدفوعة",
            "تراكم المرتجعات",
            "وصول التوصيل لعنوان خاطئ",
            "استغراق التقارير أياماً",
        ],
        "noted": ["تم تسجيل: {p}.", "فهمت، {p}.", "حسناً، {p} واضح الأثر."],
        "questions": [
            "هل يحدث في كل الفروع أم في بعضها؟",
            "هل يحدث يومياً أم أسبوعياً؟",
            "هل هو في الفرع الكبير أم الصغير؟",
            "هل يحدث غالباً صباحاً أم مساءً؟",
            "هل هذا جديد أم كان دائماً هكذا؟",
            "هل هي أشياء قليلة أم كثيرة؟",
            "هل الخسارة في الوقت أكثر أم في المال؟",
            "هل يحدث في أيام الأسبوع أكثر أم في عطلة النهاية؟",
            "هل هم نفس الأشخاص كل مرة أم مختلفون؟",
        ],
        "said": "أكبر مشكلة عندنا هي {p} وهذا مستمر منذ شهور",
        "brief": ["نعم", "غالباً", "يومياً", "اثنان"],
        "extra": [
            ("لا أستطيع فعل ذلك، لكن يمكنني تدوينه للفريق. أي فرع هو؟", "كم الضريبة التي أدفعها"),
            ("نعم، يمكنني ذلك. هل يحدث في كل الفروع أم في بعضها؟", "هل يمكنك حل مشكلة المخزون؟"),
            ("أتفهم أن هذا ثقيل جداً. أي فرع الأكثر تأثراً؟", "سأفلس قريباً"),
            ("لا بأس، شاركني فقط ما تشعر بالراحة تجاهه. أي فرع نبدأ به؟", "لا أريد أن أذكر المبلغ"),
        ],
    },
    "hi": {
        "problems": [
            "स्टॉक खत्म हो जाता है",
            "कैशियर देर से आते हैं",
            "रोज़ का कैश नहीं मिलता",
            "ग्राहकों को बहुत इंतज़ार करना पड़ता है",
            "सप्लायर माल देर से भेजता है",
            "ऑर्डर खो जाते हैं",
            "कीमतों का पता नहीं चलता",
            "स्टाफ अक्सर छोड़ जाता है",
            "बिल चुकाए नहीं जाते",
            "वापसी का माल जमा हो रहा है",
            "डिलीवरी गलत पते पर चली जाती है",
            "रिपोर्ट में दिन लग जाते हैं",
        ],
        "noted": ["नोट कर लिया: {p}।", "समझ गया, {p}।", "ठीक है, {p} का असर साफ़ है।"],
        "questions": [
            "क्या यह हर दुकान में होता है या सिर्फ कुछ में?",
            "क्या यह रोज़ होता है या हफ्ते में?",
            "क्या यह बड़ी दुकान पर होता है या छोटी पर?",
            "क्या यह ज़्यादातर सुबह होता है या शाम को?",
            "क्या यह नया है या हमेशा से ऐसा है?",
            "क्या यह कुछ चीज़ों में है या बहुत सी में?",
            "क्या समय का नुकसान ज़्यादा है या पैसे का?",
            "क्या यह हफ्ते के दिनों में ज़्यादा होता है या सप्ताहांत पर?",
            "क्या हर बार वही लोग होते हैं या अलग?",
        ],
        "said": "सच कहूँ तो हमारी सबसे बड़ी समस्या यह है कि {p}, और कई महीनों से ऐसा ही चल रहा है",
        "brief": ["हाँ", "ज़्यादातर", "रोज़", "दो"],
        "extra": [
            ("मैं यह नहीं कर सकता, पर मैं टीम को बता सकता हूँ। कौन सी दुकान है?", "टैक्स कितना दूँ"),
            ("हाँ, कर सकते हैं। क्या यह हर दुकान में होता है या कुछ में?", "क्या आप स्टॉक की समस्या हल कर सकते हैं?"),
            ("यह बहुत मुश्किल समय है। कौन सी दुकान सबसे ज़्यादा प्रभावित है?", "मैं दिवालिया हो जाऊँगा"),
            ("ठीक है, जितना आप चाहें उतना बताइए। किस दुकान से शुरू करें?", "यह मैं नहीं बताना चाहता"),
        ],
    },
}


def noted_line_of(spec, problem):
    return spec["noted"][0].format(p=problem)


def build(family):
    spec = FAMILIES[family]
    problems, questions, noted = spec["problems"], spec["questions"], spec["noted"]
    items = []
    for i, problem in enumerate(problems):
        for j, question in enumerate(questions):
            earlier = problems[(i + 5) % len(problems)]
            earlier_question = questions[(j + 3) % len(questions)]
            history = [
                AI,
                {"role": "customer", "text": spec["said"].format(p=earlier)},
                {"role": "ai", "text": f"{noted_line_of(spec, earlier)} {earlier_question}"},
            ]
            reply = f"{noted[(i + j) % len(noted)].format(p=problem)} {question}"
            items.append(
                (
                    reply,
                    {"latest_customer_message": spec["said"].format(p=problem), "history": history},
                )
            )
    for k, short in enumerate(spec["brief"]):
        for j, question in enumerate(questions[:4]):
            history = [
                AI,
                {"role": "customer", "text": spec["brief"][(k + 1) % 4]},
                {"role": "ai", "text": questions[(j + 4) % len(questions)]},
            ]
            items.append((question, {"latest_customer_message": short, "history": history}))
    for reply, latest in spec["extra"]:
        items.append((reply, {"latest_customer_message": latest, "history": [AI]}))
    return items


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_normal_replies_raise_no_gap_rule(family, capsys):
    items = build(family)
    assert len(items) >= 100, f"{family}: only {len(items)} replies"
    bad = [(reply, [f[0] for f in gaps.check(reply, context)]) for reply, context in items]
    bad = [b for b in bad if b[1]]
    with capsys.disabled():
        print(
            f"\nprecision {family}: {len(items) - len(bad)}/{len(items)} normal replies clean, {len(bad)} false positives"
        )
    assert not bad, bad[:5]
