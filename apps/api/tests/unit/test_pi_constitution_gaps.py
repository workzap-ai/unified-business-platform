# ruff: noqa: E501  (one case per line reads better than wrapped strings)
"""Rules that were enforced only in the prompt, or only narrowly, now checked in code
(app/modules/pi/constitution_gaps.py): R-PRIV-08, R-VOICE-11, R-ASK-03/04/05, R-MEM-02, R-CANT-01/02,
X5, R-PROM-02/03, R-SOL-09, R-ANS-02, R-ECHO-01/02.

Every rule has cases that must be caught and cases that must pass clean, across English, Roman Urdu,
Urdu script, Arabic and Hindi (French and Spanish where the rule has a phrase set for them)."""

import pytest

from app.modules.pi import constitution as c
from app.modules.pi import constitution_gaps as gaps

AI_TURN = {"role": "ai", "text": "Hi, I'm pi, an AI from Workzap. What is going wrong?"}


def ctx(latest, convo=(), **extra):
    history = [AI_TURN]
    for who, text in convo:
        history.append({"role": "customer" if who == "c" else "ai", "text": text})
    return {"latest_customer_message": latest, "history": history, **extra}


def broke(reply, context):
    return {f[0] for f in gaps.check(reply, context)}


def state(name):
    return {"flow": {"state": name}}


BRIEF = (("c", "stock"), ("a", "Noted: stock. Which part of it?"), ("c", "yes"))

CASES: dict[str, dict[str, list]] = {
    "R-PRIV-08": {
        "bad": [
            (
                "You have to tell me the amount. Roughly how much is it?",
                ctx("I'd rather not say how much we lose"),
            ),
            (
                "I need you to share it, otherwise I can't help. What is the figure?",
                ctx("it's private"),
            ),
            (
                "Aap ko batana hoga, bas bata dein. Kitna nuksan hota hai?",
                ctx("yeh batana nahi chahta"),
            ),
            ("آپ کو بتانا ہوگا۔ کتنا نقصان ہوتا ہے؟", ctx("یہ میں نہیں بتانا چاہتا")),
            ("يجب أن تخبرني بالمبلغ. كم الخسارة؟", ctx("لا أريد أن أذكر المبلغ")),
            ("आपको बताना होगा। कितना नुकसान होता है?", ctx("यह मैं नहीं बताना चाहता")),
            (
                "Come on, just tell me the number. How much is it?",
                ctx("I am not comfortable sharing that"),
            ),
        ],
        "good": [
            (
                "Share what you're comfortable with. Which shop is it?",
                ctx("I'd rather not say how much we lose"),
            ),
            ("No problem, we can skip that. Which shop loses stock first?", ctx("it's private")),
            (
                "Theek hai, jitna aap chahen utna batayen. Kaunsi dukaan se shuru karein?",
                ctx("yeh batana nahi chahta"),
            ),
            (
                "ٹھیک ہے، جتنا آپ چاہیں بتائیں۔ کون سی دکان سے شروع کریں؟",
                ctx("یہ میں نہیں بتانا چاہتا"),
            ),
            (
                "لا بأس، شاركني فقط ما تشعر بالراحة تجاهه. أي فرع نبدأ به؟",
                ctx("لا أريد أن أذكر المبلغ"),
            ),
            ("ठीक है, जितना आप चाहें उतना बताइए। किस दुकान से शुरू करें?", ctx("यह मैं नहीं बताना चाहता")),
            (
                "You need to tell me which shop it is. Which one?",
                ctx("the second shop is the problem"),
            ),
        ],
    },
    "R-VOICE-11": {
        "bad": [
            (
                "Noted: stock runs out at Location 2. Is it every day?",
                ctx("the Gulberg branch runs out"),
            ),
            (
                "Branch B has late cashiers. Is it only weekends?",
                ctx("cashiers at the Gulberg branch are late"),
            ),
            (
                "Dukaan 2 mein stock khatam hota hai. Roz hota hai?",
                ctx("Gulberg wali dukaan mein stock khatam hota hai"),
            ),
            (
                "دکان 2 میں اسٹاک ختم ہوتا ہے۔ کیا روز ہوتا ہے؟",
                ctx("گلبرگ والی دکان میں اسٹاک ختم ہوتا ہے"),
            ),
            ("الفرع 2 يعاني من نقص المخزون. هل يحدث يومياً؟", ctx("فرع الجلبرغ ينقصه المخزون")),
            ("दुकान 2 में स्टॉक खत्म होता है। क्या रोज़ होता है?", ctx("गुलबर्ग वाली दुकान में स्टॉक खत्म होता है")),
            (
                "Store C keeps running out of change. Is it every week?",
                ctx("one regular keeps returning items"),
            ),
        ],
        "good": [
            (
                "Noted: Gulberg branch running out. Is it every day?",
                ctx("the Gulberg branch runs out"),
            ),
            ("Noted: Shop C cash mismatch. Is it daily?", ctx("Shop C cash does not match")),
            ("How many branches do you have?", ctx("we keep running out of stock")),
            ("Is it step 2 of the process that is slow?", ctx("the process is slow")),
            (
                "Gulberg wali dukaan mein stock khatam hota hai. Roz hota hai?",
                ctx("Gulberg wali dukaan mein stock khatam hota hai"),
            ),
            (
                "گلبرگ والی دکان میں اسٹاک ختم ہوتا ہے۔ کیا روز ہوتا ہے؟",
                ctx("گلبرگ والی دکان میں اسٹاک ختم ہوتا ہے"),
            ),
            ("فرع الجلبرغ ينقصه المخزون. هل يحدث يومياً؟", ctx("فرع الجلبرغ ينقصه المخزون")),
            (
                "गुलबर्ग वाली दुकान में स्टॉक खत्म होता है। क्या रोज़ होता है?",
                ctx("गुलबर्ग वाली दुकान में स्टॉक खत्म होता है"),
            ),
        ],
    },
    "R-ASK-04": {
        "bad": [
            ("Noted. How does that happen in your shops?", ctx("mostly", BRIEF)),
            ("Why do you think it happens?", ctx("mostly", BRIEF)),
            ("Can you describe what happens then?", ctx("mostly", BRIEF)),
            ("Ye kaise hota hai?", ctx("zyada tar", BRIEF)),
            ("Is ke peeche kya wajah hai, tafseel se batayen?", ctx("zyada tar", BRIEF)),
            ("یہ کیسے ہوتا ہے؟", ctx("زیادہ تر", BRIEF)),
            ("كيف يحدث ذلك؟", ctx("غالباً", BRIEF)),
            ("यह कैसे होता है?", ctx("ज़्यादातर", BRIEF)),
        ],
        "good": [
            ("Every shop, or only some?", ctx("mostly", BRIEF)),
            ("How many shops does it happen in?", ctx("mostly", BRIEF)),
            ("Har dukaan mein ya sirf kuch mein?", ctx("zyada tar", BRIEF)),
            ("ہر دکان میں یا صرف کچھ میں؟", ctx("زیادہ تر", BRIEF)),
            ("في كل الفروع أم بعضها فقط؟", ctx("غالباً", BRIEF)),
            ("हर दुकान में या सिर्फ कुछ में?", ctx("ज़्यादातर", BRIEF)),
            (
                "How does that happen?",
                ctx(
                    "it happens at the end of every month when the supplier delivers late and the shelves are already empty by then",
                    BRIEF,
                ),
            ),
            ("What is going on?", ctx("hi", ())),
        ],
    },
    "R-ASK-05R": {
        "bad": [
            (
                "How many staff are on the evening shift?",
                ctx(
                    "skip",
                    (("c", "stock runs out"), ("a", "How many staff work in the evening shift?")),
                ),
            ),
            (
                "Roughly how many evening staff do you have?",
                ctx("idk", (("a", "How many staff work in the evening shift?"),)),
            ),
            (
                "Shaam ki shift mein kitne log hote hain?",
                ctx("pata nahi", (("a", "Shaam ki shift mein kitne log kaam karte hain?"),)),
            ),
            (
                "شام کی شفٹ میں کتنے لوگ ہوتے ہیں؟",
                ctx("پتہ نہیں", (("a", "شام کی شفٹ میں کتنے لوگ کام کرتے ہیں؟"),)),
            ),
            (
                "كم عدد الموظفين في الوردية المسائية تقريباً؟",
                ctx("لا أعرف", (("a", "كم عدد الموظفين في الوردية المسائية؟"),)),
            ),
            (
                "शाम की शिफ्ट में कितने लोग होते हैं?",
                ctx("पता नहीं", (("a", "शाम की शिफ्ट में कितने लोग काम करते हैं?"),)),
            ),
        ],
        "good": [
            (
                "Which shop is busiest?",
                ctx("skip", (("a", "How many staff work in the evening shift?"),)),
            ),
            (
                "How many staff work in the evening shift, roughly?",
                ctx("what do you mean?", (("a", "How many staff work in the evening shift?"),)),
            ),
            (
                "Which shop opens first?",
                ctx("about six", (("a", "How many staff work in the evening shift?"),)),
            ),
            (
                "How many staff work in the evening shift?",
                ctx(
                    "why do you ask that again today?",
                    (("a", "How many staff work in the evening shift?"),),
                ),
            ),
            (
                "Kaunsi dukaan sab se pehle khulti hai?",
                ctx("pata nahi", (("a", "Shaam ki shift mein kitne log kaam karte hain?"),)),
            ),
            (
                "کون سی دکان سب سے پہلے کھلتی ہے؟",
                ctx("پتہ نہیں", (("a", "شام کی شفٹ میں کتنے لوگ کام کرتے ہیں؟"),)),
            ),
            ("أي فرع يفتح أولاً؟", ctx("لا أعرف", (("a", "كم عدد الموظفين في الوردية المسائية؟"),))),
            (
                "कौन सी दुकान सबसे पहले खुलती है?",
                ctx("पता नहीं", (("a", "शाम की शिफ्ट में कितने लोग काम करते हैं?"),)),
            ),
            (
                "How many staff work in the morning shift?",
                ctx("six", (("a", "How many staff work in the evening shift?"),)),
            ),
        ],
    },
    "R-CANT-02": {
        "bad": [
            ("I can't do that.", ctx("how much tax should I pay")),
            ("Sorry, I can't help with tax.", ctx("how much tax should I pay")),
            ("Ye main nahi kar sakta.", ctx("tax kitna dena chahiye")),
            ("میں یہ نہیں کر سکتا۔", ctx("ٹیکس کتنا دوں")),
            ("لا أستطيع فعل ذلك.", ctx("كم الضريبة التي أدفعها")),
            ("मैं यह नहीं कर सकता।", ctx("टैक्स कितना दूँ")),
            ("Je ne peux pas faire cela.", ctx("combien d'impôt dois-je payer")),
        ],
        "good": [
            (
                "I can't do that. I can note it for the team instead.",
                ctx("how much tax should I pay"),
            ),
            ("I can't do that. Which shop is it?", ctx("how much tax should I pay")),
            (
                "Ye main nahi kar sakta. Main team ko bata sakta hoon.",
                ctx("tax kitna dena chahiye"),
            ),
            ("میں یہ نہیں کر سکتا۔ میں ٹیم کو بتا سکتا ہوں۔", ctx("ٹیکس کتنا دوں")),
            ("لا أستطيع فعل ذلك. لكن يمكنني تدوينه.", ctx("كم الضريبة التي أدفعها")),
            ("मैं यह नहीं कर सकता। मैं टीम को बता सकता हूँ।", ctx("टैक्स कितना दूँ")),
            ("Noted: stock runs out.", ctx("stock runs out")),
        ],
    },
    "X5": {
        "bad": [
            ("Noted: going bankrupt. Which shop is hit hardest?", ctx("I'm going bankrupt")),
            (
                "If you are in danger please call 1122. I'm here for the business side.",
                ctx("I'm going bankrupt"),
            ),
            (
                "That's a lot to carry. You should take a loan to get through this.",
                ctx("I'm going bankrupt"),
            ),
            (
                "Note kar liya: dewaliya. Kaunsi dukaan sab se zyada mutasir hai?",
                ctx("business doob raha hai, dewaliya ho jaunga"),
            ),
            ("نوٹ کر لیا: دیوالیہ۔ کون سی دکان زیادہ متاثر ہے؟", ctx("میں دیوالیہ ہونے والا ہوں")),
            ("تم تسجيل: الإفلاس. أي فرع الأكثر تأثراً؟", ctx("سأفلس قريباً")),
            ("नोट कर लिया: दिवालिया। कौन सी दुकान सबसे ज़्यादा प्रभावित है?", ctx("मैं दिवालिया हो जाऊँगा")),
        ],
        "good": [
            ("That's a lot to carry. Which shop is hit hardest?", ctx("I'm going bankrupt")),
            ("I'm sorry, that sounds heavy. Which shop is hit hardest?", ctx("I'm going bankrupt")),
            (
                "Ye bohat mushkil waqt hai. Kaunsi dukaan sab se zyada mutasir hai?",
                ctx("business doob raha hai, dewaliya ho jaunga"),
            ),
            ("یہ بہت مشکل وقت ہے۔ کون سی دکان زیادہ متاثر ہے؟", ctx("میں دیوالیہ ہونے والا ہوں")),
            ("أتفهم أن هذا ثقيل جداً. أي فرع الأكثر تأثراً؟", ctx("سأفلس قريباً")),
            ("यह बहुत मुश्किल समय है। कौन सी दुकान सबसे ज़्यादा प्रभावित है?", ctx("मैं दिवालिया हो जाऊँगा")),
            ("Noted: stock runs out. Which shop?", ctx("stock runs out")),
            (
                "Please call 1122 now, help is available.",
                ctx("I'm going bankrupt and I want to die"),
            ),
        ],
    },
    "R-PROM-02": {
        "bad": [
            (
                "I've decided: go with the cheaper supplier. Is that fine?",
                ctx("two suppliers are offering"),
            ),
            (
                "You need to close the second shop. Which one is weaker?",
                ctx("two shops lose money"),
            ),
            ("You must fire the manager today. Which shop?", ctx("the manager is slow")),
            (
                "Main ne faisla kar liya ke manager hatana hai. Kaunsi dukaan?",
                ctx("manager sust hai"),
            ),
            ("میں نے فیصلہ کر لیا کہ مینیجر کو ہٹانا ہے۔ کون سی دکان؟", ctx("مینیجر سست ہے")),
            ("قررت أن تغلق الفرع الثاني. أي فرع؟", ctx("فرعان يخسران")),
            ("मैंने फैसला कर लिया कि मैनेजर को हटाना है। कौन सी दुकान?", ctx("मैनेजर सुस्त है")),
        ],
        "good": [
            (
                "Here is what I have noted: stock, staff, cash. Which would you like to start with?",
                ctx("three things are wrong"),
            ),
            ("You decide which comes first. Which one?", ctx("three things are wrong")),
            (
                "Noted: the consultant said my recommendation is to fire the manager. Which shop?",
                ctx("the consultant wrote my recommendation is to fire the manager"),
            ),
            ("You need to tell me which shop it is. Which one?", ctx("the second shop")),
            ("Aap faisla karenge. Kaunsi cheez pehle dekhein?", ctx("teen masle hain")),
            ("فیصلہ آپ کا ہے۔ پہلے کیا دیکھیں؟", ctx("تین مسئلے ہیں")),
            ("القرار لك. بماذا نبدأ؟", ctx("ثلاث مشاكل")),
            ("फैसला आपका है। पहले क्या देखें?", ctx("तीन समस्याएँ हैं")),
        ],
    },
    "R-PROM-03": {
        "bad": [
            ("Your sales will drop next month. Which shop?", ctx("stock runs out")),
            ("Sales will rise soon. Is it every shop?", ctx("sales are flat")),
            ("In six months your business will recover. Which shop?", ctx("business is slow")),
            ("Aap ki sales barh jayengi. Kaunsi dukaan?", ctx("sales flat hain")),
            ("آپ کی فروخت بڑھے گی۔ کون سی دکان؟", ctx("فروخت کم ہے")),
            ("المبيعات ستزداد قريباً. أي فرع؟", ctx("المبيعات ثابتة")),
            ("आपकी बिक्री बढ़ेगी। कौन सी दुकान?", ctx("बिक्री कम है")),
            ("Next year you'll be out of business. Which shop?", ctx("we lose money")),
        ],
        "good": [
            ("Sales are dropping at which shop?", ctx("stock runs out")),
            ("If sales drop further, tell me which shop. Which one first?", ctx("sales are flat")),
            (
                "Noted: sales may drop next month. Is it every shop?",
                ctx("my sales will drop next month, I think"),
            ),
            ("Would sales drop in every shop?", ctx("sales are flat")),
            ("Sales kam ho rahi hain, kaunsi dukaan mein?", ctx("sales flat hain")),
            ("فروخت کم ہو رہی ہے، کس دکان میں؟", ctx("فروخت کم ہے")),
            ("المبيعات تنخفض في أي فرع؟", ctx("المبيعات ثابتة")),
            ("बिक्री कम हो रही है, किस दुकान में?", ctx("बिक्री कम है")),
        ],
    },
    "R-SOL-09": {
        "bad": [
            (
                "Give the cows an antibiotic injection after calving. Which farm?",
                ctx("milk is down"),
            ),
            ("Apply urea twice before sowing. Is it wheat?", ctx("the crop is weak")),
            ("You can claim the tax deduction on that. Which shop?", ctx("rent is high")),
            (
                "Take paracetamol for the headache. Which shop?",
                ctx("my head hurts and sales are low"),
            ),
            (
                "Refinance your loan at a lower interest rate. Which bank?",
                ctx("repayments are heavy"),
            ),
            ("Fasal par urea daalein. Konsi fasal hai?", ctx("fasal kamzor hai")),
            ("فصل پر یوریا ڈالیں۔ کون سی فصل ہے؟", ctx("فصل کمزور ہے")),
            ("ضع سماد اليوريا على المحصول. أي محصول؟", ctx("المحصول ضعيف")),
            ("फसल पर यूरिया डालें। कौन सी फसल?", ctx("फसल कमज़ोर है")),
        ],
        "good": [
            ("Do you vaccinate the calves yourself?", ctx("milk is down")),
            ("Give antibiotics yourself, or does the vet?", ctx("milk is down")),
            ("Noted: milk yield dropping at the farm. Which shed?", ctx("milk is down")),
            (
                "Count how many litres each shed gives each morning. Which shed first?",
                ctx("milk is down"),
            ),
            ("You use urea. Which field?", ctx("we use urea on the wheat")),
            ("Har shed ka doodh roz likhein. Kaunsa shed?", ctx("doodh kam hai")),
            ("ہر شیڈ کا دودھ روز لکھیں۔ کون سا شیڈ؟", ctx("دودھ کم ہے")),
            ("سجّل كمية الحليب كل يوم. أي حظيرة؟", ctx("الحليب قليل")),
            ("हर शेड का दूध रोज़ लिखें। कौन सा शेड?", ctx("दूध कम है")),
        ],
    },
    "R-ANS-02": {
        "bad": [
            ("Tell me which shop loses the most stock.", ctx("Can you fix my stock problem?")),
            ("Stock problems are common.", ctx("Can you help with stock problems?")),
            (
                "Stock ka masla kis dukaan mein zyada hai?",
                ctx("kya aap stock ka masla theek kar sakte hain?"),
            ),
            ("اسٹاک کا مسئلہ کس دکان میں زیادہ ہے؟", ctx("کیا آپ اسٹاک کا مسئلہ حل کر سکتے ہیں؟")),
            ("مشكلة المخزون في أي فرع أكثر؟", ctx("هل يمكنك حل مشكلة المخزون؟")),
            ("स्टॉक की समस्या किस दुकान में ज़्यादा है?", ctx("क्या आप स्टॉक की समस्या हल कर सकते हैं?")),
            (
                "Quel magasin perd le plus de stock ?",
                ctx("Pouvez-vous régler mon problème de stock ?"),
            ),
        ],
        "good": [
            ("Yes, I can help with stock. Which shop?", ctx("Can you fix my stock problem?")),
            (
                "No, Workzap doesn't do payroll. Which shop has the stock problem?",
                ctx("Do you do payroll?"),
            ),
            (
                "Haan, kar sakte hain. Kaunsi dukaan?",
                ctx("kya aap stock ka masla theek kar sakte hain?"),
            ),
            ("جی ہاں، کر سکتے ہیں۔ کون سی دکان؟", ctx("کیا آپ اسٹاک کا مسئلہ حل کر سکتے ہیں؟")),
            ("نعم، يمكنني ذلك. أي فرع؟", ctx("هل يمكنك حل مشكلة المخزون؟")),
            ("हाँ, कर सकते हैं। कौन सी दुकान?", ctx("क्या आप स्टॉक की समस्या हल कर सकते हैं?")),
            ("Oui, je peux. Quel magasin ?", ctx("Pouvez-vous régler mon problème de stock ?")),
            ("Noted: stock runs out. Which shop?", ctx("my stock keeps running out")),
            (
                "We handle shops and clinics. Which one is yours?",
                ctx("Do you work with shops or clinics?"),
            ),
        ],
    },
    "R-ECHO-01": {
        "bad": [
            (
                "Noted: best sellers running out. Is it weekly?",
                ctx("it is weekly", (("a", "Noted: best-sellers running out. Which shop?"),)),
            ),
            (
                "Note kar liya: stock khatam ho jata hai. Kaunsi dukaan?",
                ctx("roz hota hai", (("a", "Note kar liya: stock khatam ho jata hai."),)),
            ),
            (
                "نوٹ کر لیا: اسٹاک ختم ہو جاتا ہے۔ کون سی دکان؟",
                ctx("روز ہوتا ہے", (("a", "نوٹ کر لیا: اسٹاک ختم ہو جاتا ہے۔"),)),
            ),
            (
                "تم تسجيل: نفاد المخزون. أي فرع؟",
                ctx("يومياً", (("a", "تم تسجيل: نفاد المخزون."),)),
            ),
            (
                "नोट कर लिया: स्टॉक खत्म हो जाता है। कौन सी दुकान?",
                ctx("रोज़", (("a", "नोट कर लिया: स्टॉक खत्म हो जाता है।"),)),
            ),
            (
                "C'est noté : rupture de stock. Quel magasin ?",
                ctx("tous les jours", (("a", "C'est noté : rupture de stock."),)),
            ),
        ],
        "good": [
            ("Noted: best-sellers running out. Which shop?", ctx("best-sellers keep running out")),
            (
                "Noted: cashiers late on weekends. Is it every shop?",
                ctx("cashiers are late", (("a", "Noted: best-sellers running out. Which shop?"),)),
            ),
            (
                "Note kar liya: cash till se match nahi karta. Kaunsi dukaan?",
                ctx("cash match nahi karta", (("a", "Note kar liya: stock khatam ho jata hai."),)),
            ),
            (
                "نوٹ کر لیا: عملہ دیر سے آتا ہے۔ کون سی دکان؟",
                ctx("عملہ دیر سے آتا ہے", (("a", "نوٹ کر لیا: اسٹاک ختم ہو جاتا ہے۔"),)),
            ),
            (
                "تم تسجيل: تأخر الموظفين. أي فرع؟",
                ctx("الموظفون يتأخرون", (("a", "تم تسجيل: نفاد المخزون."),)),
            ),
            (
                "नोट कर लिया: स्टाफ देर से आता है। कौन सी दुकान?",
                ctx("स्टाफ देर से आता है", (("a", "नोट कर लिया: स्टॉक खत्म हो जाता है।"),)),
            ),
            (
                "Noted: best sellers running out, every shop. Which first?",
                ctx(
                    "every shop",
                    (("a", "Noted: best-sellers running out. Which shop?"),),
                    said_wrong=True,
                ),
            ),
            (
                "Noted: best sellers running out, every shop. Which first?",
                ctx(
                    "no, I meant every shop",
                    (("a", "Noted: best-sellers running out. Which shop?"),),
                    said_wrong=True,
                ),
            ),
        ],
    },
    "R-ECHO-02": {
        "bad": [
            (
                "• Cashiers come late on weekends\n• Daily cash does not match the till\nIs anything missing?",
                ctx(
                    "stock runs out",
                    (
                        ("c", "cashiers come late on weekends"),
                        ("a", "Noted. Anything else?"),
                        ("c", "daily cash does not match the till"),
                        ("a", "Noted. Anything else?"),
                    ),
                    **state("S3_NOTED"),
                ),
            ),
            (
                "- Cashiers come late on weekends\n- Daily cash does not match the till\nIs anything missing?",
                ctx(
                    "stock runs out",
                    (
                        ("c", "cashiers come late on weekends"),
                        ("a", "Noted."),
                        ("c", "daily cash does not match the till"),
                        ("a", "Noted."),
                    ),
                    **state("S1_LISTENING"),
                ),
            ),
            (
                "• cashier weekend par late aate hain\n• roz ka cash till se match nahi karta\nKuch reh gaya?",
                ctx(
                    "stock khatam ho jata hai",
                    (
                        ("c", "cashier weekend par late aate hain"),
                        ("a", "Theek."),
                        ("c", "roz ka cash till se match nahi karta"),
                        ("a", "Theek."),
                    ),
                    **state("S3_NOTED"),
                ),
            ),
            (
                "• ویک اینڈ پر کیشیئر دیر سے آتے ہیں\n• روزانہ کا کیش ٹِل سے نہیں ملتا\nکچھ رہ گیا؟",
                ctx(
                    "اسٹاک ختم ہو جاتا ہے",
                    (
                        ("c", "ویک اینڈ پر کیشیئر دیر سے آتے ہیں"),
                        ("a", "ٹھیک۔"),
                        ("c", "روزانہ کا کیش ٹِل سے نہیں ملتا"),
                        ("a", "ٹھیک۔"),
                    ),
                    **state("S3_NOTED"),
                ),
            ),
            (
                "• الكاشيرات يتأخرون في عطلة نهاية الأسبوع\n• النقد اليومي لا يطابق الصندوق\nهل فاتني شيء؟",
                ctx(
                    "المخزون ينفد",
                    (
                        ("c", "الكاشيرات يتأخرون في عطلة نهاية الأسبوع"),
                        ("a", "حسناً."),
                        ("c", "النقد اليومي لا يطابق الصندوق"),
                        ("a", "حسناً."),
                    ),
                    **state("S3_NOTED"),
                ),
            ),
            (
                "• वीकेंड पर कैशियर देर से आते हैं\n• रोज़ का कैश टिल से नहीं मिलता\nकुछ छूट गया?",
                ctx(
                    "स्टॉक खत्म हो जाता है",
                    (
                        ("c", "वीकेंड पर कैशियर देर से आते हैं"),
                        ("a", "ठीक है।"),
                        ("c", "रोज़ का कैश टिल से नहीं मिलता"),
                        ("a", "ठीक है।"),
                    ),
                    **state("S3_NOTED"),
                ),
            ),
        ],
        "good": [
            (
                "• Cashiers come late on weekends\n• Daily cash does not match the till\nIs anything missing?",
                ctx(
                    "cashiers come late on weekends and daily cash does not match the till",
                    **state("S3_NOTED"),
                ),
            ),
            (
                "• Cashiers come late on weekends\n• Daily cash does not match the till\nIs anything missing?",
                ctx(
                    "stock runs out",
                    (
                        ("c", "cashiers come late on weekends"),
                        ("c", "daily cash does not match the till"),
                    ),
                    **state("S4_SORTED_SUMMARY"),
                ),
            ),
            (
                "Noted: stock running out. Which shop?",
                ctx(
                    "stock runs out",
                    (("c", "cashiers come late on weekends"),),
                    **state("S3_NOTED"),
                ),
            ),
            (
                "• Stock runs out at the Gulberg shop every Friday\n• Delivery comes late\nIs anything missing?",
                ctx(
                    "stock runs out",
                    (
                        ("c", "cashiers come late on weekends"),
                        ("c", "daily cash does not match the till"),
                    ),
                    **state("S3_NOTED"),
                ),
            ),
            (
                "• वीकेंड पर कैशियर देर से आते हैं\n• रोज़ का कैश टिल से नहीं मिलता\nकुछ छूट गया?",
                ctx("वीकेंड पर कैशियर देर से आते हैं और रोज़ का कैश टिल से नहीं मिलता", **state("S3_NOTED")),
            ),
            ("Noted. Which shop is it?", ctx("stock runs out")),
        ],
    },
    "R-ASK-03": {
        "bad": [
            (
                "How many shops do you have?",
                ctx("stock runs out", (("c", "we have 4 shops in Lahore"),)),
            ),
            (
                "Does stock run out at the Gulberg shop every Friday?",
                ctx("it is bad", (("c", "stock runs out at the Gulberg shop every Friday"),)),
            ),
            (
                "Aap ki kitni dukaanein hain?",
                ctx("stock khatam hota hai", (("c", "hamari 4 dukaanein hain"),)),
            ),
            ("آپ کی کتنی دکانیں ہیں؟", ctx("اسٹاک ختم ہوتا ہے", (("c", "ہماری 4 دکانیں ہیں"),))),
            ("كم فروع لديك؟", ctx("المخزون ينفد", (("c", "عندنا 4 فروع"),))),
            ("आपकी कितनी दुकानें हैं?", ctx("स्टॉक खत्म होता है", (("c", "हमारी 4 दुकानें हैं"),))),
        ],
        "good": [
            (
                "How many staff work at the Gulberg shop?",
                ctx("stock runs out", (("c", "we have 4 shops in Lahore"),)),
            ),
            (
                "How many shops do you have?",
                ctx("stock runs out", (("c", "I have a few shops in Lahore"),)),
            ),
            (
                "Which shop runs out first?",
                ctx("stock runs out", (("c", "we have 4 shops in Lahore"),)),
            ),
            (
                "Does stock run out on Friday?",
                ctx("it is bad", (("c", "stock runs out at the Gulberg shop every Friday"),)),
            ),
            (
                "Aap ka staff kitna hai?",
                ctx("stock khatam hota hai", (("c", "hamari 4 dukaanein hain"),)),
            ),
            ("کتنا اسٹاک ختم ہوتا ہے؟", ctx("اسٹاک ختم ہوتا ہے", (("c", "ہماری 4 دکانیں ہیں"),))),
            ("كم موظفاً لديك؟", ctx("المخزون ينفد", (("c", "عندنا 4 فروع"),))),
            ("आपके कितने कर्मचारी हैं?", ctx("स्टॉक खत्म होता है", (("c", "हमारी 4 दुकानें हैं"),))),
        ],
    },
    "R-MEM-02": {
        "bad": [
            (
                "Where do you sell, online or in the shop?",
                ctx("stock runs out", customer_profile={"channels": "Instagram and walk-ins"}),
            ),
            (
                "What is your website?",
                ctx("stock runs out", customer_profile={"website": "acme.pk"}),
            ),
            (
                "What do you want to achieve?",
                ctx("stock runs out", customer_profile={"goal": "fewer stockouts"}),
            ),
            ("آپ کا نام کیا ہے؟", ctx("اسٹاک ختم ہوتا ہے", customer_profile={"name": "Ali"})),
            (
                "ما هو اسم نشاطك التجاري؟",
                ctx("المخزون ينفد", customer_profile={"business_name": "Noor Mart"}),
            ),
            ("आप किस शहर में हैं?", ctx("स्टॉक खत्म होता है", customer_profile={"location": "Lahore"})),
            (
                "Aap kahan bechte hain, online ya dukaan par?",
                ctx("stock khatam hota hai", what_i_know={"channels": "Instagram"}),
            ),
        ],
        "good": [
            (
                "Where do you sell, online or in the shop?",
                ctx("stock runs out", customer_profile={}),
            ),
            (
                "What is your website?",
                ctx("stock runs out", customer_profile={"website": "WhatsApp"}),
            ),
            (
                "What do you want to achieve?",
                ctx("stock runs out", customer_profile={"channels": "Instagram"}),
            ),
            ("آپ کا نام کیا ہے؟", ctx("اسٹاک ختم ہوتا ہے", customer_profile={"name": "unknown"})),
            ("ما هو اسم نشاطك التجاري؟", ctx("المخزون ينفد", customer_profile={"name": "Omar"})),
            ("आप किस शहर में हैं?", ctx("स्टॉक खत्म होता है", customer_profile={"name": "Raj"})),
            (
                "Which shop runs out first?",
                ctx(
                    "stock runs out",
                    customer_profile={"channels": "Instagram", "website": "acme.pk"},
                ),
            ),
        ],
    },
}

ALL = [
    (rule, side, i, case)
    for rule, sides in CASES.items()
    for side in sides
    for i, case in enumerate(sides[side])
]


@pytest.mark.parametrize("rule", sorted(CASES))
def test_each_rule_has_enough_cases_in_every_language_family(rule):
    assert len(CASES[rule]["bad"]) >= 6, rule
    assert len(CASES[rule]["good"]) >= 6, rule


@pytest.mark.parametrize(
    ("rule", "reply", "context"),
    [(r, case[0], case[1]) for r, s, _, case in ALL if s == "bad"],
    ids=[f"{r}-bad{i}" for r, s, i, _ in ALL if s == "bad"],
)
def test_a_reply_that_breaks_the_rule_is_caught(rule, reply, context):
    assert rule in broke(reply, context), reply


@pytest.mark.parametrize(
    ("rule", "reply", "context"),
    [(r, case[0], case[1]) for r, s, _, case in ALL if s == "good"],
    ids=[f"{r}-good{i}" for r, s, i, _ in ALL if s == "good"],
)
def test_a_normal_reply_passes_clean(rule, reply, context):
    assert rule not in broke(reply, context), reply


@pytest.mark.parametrize(
    ("rule", "reply", "context"),
    [(r, case[0], case[1]) for r, s, _, case in ALL if s == "bad"],
    ids=[f"{r}-bad{i}" for r, s, i, _ in ALL if s == "bad"],
)
def test_the_linter_reports_it_through_lint(rule, reply, context):
    """The hook in constitution.lint returns the same rule, so the usual retry and repair apply."""
    assert rule in {v.rule for v in c.lint(reply, context)}, reply


def test_hard_rules_are_hard_and_style_rules_soft():
    hard: set[str] = set()
    for rule, sides in CASES.items():
        reply, context = sides["bad"][0]
        found = [f for f in gaps.check(reply, context) if f[0] == rule]
        assert found, rule
        assert all(f[2] == (rule in hard) for f in found), rule


def test_check_is_pure_and_does_not_change_the_context():
    reply, context = CASES["R-ASK-05R"]["bad"][0]
    before = repr(context)
    assert gaps.check(reply, context) == gaps.check(reply, context)
    assert repr(context) == before


def test_check_survives_empty_and_odd_input():
    assert gaps.check("", {}) == []
    assert gaps.check("Hello.", {"history": None, "latest_customer_message": None}) == []
    assert gaps.check("Hello?", {"history": [{"role": "ai"}, {}], "flow": None}) == []


# ---- round 3: audit findings (soft only, AI-disclosure safety, narrower re-ask checks) -----------------
INTRO_Q = {
    "en": "What's going wrong in the business?",
    "ru": "Aap ke business mein kya masla hai?",
    "ur": "آپ کے کاروبار میں کیا مسئلہ ہے؟",
    "ar": "ما المشكلة في عملك؟",
    "hi": "आपके बिज़नेस में क्या समस्या है?",
}
IDENTITY_ANSWERS = [
    ("en", "are you human?", "I'm an AI, pi from Workzap. "),
    ("en", "is this a bot?", "Yes, I'm an AI. "),
    ("en", "who am I talking to", "You're talking to pi, an AI from Workzap. "),
    ("en", "are you a real person", "No, I'm an AI, not a person. "),
    ("en", "who are you", "I'm pi, an AI from Workzap. "),
    ("ru", "aap insaan hain?", "Main insaan nahi hoon, main ek AI hoon, Workzap ka pi. "),
    ("ru", "kya ye bot hai", "Ji, main ek AI hoon, pi. "),
    ("ru", "kya aap human hain", "Nahi, main AI hoon. "),
    ("ur", "کیا آپ انسان ہیں", "میں انسان نہیں ہوں، میں ایک اے آئی ہوں۔ "),
    ("ur", "یہ بوٹ ہے؟", "جی، میں اے آئی ہوں۔ "),
    ("ur", "میں کس سے بات کر رہا ہوں", "آپ ایک اے آئی سے بات کر رہے ہیں۔ "),
    ("ar", "هل أنت إنسان؟", "أنا لست إنساناً، أنا ذكاء اصطناعي. "),
    ("ar", "هل هذا بوت؟", "نعم، أنا ذكاء اصطناعي. "),
    ("ar", "مع من أتحدث", "أنت تتحدث مع ذكاء اصطناعي. "),
    ("hi", "क्या आप इंसान हैं", "मैं इंसान नहीं हूँ, मैं एक एआई हूँ। "),
    ("hi", "यह बॉट है?", "जी, मैं एक एआई हूँ। "),
    ("hi", "मैं किससे बात कर रहा हूँ", "आप एक एआई से बात कर रहे हैं। "),
]
MID = (("c", "stock runs out"), ("a", "Noted: stock runs out. Which shop?"))


@pytest.mark.parametrize(("lang", "asked", "answer"), IDENTITY_ANSWERS)
@pytest.mark.parametrize("repeat_intro", [True, False])
@pytest.mark.parametrize("mid", [True, False])
def test_an_ai_disclosure_answer_is_never_flagged_even_when_it_repeats_the_intro_question(
    lang, asked, answer, repeat_intro, mid
):
    reply = answer + (INTRO_Q[lang] if repeat_intro else "")
    context = ctx(asked, MID if mid else ())
    assert gaps.check(reply, context) == [], reply
    assert not {"R-ASK-05R", "R-ANS-02", "R-DISC-02"} & {v.rule for v in c.lint(reply, context)}, (
        reply
    )


def test_the_old_closer_and_the_new_re_ask_check_keep_different_ids():
    asked = (("a", "How many staff work in the evening shift?"),)
    assert "R-ASK-05R" in broke("How many staff are on the evening shift?", ctx("skip", asked))
    assert "R-ASK-05" not in broke("How many staff are on the evening shift?", ctx("skip", asked))


def test_a_narrower_follow_up_after_i_dont_know_is_a_new_question():
    asked = (("a", "How many shops lose stock?"),)
    assert "R-ASK-05R" not in broke("Is it every shop, or only some?", ctx("I don't know", asked))
    assert "R-ASK-05R" not in broke("Is it every shop?", ctx("I don't know", asked))
    assert "R-ASK-05R" in broke("How many shops lose stock each week?", ctx("I don't know", asked))


def test_the_opening_question_may_be_asked_again_after_a_side_question():
    assert "R-ASK-05R" not in broke(
        "Noted. What is going wrong?", ctx("what does Workzap do for shops, tell me", ())
    )


def test_re_ask_needs_half_the_words_after_a_skip_and_looks_back_two_turns():
    asked = (("a", "How many staff work in the evening shift?"),)
    assert "R-ASK-05R" in broke("How many staff cover the evening rota?", ctx("skip", asked))
    assert "R-ASK-05R" not in broke("How many drivers cover Fridays?", ctx("skip", asked))
    two_back = (
        ("a", "How many staff work in the evening shift?"),
        ("c", "six, and two more on Fridays maybe"),
        ("a", "Which shop opens first?"),
    )
    assert "R-ASK-05R" in broke("How many staff are on the evening shift?", ctx("skip", two_back))


def test_only_an_explicit_skip_counts_and_a_second_message_in_a_row_answers_it():
    asked = (("a", "How many staff work in the evening shift?"),)
    same = "How many staff work in the evening shift?"
    assert "R-ASK-05R" not in broke(same, ctx("the delivery is late again today", asked))
    assert "R-ASK-05R" not in broke(same, ctx("what do you think about that", asked))
    answered = (
        ("a", "Is it every shop, or only some?"),
        ("c", "mostly two shops, and the delivery is late"),
    )
    assert "R-ASK-05R" not in broke(
        "Is it every shop, or only some?", ctx("I don't know", answered)
    )


def test_the_emergency_reply_with_a_limit_after_the_numbers_is_not_flagged():
    reply = "Please call 1122 now. I can't help with emergencies, but the emergency services can."
    assert "R-CANT-01" not in {v.rule for v in c.lint(reply, ctx("my shop is on fire"))}
    assert gaps.check(reply, ctx("my shop is on fire")) == []


def test_a_refined_or_different_note_is_not_a_repeat_and_an_identical_one_is():
    before = (("a", "Noted: stock running out in the evening. Is it every shop, or only some?"),)
    assert "R-ECHO-01" not in broke(
        "Noted: the Gulberg branch running out of stock. Is it daily?",
        ctx("mostly Gulberg", before),
    )
    assert "R-ECHO-01" not in broke(
        "Noted: cashiers late on weekends. Is it every shop?", ctx("cashiers are late", before)
    )
    assert "R-ECHO-01" in broke(
        "Noted: stock running out in the evening. Is it daily?", ctx("yes", before)
    )


def test_a_question_about_another_fact_is_not_a_re_ask():
    assert "R-ASK-03" not in broke(
        "Lahore, theek. Aap ki kitni dukaanein hain?",
        ctx(
            "do dukaanon mein, aur supplier ki delivery aksar late hoti hai",
            (("c", "mera stock shaam ko khatam ho jata hai"),),
        ),
    )
    assert "R-ASK-03" not in broke(
        "How many shops do you have?", ctx("mostly two shops, and the delivery is often late")
    )
    assert "R-ASK-03" in broke(
        "How many shops do you have?", ctx("stock runs out", (("c", "we have 4 shops in Lahore"),))
    )
    assert "R-ASK-03" in broke(
        "Aap ki kitni dukaanein hain?",
        ctx("late aata hai", (("c", "hamari 4 dukaanon ka maal late aata hai"),)),
    )


def test_a_logistics_idea_that_mixes_fertiliser_orders_is_not_agronomy_advice():
    reply = "Mix the small fertiliser orders into one trip per area. Do drivers get the list the night before?"
    assert gaps.check(reply, ctx("fertiliser deliveries are late")) == []
    assert "R-SOL-09" in broke(
        "Mix the fertiliser into the soil before sowing. Which field?", ctx("the crop is weak")
    )


def test_ordinary_empathy_with_a_crisis_redirect_is_still_flagged_as_x5():
    reply = "That's a lot to carry. Please call 1122 if you need help. Which shop is hit hardest?"
    assert "X5" in broke(reply, ctx("I'm going bankrupt"))


def test_bullets_that_mostly_repeat_earlier_messages_are_flagged():
    earlier = (
        ("c", "cashiers come late on weekends"),
        ("a", "Noted."),
        ("c", "daily cash does not match the till"),
        ("a", "Noted."),
    )
    near = "• Cashiers come late on weekends again\n• Daily cash does not match the till again\nIs anything missing?"
    assert "R-ECHO-02" in broke(near, ctx("stock runs out", earlier, **state("S3_NOTED")))


def test_branch_is_a_label_only_where_the_owner_talks_about_branches_not_steps():
    assert "R-VOICE-11" not in broke(
        "Branch B is late. Which one?", ctx("step by step the second shop is late")
    )
    assert "R-VOICE-11" in broke("Branch B is late. Which one?", ctx("the Gulberg branch is late"))


def test_an_identity_answer_in_urdu_hindi_and_arabic_is_not_a_missing_yes():
    assert "R-ANS-02" not in broke("میں اے آئی ہوں۔ کون سی دکان؟", ctx("کیا آپ انسان ہیں؟"))
    assert "R-ANS-02" not in broke("मैं एक एआई हूँ। कौन सी दुकान?", ctx("क्या आप इंसान हैं?"))
    assert "R-ANS-02" not in broke("أنا ذكاء اصطناعي. أي فرع؟", ctx("هل أنت إنسان؟"))
    assert "R-ANS-02" not in broke("Main AI hoon. Kaunsi dukaan?", ctx("kya aap insaan hain?"))


def test_a_recap_of_what_was_noted_is_not_a_second_noted_line():
    before = (("a", "Noted: stock and late cashiers. Which one should we look at first?"),)
    recap = "Here is what I have noted: stock and late cashiers. Which one should we look at first?"
    assert "R-ECHO-01" not in broke(recap, ctx("what do you think", before))
    assert "R-ECHO-01" in broke("Noted: stock and late cashiers. Which first?", ctx("yes", before))


# ---- R-SOL-09: quantities and units are not medicine; ideas about perfume, coffee, hardware pass ----
UNIT_IDEAS = [
    "Give customers a 5 ml sample of the new perfume. Which shop sells the most perfume?",
    "Try the 250 ml bottle as the default size for the juice. Is it every shop, or only some?",
    "Start with a 500 ml iced coffee offer on Mondays. Which shop is busiest on Mondays?",
    "Offer a 10 ml travel perfume at the till. Is it every shop, or only some?",
    "Sell the 1 litre juice pack next to the cold drinks. Which shop has the fridge?",
    "Give regulars a free 30 ml oud sample on their third visit. Which shop has most regulars?",
    "Try a 200 mg caffeine-free blend as the evening coffee. Is it weekdays, or weekends?",
    "Start a 750 ml cold brew bottle for office orders. Which shop is near offices?",
    "Give every order over 2000 a 5 ml attar vial. Which shop has the larger orders?",
    "Try 100 ml tester bottles on the perfume shelf. Is it the main shop, or a smaller one?",
    "Start weighing the 5 kg nails pack before it goes on the shelf. Which shop has the scale?",
    "Stock the 20 litre paint tin near the brushes. Is it every shop, or some?",
    "Offer 250 g screw packs at the counter. Which shop sells screws?",
    "Bundle the 10 mm drill bits with the drill. Is it a few items, or many?",
    "Give contractors a printed price list for the 50 kg cement bags. Which shop serves contractors?",
    "Count the paracetamol packs on the shelf each evening. Which shop has the most packs?",
    "Keep a register of antibiotics sold each day, as the law already asks. Which shop keeps it?",
    "Label each 100 mg tablet strip with its expiry date. Is it every shop, or some?",
    "Sort the insulin pens in the fridge by expiry date. Which shop has the fridge?",
    "Give the customer a printed receipt for each prescription filled. Which shop prints it?",
    "Start a shelf card for the 500 mg vitamin packs. Which shop sells vitamins?",
    "Try a 60 ml hand sanitiser at the till. Is it every shop, or some?",
    "Give walk-in customers a 15 ml lotion sample. Which shop has walk-ins?",
    "Start a 1.5 litre water bottle bundle for families. Which shop has families?",
    "Offer the 330 ml can as a single, and the 6 pack as a deal. Which shop sells cans?",
    "Try a 100 g trial pack of the new tea. Is it weekdays, or weekends?",
    "Give new buyers a 250 ml sample of the floor cleaner. Which shop has new buyers?",
    "Stock the 5 ml super glue tubes by the till. Is it every shop, or some?",
    "Start a 2 litre refill price for the shampoo. Which shop has the refill station?",
    "Keep the 30 ml tester of each perfume behind the counter. Which shop has the counter?",
    "Try a 3 mg per sachet saffron pack as the gift option. Is it a few items, or many?",
    "Offer a 20 ml fragrance oil in the gift box. Is it every shop, or some?",
]


@pytest.mark.parametrize("reply", UNIT_IDEAS)
def test_quantities_and_units_are_not_regulated_advice(reply):
    assert "R-SOL-09" not in broke(reply, ctx("sales are slow")), reply
    assert "R-SOL-09" not in {v.rule for v in c.lint(reply, ctx("sales are slow"))}, reply


@pytest.mark.parametrize(
    "reply",
    [
        "File each GST invoice in a folder by month. Which shop files them?",
        "Start a vaccination calendar for each calf on a wall chart. Which farm?",
        "Apply a 10% discount on fertiliser bags bought in pairs. Which shop?",
        "Get the interest rate in writing from each supplier. Which one first?",
        "Reduce fertiliser waste by weighing each bag at the door. Which shop?",
        "Use a sheet to log the pesticide bought each week. Which shop?",
        "Khaad ka hisaab roz likh dein. Kaunsi dukaan?",
        "کھاد کا حساب روز لکھ دیں۔ کون سی دکان؟",
        "खाद का हिसाब रोज़ लिख दें। कौन सी दुकान?",
    ],
)
def test_other_domain_words_in_operational_ideas_pass(reply):
    assert "R-SOL-09" not in broke(reply, ctx("sales are slow")), reply


# ---- R-PROM-03 is soft and ignores generic seasonality --------------------------------------------
@pytest.mark.parametrize(
    "reply",
    [
        "Demand will increase before Eid, so shops usually plan ahead. Which shop is busiest?",
        "Sales will rise and fall through the year in most shops. Which shop is yours?",
        "Business will usually slow down in summer. Which shop feels it?",
        "Har saal Eid se pehle sales barh jati hain. Kaunsi dukaan?",
        "عید سے پہلے فروخت بڑھے گی۔ کون سی دکان؟",
        "المبيعات ستزداد قبل العيد عادة. أي فرع؟",
        "ईद से पहले बिक्री बढ़ेगी। कौन सी दुकान?",
    ],
)
def test_generic_seasonality_is_not_a_forecast(reply):
    assert "R-PROM-03" not in broke(reply, ctx("sales are slow")), reply


def test_forecasts_are_soft():
    found = [
        f
        for f in gaps.check("Your sales will drop next month. Which shop?", ctx("stock runs out"))
        if f[0] == "R-PROM-03"
    ]
    assert found
    assert not any(f[2] for f in found)


def test_no_gap_rule_is_hard():
    for rule, reply, context in (
        ("R-SOL-09", "Take paracetamol for the headache. Which shop?", ctx("my head hurts")),
        ("R-PROM-03", "Your sales will drop next month. Which shop?", ctx("stock runs out")),
    ):
        found = [f for f in gaps.check(reply, context) if f[0] == rule]
        assert found and not any(f[2] for f in found), rule


def test_forecast_the_person_already_said_is_exempt():
    context = ctx("our sales will drop next month, I am sure")
    assert "R-PROM-03" not in broke("Sales will drop next month, you say. Which shop?", context)
    assert "R-PROM-03" in broke(
        "Sales will drop next month, I think. Which shop?", ctx("stock runs out")
    )


def test_a_conditional_forecast_is_exempt():
    assert "R-PROM-03" not in broke(
        "Your sales will drop if stock keeps running out. Which shop?", ctx("stock runs out")
    )
    assert "R-PROM-03" in broke("Your sales will drop. Which shop?", ctx("stock runs out"))


# ---- R-PROM-02 flags deciding, not recommending ---------------------------------------------------
@pytest.mark.parametrize(
    "reply",
    [
        "My recommendation is to count the slips first. Which shop?",
        "My suggestion is to start with stock. Which one first?",
        "I'd suggest looking at cash before staff. Which shop?",
        "Mera mashwara hai ke pehle stock dekhein. Kaunsi dukaan?",
        "میرا مشورہ ہے کہ پہلے اسٹاک دیکھیں۔ کون سی دکان؟",
        "نصيحتي أن نبدأ بالمخزون. أي فرع؟",
        "मेरी सलाह है कि पहले स्टॉक देखें। कौन सी दुकान?",
    ],
)
def test_a_recommendation_is_allowed(reply):
    assert "R-PROM-02" not in broke(reply, ctx("three things are wrong")), reply


# ---- X5 ------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("reply", "latest"),
    [
        ("I'm here with you. Which shop is hit hardest?", "I'm going bankrupt"),
        ("That sounds hard. Which shop is hit hardest?", "I'm going bankrupt"),
        ("Sorry to hear that. Which shop is hit hardest?", "I'm going bankrupt"),
        ("Thank you for telling me. Which shop is hit hardest?", "I'm going bankrupt"),
        ("Main aap ke saath hoon. Kaunsi dukaan sab se zyada mutasir hai?", "dewaliya ho jaunga"),
        ("سن کر افسوس ہوا۔ کون سی دکان زیادہ متاثر ہے؟", "میں دیوالیہ ہونے والا ہوں"),
        ("أنا هنا معك. أي فرع الأكثر تأثراً؟", "سأفلس قريباً"),
        ("मैं आपके साथ हूँ। कौन सी दुकान सबसे ज़्यादा प्रभावित है?", "मैं दिवालिया हो जाऊँगा"),
    ],
)
def test_ordinary_empathy_is_an_acknowledgement(reply, latest):
    assert "X5" not in broke(reply, ctx(latest)), reply


@pytest.mark.parametrize(
    "reply",
    [
        "That's a lot to carry. I won't tell you whether to borrow or invest. Which shop is hit hardest?",
        "That sounds hard. I can't advise on whether to borrow. Which shop is hit hardest?",
        "I'm sorry. I'm not going to tell you to invest or borrow. Which shop is hit hardest?",
    ],
)
def test_declining_to_advise_is_not_advice(reply):
    assert "X5" not in broke(reply, ctx("I'm going bankrupt")), reply


@pytest.mark.parametrize(
    "reply",
    [
        "That's a lot to carry. You should borrow money from a cousin. Which shop?",
        "That's a lot to carry. Invest in a second shop. Which shop?",
    ],
)
def test_advice_to_borrow_or_invest_is_flagged(reply):
    assert "X5" in broke(reply, ctx("I'm going bankrupt")), reply


def test_x5_stays_quiet_in_an_emergency_state():
    reply = "Noted: going bankrupt. Which shop is hit hardest?"
    assert "X5" in broke(reply, ctx("I'm going bankrupt"))
    assert "X5" not in broke(reply, ctx("I'm going bankrupt", **state("X_EMERGENCY")))


# ---- R-CANT-01 / R-CANT-02 -------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("reply", "latest"),
    [
        (
            "Thank you. I can't confirm payment myself, staff confirm it. Which shop is it?",
            "did my payment go through",
        ),
        (
            "Shukriya. Payment main khud confirm nahi kar sakta, staff karega. Kaunsi dukaan?",
            "meri payment ho gayi",
        ),
        (
            "شکریہ۔ میں ادائیگی خود کنفرم نہیں کر سکتا، عملہ کرے گا۔ کون سی دکان؟",
            "میری ادائیگی ہو گئی",
        ),
        ("شكراً. لا أستطيع تأكيد الدفع بنفسي، الموظفون يؤكدونه. أي فرع؟", "هل تم الدفع"),
        ("धन्यवाद। मैं भुगतान खुद पुष्टि नहीं कर सकता, स्टाफ करेगा। कौन सी दुकान?", "मेरा भुगतान हो गया"),
        (
            "I can't confirm payment myself. Staff confirm it, then I tell you.",
            "did my payment go through",
        ),
    ],
)
def test_a_limit_after_a_pleasantry_or_as_the_first_sentence_is_fine(reply, latest):
    found = broke(reply, ctx(latest))
    assert "R-CANT-01" not in found, reply
    assert "R-CANT-02" not in found, reply


def test_cant_02_is_exempt_with_emergency_numbers_or_a_next_step():
    assert "R-CANT-02" not in broke(
        "I can't help with that. Please call 1122 now.", ctx("my shop is on fire")
    )
    assert "R-CANT-02" not in broke(
        "I can't confirm that. Staff will confirm it.", ctx("is it paid")
    )
    assert "R-CANT-02" in broke("I can't confirm that.", ctx("is it paid"))


def test_a_refusal_that_is_a_question_or_a_conditional_is_not_a_refusal():
    sentences_before = "Noted. We looked at the stock together. "
    assert "R-CANT-01" not in broke(
        sentences_before + "I can't give tax advice. Which shop?", ctx("tax")
    )
    assert "R-CANT-01" not in broke(
        sentences_before + "Can I tell you why I can't give tax advice? Which shop?", ctx("tax")
    )
    assert "R-CANT-01" not in broke(
        sentences_before + "If I can't help with that, I will say so. Which shop?", ctx("tax")
    )
    assert "R-CANT-02" not in broke("Can I explain why I can't give tax advice?", ctx("tax"))
    assert "R-CANT-02" not in broke("If I can't help, I will say so.", ctx("tax"))


# ---- R-ANS-02 and the AI-disclosure non-negotiable --------------------------------------------------
HUMAN_ASKED = [
    ("Are you human?", "I'm an AI from Workzap, not a person. Which shop is it?"),
    ("Are you human?", "I'm pi, an AI. Which shop is it?"),
    ("kya aap insaan hain?", "Main AI hoon, Workzap ka. Kaunsi dukaan?"),
    ("کیا آپ انسان ہیں؟", "میں اے آئی ہوں، Workzap کی طرف سے۔ کون سی دکان؟"),
    ("هل أنت إنسان؟", "أنا ذكاء اصطناعي من Workzap. أي فرع؟"),
    ("क्या आप इंसान हैं?", "मैं एक एआई हूँ, Workzap का। कौन सी दुकान?"),
    ("Pouvez-vous me dire si vous êtes humain ?", "Je suis une IA de Workzap. Quel magasin ?"),
]


@pytest.mark.parametrize(("asked", "reply"), HUMAN_ASKED)
def test_i_am_an_ai_answers_are_you_human(asked, reply):
    context = ctx(asked)
    assert "R-ANS-02" not in broke(reply, context), reply
    assert "R-ANS-02" not in {v.rule for v in c.lint(reply, context)}, reply


def test_the_ai_disclosure_rule_is_never_blocked_by_ans_02():
    for asked, reply in HUMAN_ASKED:
        context = ctx(asked)
        assert not any(v.rule in ("R-ANS-02", "R-DISC-02") for v in c.lint(reply, context)), (
            asked,
            reply,
        )


def test_a_workzap_statement_answers_can_you_fix_this():
    assert "R-ANS-02" not in broke(
        "Workzap handles stock problems like this. Which shop is it?", ctx("Can you fix this?")
    )
    assert "R-ANS-02" in broke("Stock problems are common.", ctx("Can you fix this?"))


@pytest.mark.parametrize(
    ("reply", "latest"),
    [
        ("Of course. Which shop?", "Can you help with stock?"),
        ("They are available. Which shop?", "Are they open on Friday?"),
        ("Kar sakte hain. Kaunsi dukaan?", "kya aap stock ka masla theek kar sakte hain?"),
        ("ہو سکتا ہے۔ کون سی دکان؟", "کیا یہ ہو سکتا ہے؟"),
        ("कर सकते हैं। कौन सी दुकान?", "क्या आप स्टॉक की समस्या हल कर सकते हैं?"),
    ],
)
def test_phrase_answers_count_as_yes_or_no(reply, latest):
    assert "R-ANS-02" not in broke(reply, ctx(latest)), reply


# ---- R-VOICE-11 -------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "reply",
    [
        "Item 1 is the quote, Item 2 is the terms. Which shop?",
        "Unit 1 has the freezer. Which shop?",
        "Customer 2 asked for a refund. Which shop?",
        "Step 2 is counting the till. Which shop?",
        "Point 3 is about delivery. Which shop?",
        "Option A is weekly, option B is monthly. Which shop?",
        "Branch 2 is not named yet, so which branch is it?",
    ],
)
def test_structural_labels_are_not_invented_names(reply):
    assert "R-VOICE-11" not in broke(reply, ctx("stock runs out")), reply


def test_a_location_label_is_still_caught_and_a_document_is_exempt():
    assert "R-VOICE-11" in broke("Stock runs out at Location 2. Which shop?", ctx("stock runs out"))
    assert "R-VOICE-11" not in broke(
        "Quote line: Location 2 delivery. Which shop?", ctx("stock runs out", **state("S8_REVIEW"))
    )
    # "Branch 2" is only a label where the owner talks about branches
    assert "R-VOICE-11" in broke("Branch B is late. Which one?", ctx("the Gulberg branch is late"))
    assert "R-VOICE-11" not in broke("Branch B is late. Which one?", ctx("the second shop is late"))


# ---- the rule-id split --------------------------------------------------------------------------------
def test_the_skipped_question_check_has_its_own_id_and_the_old_closer_keeps_r_ask_05():
    asked = (("a", "How many staff work in the evening shift?"),)
    reasked = {
        v.rule for v in c.lint("How many staff are on the evening shift?", ctx("skip", asked))
    }
    assert "R-ASK-05R" in reasked and "R-ASK-05" not in reasked
    closer = c.lint(
        "Noted: stock runs out at the Gulberg shop every Friday. Anything else?",
        ctx(
            "stock runs out at the Gulberg shop every Friday and it costs us a lot",
            **state("S1_LISTENING"),
        ),
    )
    assert "R-ASK-05" in {v.rule for v in closer}
    assert "R-ASK-05R" not in {v.rule for v in closer}


# ---- exemptions that used to be untested -------------------------------------------------------------
def test_regulated_advice_the_person_already_said_is_exempt():
    said = ctx("the agronomist told us to apply urea twice")
    assert "R-SOL-09" not in broke("So you apply urea twice. Which field?", said)
    assert "R-SOL-09" in broke(
        "Apply urea twice on the wheat field. Which field?", ctx("the crop is weak")
    )


def test_the_comfort_line_is_not_pressure():
    hesitant = ctx("I'd rather not say the amount")
    assert "R-PRIV-08" not in broke(
        "Please just tell me what you're comfortable sharing. Which shop?", hesitant
    )
    assert "R-PRIV-08" in broke("Please just tell me the amount. Which shop?", hesitant)


def test_brief_writer_limit_is_five_words_and_choice_questions_are_closed():
    brief = (("c", "stock"), ("a", "Noted: stock. Which part of it?"), ("c", "yes"))
    longer = (("c", "mostly the second shop at the main road"), ("a", "Noted. Which part of it?"))
    assert "R-ASK-04" in broke("How does that happen in your shops?", ctx("mostly", brief))
    assert "R-ASK-04" not in broke(
        "How does that happen in your shops?", ctx("mostly the second shop at the road", longer)
    )
    assert "R-ASK-04" not in broke("How does it go, daily or weekly?", ctx("mostly", brief))
    assert "R-ASK-04" not in broke("How does that happen in your shops?", ctx("mostly", longer))


def test_noted_twice_means_no_new_fact():
    before = (("a", "Noted: best-sellers running out badly. Which shop?"),)
    same = "Noted: best sellers running out. Is it weekly?"
    assert "R-ECHO-01" in broke(same, ctx("it is weekly", before))
    refined = "Noted: best sellers running low at Gulberg. Is it weekly?"
    assert "R-ECHO-01" not in broke(refined, ctx("it is weekly", before))
    other = "Noted: best selling mugs breaking. Is it weekly?"
    assert "R-ECHO-01" not in broke(other, ctx("it is weekly", before))


def test_bullets_that_only_partly_repeat_earlier_messages_pass():
    earlier = (
        ("c", "cashiers come late on weekends"),
        ("a", "Noted."),
        ("c", "daily cash does not match the till"),
        ("a", "Noted."),
    )
    mixed = "• Cashiers come late on weekends at the airport shop\n• Daily cash does not match at the airport till\nIs anything missing?"
    assert "R-ECHO-02" not in broke(mixed, ctx("stock runs out", earlier, **state("S3_NOTED")))
    plain = "• Cashiers come late on weekends\n• Daily cash does not match the till\nIs anything missing?"
    assert "R-ECHO-02" in broke(plain, ctx("stock runs out", earlier, **state("S3_NOTED")))


def test_a_confirming_question_is_not_a_re_ask():
    said = ctx(
        "stock runs out at the Gulberg shop every Friday and that is correct", (("c", "ok"),)
    )
    assert "R-ASK-03" not in broke(
        "Stock runs out at the Gulberg shop every Friday, correct?", said
    )
    assert "R-ASK-03" in broke("Does stock run out at the Gulberg shop every Friday?", said)


def test_advice_the_person_said_first_is_exempt_even_when_phrased_as_an_instruction():
    said = ctx("the agronomist told us to apply urea twice on the wheat field")
    assert "R-SOL-09" not in broke(
        "Apply urea twice on the wheat field, as the agronomist said. Which field?", said
    )
    assert "R-SOL-09" in broke(
        "Apply urea twice on the wheat field, as I said. Which field?", ctx("the crop is weak")
    )


def test_a_sentence_that_declines_to_advise_on_a_loan_is_not_advice():
    distress = ctx("I'm going bankrupt")
    assert "X5" not in broke(
        "That sounds hard. I can't tell you whether to take a loan. Which shop?", distress
    )
    assert "X5" in broke("That sounds hard. Take a loan from the bank. Which shop?", distress)


def test_a_decision_the_person_quoted_is_not_pi_deciding():
    said = ctx("the consultant said you must fire the manager")
    assert "R-PROM-02" not in broke(
        "Noted: the consultant said you must fire the manager. Which shop?", said
    )
    assert "R-PROM-02" in broke(
        "You must fire the manager. Which shop?", ctx("the manager is slow")
    )


def test_an_identity_answer_that_repeats_a_skipped_question_is_not_retried():
    asked = (("a", "Which shop loses stock first?"),)
    context = ctx("skip, are you human?", asked)
    assert "R-ASK-05R" not in broke(
        "I'm an AI from Workzap. Which shop loses stock first?", context
    )
    assert "R-ASK-05R" in broke("Noted. Which shop loses stock first?", context)


def test_a_follow_up_of_another_shape_after_a_skip_is_a_new_question():
    asked = (("a", "How many shops lose stock each week?"),)
    assert "R-ASK-05R" not in broke(
        "Do shops lose stock each week, or only some?", ctx("I don't know", asked)
    )
    assert "R-ASK-05R" in broke("How many shops lose stock each week?", ctx("I don't know", asked))


def test_a_conditional_limit_is_not_a_limit_so_it_needs_no_next_step():
    assert "R-CANT-02" not in broke("If I can't help, that is that.", ctx("tax"))
    assert "R-CANT-02" in broke("I can't help, that is that.", ctx("tax"))
