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
                "برانچ 2 میں اسٹاک ختم ہوتا ہے۔ کیا روز ہوتا ہے؟",
                ctx("گلبرگ والی دکان میں اسٹاک ختم ہوتا ہے"),
            ),
            ("الفرع 2 يعاني من نقص المخزون. هل يحدث يومياً؟", ctx("فرع الجلبرغ ينقصه المخزون")),
            ("दुकान 2 में स्टॉक खत्म होता है। क्या रोज़ होता है?", ctx("गुलबर्ग वाली दुकान में स्टॉक खत्म होता है")),
            (
                "Customer A keeps returning items. Is it every week?",
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
    "R-ASK-05": {
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
                "How many staff work in the evening shift?",
                ctx(
                    "the delivery is late again today",
                    (("a", "How many staff work in the evening shift?"),),
                ),
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
    "R-CANT-01": {
        "bad": [
            (
                "Thanks for asking about that. I can't give tax advice. Which shop loses stock?",
                ctx("how much tax should I pay"),
            ),
            (
                "Samajh gaya. Ye main nahi kar sakta. Kaunsi dukaan se shuru karein?",
                ctx("tax kitna dena chahiye"),
            ),
            ("ٹھیک ہے۔ میں یہ نہیں کر سکتا۔ آپ کی کون سی دکان ہے؟", ctx("ٹیکس کتنا دوں")),
            ("حسناً. لا أستطيع فعل ذلك. أي فرع؟", ctx("كم الضريبة التي أدفعها")),
            ("ठीक है। मैं यह नहीं कर सकता। कौन सी दुकान?", ctx("टैक्स कितना दूँ")),
            (
                "D'accord. Je ne peux pas faire cela. Quel magasin ?",
                ctx("combien d'impôt dois-je payer"),
            ),
            ("Entiendo. No puedo hacer eso. ¿Qué tienda?", ctx("cuánto impuesto debo pagar")),
        ],
        "good": [
            ("I can't do that. Which shop loses stock?", ctx("how much tax should I pay")),
            (
                "Thanks, but I can't give tax advice. Which shop loses stock?",
                ctx("how much tax should I pay"),
            ),
            (
                "Ye main nahi kar sakta. Kaunsi dukaan se shuru karein?",
                ctx("tax kitna dena chahiye"),
            ),
            ("میں یہ نہیں کر سکتا۔ کون سی دکان سے شروع کریں؟", ctx("ٹیکس کتنا دوں")),
            ("لا أستطيع فعل ذلك. أي فرع؟", ctx("كم الضريبة التي أدفعها")),
            ("मैं यह नहीं कर सकता। कौन सी दुकान?", ctx("टैक्स कितना दूँ")),
            ("Noted: stock runs out. Which shop?", ctx("stock runs out")),
            ("Cashiers can't log in? Which shop is it?", ctx("cashiers can't log in")),
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
            ("My recommendation is to fire the manager. Which shop?", ctx("the manager is slow")),
            (
                "You need to close the second shop. Which one is weaker?",
                ctx("two shops lose money"),
            ),
            (
                "Mera mashwara hai ke aap manager ko nikal dein. Kaunsi dukaan?",
                ctx("manager sust hai"),
            ),
            ("میرا مشورہ ہے کہ آپ مینیجر کو نکال دیں۔ کون سی دکان؟", ctx("مینیجر سست ہے")),
            ("نصيحتي أن تغلق الفرع الثاني. أي فرع؟", ctx("فرعان يخسران")),
            ("मेरी सलाह है कि आप मैनेजर को निकाल दें। कौन सी दुकान?", ctx("मैनेजर सुस्त है")),
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
                "Note kar liya: stock khatam ho jata hai, roz. Kaunsi dukaan?",
                ctx("roz hota hai", (("a", "Note kar liya: stock khatam ho jata hai."),)),
            ),
            (
                "نوٹ کر لیا: اسٹاک ختم ہو جاتا ہے روز۔ کون سی دکان؟",
                ctx("روز ہوتا ہے", (("a", "نوٹ کر لیا: اسٹاک ختم ہو جاتا ہے۔"),)),
            ),
            (
                "تم تسجيل: نفاد المخزون يومياً. أي فرع؟",
                ctx("يومياً", (("a", "تم تسجيل: نفاد المخزون."),)),
            ),
            (
                "नोट कर लिया: स्टॉक खत्म हो जाता है रोज़। कौन सी दुकान?",
                ctx("रोज़", (("a", "नोट कर लिया: स्टॉक खत्म हो जाता है।"),)),
            ),
            (
                "C'est noté : rupture de stock tous les jours. Quel magasin ?",
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
    hard = {"R-PROM-03", "R-SOL-09"}
    for rule, sides in CASES.items():
        reply, context = sides["bad"][0]
        found = [f for f in gaps.check(reply, context) if f[0] == rule]
        assert found, rule
        assert all(f[2] == (rule in hard) for f in found), rule


def test_check_is_pure_and_does_not_change_the_context():
    reply, context = CASES["R-ASK-05"]["bad"][0]
    before = repr(context)
    assert gaps.check(reply, context) == gaps.check(reply, context)
    assert repr(context) == before


def test_check_survives_empty_and_odd_input():
    assert gaps.check("", {}) == []
    assert gaps.check("Hello.", {"history": None, "latest_customer_message": None}) == []
    assert gaps.check("Hello?", {"history": [{"role": "ai"}, {}], "flow": None}) == []
